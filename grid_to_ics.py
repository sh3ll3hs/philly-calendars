#!/usr/bin/env python3
"""
grid_to_ics.py — Grid Magazine's Philadelphia events calendar as a full .ics.

gridphilly.com publishes a native iCal export (/events/?ical=1) but it is capped
at 30 events. The site's Events Calendar REST API has all of them with real
start and end times, so this script pages through that instead. Multi-week
courses and exhibitions are shown on their opening day only, with
"(through <date>)" added to the title, so they don't sit across the top of
every day on the calendar.

Usage:
    python3 grid_to_ics.py                      # writes grid.ics
    python3 grid_to_ics.py --out docs/grid.ics --days-ahead 365

Shares its iCalendar helpers with pgc_to_ics.py (keep both files together).
No third-party packages are needed.
"""
import argparse
import collections
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request

from pgc_to_ics import VTIMEZONE, TZID, esc, fold, collapse_span

API = "https://gridphilly.com/wp-json/tribe/events/v1/events"
UA = "Mozilla/5.0 (grid_to_ics; personal calendar subscription)"
DEFAULT_HOURS = 2
MAX_DESC = 500
DAILY_MIN = 10  # a title with this many occurrences is a daily run (festival, market, light show)


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def fetch_all(start, end):
    events, page = [], 1
    while True:
        q = urllib.parse.urlencode({"per_page": 50, "page": page, "start_date": start, "end_date": end})
        try:
            d = get_json(f"{API}?{q}")
        except urllib.error.HTTPError as e:
            if e.code == 400 and page > 1:
                break
            raise
        events += d.get("events", [])
        if page >= int(d.get("total_pages") or 1):
            break
        page += 1
    return events


def text(s):
    s = re.sub(r"<br\s*/?>|</p>|</li>", "\n", s or "", flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    s = re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", s)).strip()
    return s if len(s) <= MAX_DESC else s[:MAX_DESC].rsplit(" ", 1)[0] + "…"


def parse(s):
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="grid.ics")
    ap.add_argument("--past-days", type=int, default=14)
    ap.add_argument("--days-ahead", type=int, default=365)
    a = ap.parse_args()

    today = dt.date.today()
    raw = fetch_all((today - dt.timedelta(days=a.past_days)).isoformat(),
                    (today + dt.timedelta(days=a.days_ahead)).isoformat())
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0",
           "PRODID:-//grid_to_ics//Grid Magazine events//EN",
           "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
           "X-WR-CALNAME:Grid Magazine Events",
           f"X-WR-TIMEZONE:{TZID}",
           "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
           "X-PUBLISHED-TTL:PT12H"]
    out += VTIMEZONE.split("\n")

    # Recurring series come back as one entry per occurrence, each carrying the
    # whole series' end date. Group by title so we can treat them sensibly:
    # a daily series (10+ occurrences) becomes one entry on its opening day;
    # a weekly class keeps every occurrence but as a single-day event.
    raw = sorted({e["id"]: e for e in raw}.values(), key=lambda e: e["start_date"])
    by_title = collections.defaultdict(list)
    for e in raw:
        by_title[html.unescape(e.get("title") or "").strip()].append(e)

    n = 0
    for e in raw:
        start, end = parse(e["start_date"]), parse(e["end_date"])
        title = html.unescape(e.get("title") or "").strip()
        series = by_title[title]
        v = e.get("venue") or {}
        venue = html.unescape(", ".join(x for x in (v.get("venue"), v.get("address"), v.get("city")) if x))
        url = e.get("url") or ""
        cats = [c["name"] for c in e.get("categories", [])]
        desc = "\n\n".join(x for x in (text(e.get("description")), url) if x)
        uid = hashlib.sha1(f"grid-{e['id']}".encode()).hexdigest() + "@gridphilly.com"

        if len(series) >= DAILY_MIN:
            dates = sorted({parse(x["start_date"]).date() for x in series})
            gaps = sorted((b - a).days for a, b in zip(dates, dates[1:]))
            daily = gaps[len(gaps) // 2] <= 2  # median gap: 1 = nightly run, 7 = weekly class
        else:
            daily = False
        if daily:
            if e is not series[0]:
                continue  # only the opening occurrence
            last = parse(series[-1]["start_date"]).date()
            title += f" (daily through {last:%b %-d})"
            through = None
        elif len(series) > 1:
            through = None  # weekly class: each occurrence is just that day
        else:
            through = "auto"

        out += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{now}"]
        if e.get("all_day"):
            s = start.date()
            if through == "auto" and end.date() > s:
                title += f" (through {end.date():%b %-d})"
            out += [f"DTSTART;VALUE=DATE:{s:%Y%m%d}",
                    f"DTEND;VALUE=DATE:{s + dt.timedelta(days=1):%Y%m%d}"]
        else:
            if end <= start:
                end = start + dt.timedelta(hours=DEFAULT_HOURS)
            start, end, span_through = collapse_span(start, end, default_hours=DEFAULT_HOURS)
            if through == "auto" and span_through:
                title += f" (through {span_through:%b %-d})"
            out += [f"DTSTART;TZID={TZID}:{start:%Y%m%dT%H%M%S}",
                    f"DTEND;TZID={TZID}:{end:%Y%m%dT%H%M%S}"]
        out.append(f"SUMMARY:{esc(title)}")
        if venue:
            out.append(f"LOCATION:{esc(venue)}")
        if desc:
            out.append(f"DESCRIPTION:{esc(desc)}")
        if url:
            out.append(f"URL:{url}")
        if cats:
            out.append(f"CATEGORIES:{','.join(esc(c) for c in cats)}")
        out.append("END:VEVENT")
        n += 1
    out.append("END:VCALENDAR")

    if os.path.dirname(a.out):
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", newline="") as f:
        f.write("\r\n".join(fold(l) for l in out) + "\r\n")
    print(f"{len(raw)} events from Grid; {n} written to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
