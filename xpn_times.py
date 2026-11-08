#!/usr/bin/env python3
"""
xpn_times.py — look up real show times for WXPN concert listings.

XPN's calendar gives a date, artist, venue, and a ticket link, but no time.
This module follows each ticket link with requests + BeautifulSoup and tries,
in order:
  1. schema.org JSON-LD "startDate" with a clock time (most ticketing pages)
  2. text labelled "Show"/"Starts"/"Music" followed by a time
  3. "Doors" time plus one hour
  4. the earliest evening time (5 PM or later) on the page

Results are cached in a JSON file keyed by XPN event id so each ticket page is
fetched once; pages that gave no time are retried every RETRY_DAYS.
Some ticketing platforms block automated requests outright (Ticketmaster, AXS,
Tixr, Etix); those are skipped and the show keeps the placeholder time.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:  # keep the feed building even without the extras
    requests = None

ET = ZoneInfo("America/New_York")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
BLOCKED = {"ticketmaster.com", "axs.com", "tixr.com", "etix.com", "livenation.com",
           "instagram.com", "facebook.com"}
RETRY_DAYS = 7
WORKERS = 8

CLOCK = r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?"
LABELLED = re.compile(r"\b(show|showtime|starts?|start time|music|performance|concert)\b\W{0,12}(?:at\W)?" + CLOCK, re.I)
DOORS = re.compile(r"\bdoors?\b\W{0,12}(?:at\W)?(?:open\W{0,3})?" + CLOCK, re.I)
ANY = re.compile(r"(?<![\d:])" + CLOCK + r"(?![\d:])", re.I)
LD_START = re.compile(r'"startDate"\s*:\s*"([^"]+)"')


def _t(h, m, ap):
    h = int(h)
    if h > 12:
        return None
    return dt.time(h % 12 + (12 if ap.lower() == "p" else 0), int(m or 0))


def plausible(t):
    return t is not None and dt.time(10, 0) <= t <= dt.time(23, 59)


def from_jsonld(html, show_date):
    for raw in LD_START.findall(html):
        if "T" not in raw:
            continue
        try:
            d = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if d.tzinfo:
            local = d.astimezone(ET)
            # Some sites stamp the right clock time with the wrong zone; trust the
            # conversion only if it still lands on the show's date.
            d = local if local.date() == show_date else d.replace(tzinfo=None)
        t = d.time().replace(second=0, microsecond=0)
        if plausible(t):
            return t, "jsonld"
    return None


def date_patterns(d):
    """Ways the show date might be written on the page: Nov 12, November 12, 11/12, 11.12, 2026-11-12."""
    mon, day = d.strftime("%b"), d.day
    return [re.compile(p, re.I) for p in (
        rf"\b{mon}[a-z]*\.?\s+{day}\b", rf"\b{d.month}/{day}(?:/\d{{2,4}})?\b",
        rf"\b{d.month}\.{day}\b", rf"\b{d:%Y-%m-%d}\b", rf"\b{day}\s+{mon}[a-z]*\b")]


def near_date(text, pos, show_date, window=400):
    """True if the show's date is written within `window` characters of position `pos`."""
    seg = text[max(0, pos - window): pos + window]
    return any(p.search(seg) for p in date_patterns(show_date))


def from_text(text, show_date):
    m = LABELLED.search(text)
    if m:
        t = _t(*m.groups()[1:])
        if plausible(t):
            return t, "show"
    # Looser rules only count when the time sits next to the show's date, so a
    # restaurant's "open 5:00 PM" or box-office hours elsewhere on the page don't win.
    for m in DOORS.finditer(text):
        t = _t(*m.groups())
        if plausible(t) and near_date(text, m.start(), show_date):
            return (dt.datetime.combine(dt.date.today(), t) + dt.timedelta(hours=1)).time(), "doors+1h"
    evening = sorted(t for t in (_t(*m.groups()) for m in ANY.finditer(text)
                                 if near_date(text, m.start(), show_date))
                     if plausible(t) and t >= dt.time(17, 0))
    if evening:
        return evening[0], "evening-time-near-date"
    return None


def lookup(url, show_date):
    """Return (time, source) or (None, reason)."""
    host = urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")
    if any(host == b or host.endswith("." + b) for b in BLOCKED):
        return None, "blocked-site"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
    except Exception as e:
        return None, f"error:{type(e).__name__}"
    if r.status_code != 200 or len(r.text) < 500:
        return None, f"http:{r.status_code}"
    hit = from_jsonld(r.text, show_date)
    if hit:
        return hit
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" "))
    hit = from_text(text, show_date)
    return hit if hit else (None, "no-time-found")


def resolve_times(events, cache_path):
    """events: list of {id, website, date(YYYY-MM-DD)}. Returns {id: {time, source}}."""
    cache = {}
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            cache = json.load(f)
    if requests is None:
        print("requests/beautifulsoup4 not installed; using cached times only", file=sys.stderr)
        return cache

    today = dt.date.today().isoformat()
    todo = []
    for e in events:
        key = str(e["id"])
        c = cache.get(key)
        if not e.get("website"):
            continue
        if c and (c.get("time") or c.get("checked", "") > (dt.date.today() - dt.timedelta(days=RETRY_DAYS)).isoformat()):
            continue
        if c and c.get("source") == "blocked-site":
            continue
        todo.append(e)

    def work(e):
        t, src = lookup(e["website"], dt.date.fromisoformat(e["date"]))
        return str(e["id"]), {"time": t.strftime("%H:%M") if t else None, "source": src, "checked": today,
                              "url": e["website"]}

    if todo:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for key, rec in pool.map(work, todo):
                cache[key] = rec

    # drop cache rows for events no longer listed
    live = {str(e["id"]) for e in events}
    cache = {k: v for k, v in cache.items() if k in live}
    if os.path.dirname(cache_path):
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(cache, f, indent=1, sort_keys=True)
    found = sum(1 for v in cache.values() if v.get("time"))
    print(f"show times: looked up {len(todo)} pages; {found} of {len(live)} shows have a real time", file=sys.stderr)
    return cache
