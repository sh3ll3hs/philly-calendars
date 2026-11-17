"""Shared pieces for the readers of the Queer Tech Events feed (queertech_sources.json)."""
import datetime as dt
import html
import re

import urllib.parse
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

try:
    from curl_cffi import requests as cf_requests
except ImportError:
    cf_requests = None

import combined_to_ics as C
from combined_readers import zones

EASTERN = zones.NY

TZ_MAP = {
    "PST": ZoneInfo("America/Los_Angeles"),
    "PDT": ZoneInfo("America/Los_Angeles"),
    "MST": ZoneInfo("America/Denver"),
    "MDT": ZoneInfo("America/Denver"),
    "CST": ZoneInfo("America/Chicago"),
    "CDT": ZoneInfo("America/Chicago"),
    "EST": ZoneInfo("America/New_York"),
    "EDT": ZoneInfo("America/New_York"),
    "CET": ZoneInfo("Europe/Amsterdam"),
    "CEST": ZoneInfo("Europe/Amsterdam"),
    "GMT": ZoneInfo("Etc/UTC"),
    "UTC": ZoneInfo("Etc/UTC"),
    "BST": ZoneInfo("Europe/London"),
    "AEDT": ZoneInfo("Australia/Sydney"),
    "AEST": ZoneInfo("Australia/Sydney"),
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_cloudflare_text(url: str) -> str:
    """Fetch HTML from a Cloudflare/WAF-protected page using curl_cffi TLS impersonation."""
    C.http._wait(url)
    if cf_requests is not None:
        resp = cf_requests.get(url, impersonate="chrome120", headers=HEADERS, timeout=20)
    else:
        resp = C.http._SESSION.get(url, headers=HEADERS, timeout=20)
    if resp.status_code in (403, 406):
        raise C.http.BlockedError(f"{resp.status_code} from {urllib.parse.urlsplit(url).netloc}")
    resp.raise_for_status()
    return resp.text


def fetch_cloudflare_protected(url: str) -> BeautifulSoup:
    return BeautifulSoup(fetch_cloudflare_text(url), "html.parser")


MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
RSVP_TEXT = re.compile(r"\b(register|registration|rsvp|tickets?|sign up|apply|reserve|save (?:my|your) (?:spot|seat))\b", re.I)
ONLINE_RX = re.compile(r"^\W*(virtual|online|zoom|webinar|remote|google meet|microsoft teams|livestream)\b", re.I)


def lines(body):
    """Page -> its visible text, one line per block element. A link is kept as a
    marker ⟦url⟧ in front of its text, so a reader can pick up the link for a line."""
    b = re.sub(r"<(script|style|noscript|svg)\b[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    b = re.sub(r"<!--.*?-->", " ", b, flags=re.S)
    b = re.sub(r'<a\b[^>]*?href="([^"]*)"[^>]*>', lambda m: "⟦" + html.unescape(m.group(1)).strip() + "⟧", b, flags=re.I)
    b = re.sub(r"</?(p|div|h[1-6]|li|ul|ol|section|article|br|tr|td|th|header|footer|small|time|figure|blockquote|title)\b[^>]*>",
               "\n", b, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", b))
    return [l for l in (re.sub(r"[ \t\xa0\r]+", " ", x).strip() for x in t.split("\n")) if l]


def plain(line):
    """A line without its link markers."""
    return C.clean(re.sub(r"⟦[^⟧]*⟧", " ", line))


def links(line):
    return re.findall(r"⟦([^⟧]*)⟧", line)


def place(s):
    """'Online' for a virtual event, else the cleaned text."""
    s = C.clean(s)
    return "Online" if ONLINE_RX.match(s) else s


def cached(ctx, url, budget, parse):
    """Details of one event page: from the state file when read within the last week,
    else fetched and parsed with parse(body) -> dict. `budget` is a one-item list
    counting the pages this source may still open in this run; None when it is spent
    (the caller then goes without the details until the next run)."""
    cache, today = ctx.get("detail"), ctx["today"]
    hit = cache.get(url) if isinstance(cache, dict) else None
    if hit and isinstance(hit.get("info"), dict):
        try:
            if (today - dt.date.fromisoformat(hit["fetched"])).days < C.DETAIL_TTL_DAYS:
                return hit["info"]
        except (KeyError, TypeError, ValueError):
            pass
    if budget[0] <= 0:
        return hit["info"] if hit and isinstance(hit.get("info"), dict) else None
    budget[0] -= 1
    try:
        info = parse(C.get_text(url))
    except C.http.BlockedError:
        raise
    except Exception:
        return hit["info"] if hit and isinstance(hit.get("info"), dict) else None
    if isinstance(cache, dict):
        cache[url] = {"fetched": today.isoformat(), "events": [], "info": info}
    return info


TICKET_HOSTS = re.compile(r"(^|\.)(eventbrite\.[a-z.]+|lu\.ma|luma\.com|partiful\.com|humanitix\.com|tickettailor\.com|"
                          r"ticketleap\.events|givebutter\.com|cvent\.com|cvent\.me|splashthat\.com|zoom\.us|meetup\.com|"
                          r"forms\.gle|typeform\.com|jotform\.com|airtable\.com)$", re.I)


def find_rsvp(body, page_url):
    """The sign-up link on an event page: the first link to a ticketing or forms
    service, else the first off-site link whose text says register / RSVP / tickets.
    '' when the page has neither (sign-up is then on the page itself)."""
    import urllib.parse
    own = urllib.parse.urlsplit(page_url).netloc.lower().removeprefix("www.")
    worded = ""
    for href, label in re.findall(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', body, re.S | re.I):
        h = html.unescape(href).strip()
        if not h.startswith("http"):
            continue
        host = urllib.parse.urlsplit(h).netloc.lower().removeprefix("www.")
        if host == own or re.search(r"facebook\.|twitter\.|x\.com$|linkedin\.|google\.com$|instagram\.", host):
            continue
        if TICKET_HOSTS.search(host):
            return h
        if not worded and RSVP_TEXT.search(C.clean(re.sub(r"<[^>]+>", " ", label))):
            worded = h
    return worded


def rsvp_from_pages(src, events, ctx):
    """For a registry entry with "rsvp_pages": true: open each event's own page (kept a
    week in the state file, at most "detail_max" new pages per run, default 12) and
    add the sign-up link found there. Events that already have one are left alone."""
    budget = [int(src.get("detail_max", C.DETAIL_PER_SOURCE))]
    for e in events:
        url = e.get("url") or ""
        if e.get("rsvp") or "raw" in e or not url.startswith("http") or url.rstrip("/") == src["url"].rstrip("/"):
            continue
        info = cached(ctx, url, budget, lambda body, u=url: {"rsvp": find_rsvp(body, u)})
        if info and info.get("rsvp"):
            e["rsvp"] = info["rsvp"]
    return events
