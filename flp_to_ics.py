#!/usr/bin/env python3
"""
flp_to_ics.py — Free Library of Philadelphia events as a subscribable .ics.

The calendar site (libwww.freelibrary.org/calendar) sits behind a Cloudflare
bot challenge, so it isn't scraped. The library's own RSS feeds are not behind
it and carry everything needed:
    /rss/eventsrss.cfm?location=<BRANCH>&type=<CATEGORY>
    item title: "11/12/26: Chair Yoga - Andorra Library"
    item description ends: "11/12/26, 10:00 A.M. - Andorra Library"
    item link:  /calendar/event/<id>

Each feed returns only the next 10 events, so the script walks every branch
(codes read from the RSS menu) and, for branches whose feed is full, each
category too, then merges the results into a running history file. Run daily,
the calendar fills in further ahead each day. It skips itself if it already ran
in the last 20 hours, to keep load on the library's server low.

Usage:
    python3 flp_to_ics.py                                   # writes flp.ics + flp_history.json
    python3 flp_to_ics.py --out docs/flp.ics --history docs/flp_history.json
    python3 flp_to_ics.py --force                           # ignore the once-a-day guard

Needs requests + beautifulsoup4 (via common/http.py).
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys

from bs4 import BeautifulSoup

from common import http
from pgc_to_ics import VTIMEZONE, TZID, esc, fold

BASE = "https://libwww.freelibrary.org"
MENU = BASE + "/rss/rssmenu.cfm"
FEED = BASE + "/rss/eventsrss.cfm"
CATEGORIES = [1, 2, 3, 4, 5, 6, 8, 10]  # 7 duplicates 2; 9, 11+ are empty
FULL = 10                                # items per feed
DEFAULT_MIN = 60
MAX_DESC = 500
WHEN = re.compile(r"(\d{2})/(\d{2})/(\d{2}),\s*(\d{1,2}):(\d{2})\s*([AP])\.?M\.?\s*-\s*(.+?)\s*$", re.I)


def branches():
    soup = BeautifulSoup(http.get_text(MENU), "html.parser")
    sel = soup.find("select", attrs={"name": "location"})
    return [(o["value"], o.get_text(strip=True)) for o in sel.find_all("option") if o.get("value")] if sel else []


def text(s):
    s = html.unescape(html.unescape(s or ""))
    s = re.sub(r"<br\s*/?>|</p>|</li>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s).replace("#39;", "'")
    return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", s)).strip()


def parse_feed(xml, category=None):
    out = []
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
        g = lambda tag: (re.search(rf"<{tag}>(.*?)</{tag}>", it, re.S) or [None, ""])[1].strip()
        title, link, desc = html.unescape(g("title")), g("link"), text(g("description"))
        m = re.search(r"/calendar/event/(\d+)", link)
        if not m:
            continue
        last = desc.strip().splitlines()[-1] if desc.strip() else ""
        w = WHEN.search(last)
        if w:
            mo, dd, yy, h, mi, ap, branch = w.groups()
            h = int(h) % 12 + (12 if ap.upper() == "P" else 0)
            start = dt.datetime(2000 + int(yy), int(mo), int(dd), h, int(mi))
            body = desc[: desc.rfind(last)].strip()
        else:
            tm = re.match(r"(\d{2})/(\d{2})/(\d{2}):", title)
            if not tm:
                continue
            start = dt.datetime(2000 + int(tm.group(3)), int(tm.group(1)), int(tm.group(2)))
            branch, body = "", desc
        name = re.sub(r"^\d{2}/\d{2}/\d{2}:\s*", "", title)
        if branch and name.endswith(" - " + branch):
            name = name[: -len(branch) - 3]
        out.append({"id": m.group(1), "start": start.isoformat(), "timed": bool(w),
                    "title": name.strip(), "branch": branch, "url": link.replace("http://", "https://"),
                    "desc": body if len(body) <= MAX_DESC else body[:MAX_DESC].rsplit(" ", 1)[0] + "…",
                    "category": category})
    return out


def collect():
    events, n_req = {}, 0
    for code, name in branches():
        try:
            items = parse_feed(http.get_text(f"{FEED}?location={code}")); n_req += 1
        except Exception as e:
            print(f"flp: {code}: {e}", file=sys.stderr)
            continue
        for it in items:
            events[(it["id"], it["start"][:10])] = it
        if len(items) >= FULL:  # busy branch: go deeper by category
            for cat in CATEGORIES:
                try:
                    for it in parse_feed(http.get_text(f"{FEED}?location={code}&type={cat}"), cat):
                        events.setdefault((it["id"], it["start"][:10]), it)
                    n_req += 1
                except Exception as e:
                    print(f"flp: {code}/type {cat}: {e}", file=sys.stderr)
    return events, n_req


def build_ics(history):
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//flp_to_ics//Free Library//EN",
           "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Free Library of Philadelphia",
           f"X-WR-TIMEZONE:{TZID}", "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]
    out += VTIMEZONE.split("\n")
    for key, e in sorted(history.items(), key=lambda kv: kv[1]["start"]):
        s = dt.datetime.fromisoformat(e["start"])
        uid = hashlib.sha1("|".join(key).encode()).hexdigest() + "@freelibrary.org"
        out += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{now}"]
        if e["timed"]:
            out += [f"DTSTART;TZID={TZID}:{s:%Y%m%dT%H%M%S}",
                    f"DTEND;TZID={TZID}:{s + dt.timedelta(minutes=DEFAULT_MIN):%Y%m%dT%H%M%S}"]
        else:
            out += [f"DTSTART;VALUE=DATE:{s:%Y%m%d}", f"DTEND;VALUE=DATE:{s + dt.timedelta(days=1):%Y%m%d}"]
        out.append(f"SUMMARY:{esc(e['title'])}")
        if e["branch"]:
            out.append(f"LOCATION:{esc(e['branch'])}")
        out.append(f"DESCRIPTION:{esc((e['desc'] + chr(10) + chr(10) + e['url']).strip())}")
        out.append(f"URL:{e['url']}")
        out.append("END:VEVENT")
    out.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in out) + "\r\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="flp.ics")
    ap.add_argument("--history", default="flp_history.json")
    ap.add_argument("--past-days", type=int, default=14)
    ap.add_argument("--min-hours", type=float, default=20, help="skip if the last run was more recent")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    state = {"last_run": None, "events": {}}
    if os.path.exists(a.history):
        with open(a.history) as f:
            state = json.load(f)
    last = state.get("last_run")
    if last and not a.force:
        age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(last)
        if age < dt.timedelta(hours=a.min_hours):
            print(f"flp: last run {age.total_seconds() / 3600:.1f}h ago; skipping (use --force)")
            return 0

    fresh, n_req = collect()
    hist = {tuple(k.split("|")): v for k, v in state.get("events", {}).items()}
    hist.update(fresh)
    cutoff = (dt.date.today() - dt.timedelta(days=a.past_days)).isoformat()
    hist = {k: v for k, v in hist.items() if v["start"][:10] >= cutoff}

    for p in (a.out, a.history):
        if os.path.dirname(p):
            os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(a.history, "w") as f:
        json.dump({"last_run": dt.datetime.now(dt.timezone.utc).isoformat(),
                   "events": {"|".join(k): v for k, v in hist.items()}}, f, indent=1, sort_keys=True)
    with open(a.out, "w", newline="") as f:
        f.write(build_ics(hist))
    timed = sum(1 for v in hist.values() if v["timed"])
    print(f"flp: {n_req} feed requests, {len(fresh)} events this run; {len(hist)} in calendar ({timed} with times)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
