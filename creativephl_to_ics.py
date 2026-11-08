#!/usr/bin/env python3
"""
creativephl_to_ics.py — turn CreativePHL's OACCE arts calendar into a subscribable .ics.

The site has no iCal feed, but the calendar page embeds every event (about two
years ahead) as a `calendarArgs` data block. This script downloads that page
once, reads the block, and writes a standard .ics file.

Usage:
    python3 creativephl_to_ics.py                        # writes creativephl.ics
    python3 creativephl_to_ics.py --out docs/creativephl.ics --past-days 30 --days-ahead 365

Shares its iCalendar helpers with pgc_to_ics.py (keep both files together).
No third-party packages are needed.
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import urllib.request

from pgc_to_ics import VTIMEZONE, TZID, esc, fold, clock_from_text, collapse_span

PAGE = "https://www.creativephl.org/oacce-calendar/"
UA = "Mozilla/5.0 (creativephl_to_ics; personal calendar subscription)"
DEFAULT_HOURS = 2
MAX_DESC = 500  # long descriptions bloat the file; the event link has the full text


def fetch_events():
    req = urllib.request.Request(PAGE, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        page = r.read().decode("utf-8", "replace")
    m = re.search(r"var calendarArgs\s*=\s*(\{.*?\});\s*\n", page, re.S)
    if not m:
        raise SystemExit("Couldn't find calendarArgs on the page — the site layout may have changed.")
    return json.loads(m.group(1))["events"]


def parse_dt(s):
    """'2026-10-27T18:00 America/New_York' or '2026-10-27' -> datetime (or None)."""
    s = (s or "").split(" ")[0]
    try:
        return dt.datetime.fromisoformat(s)
    except ValueError:
        return None


def text(s):
    s = re.sub(r"<br\s*/?>|</p>|</li>", "\n", s or "", flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s).strip()
    return s if len(s) <= MAX_DESC else s[:MAX_DESC].rsplit(" ", 1)[0] + "…"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="creativephl.ics")
    ap.add_argument("--past-days", type=int, default=30, help="keep events this many days back (default 30)")
    ap.add_argument("--days-ahead", type=int, default=180,
                    help="include events this many days ahead (default 180; big feeds sync poorly)")
    a = ap.parse_args()

    raw = fetch_events()
    cutoff = dt.datetime.combine(dt.date.today() - dt.timedelta(days=a.past_days), dt.time())
    horizon = dt.datetime.combine(dt.date.today() + dt.timedelta(days=a.days_ahead), dt.time())
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0",
           "PRODID:-//creativephl_to_ics//OACCE//EN",
           "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
           "X-WR-CALNAME:CreativePHL Arts Calendar",
           f"X-WR-TIMEZONE:{TZID}",
           "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
           "X-PUBLISHED-TTL:PT12H"]
    out += VTIMEZONE.split("\n")

    seen, n = set(), 0
    for e in sorted(raw, key=lambda x: x.get("start", "")):
        start = parse_dt(e.get("start"))
        if not start or start < cutoff or start > horizon:
            continue
        key = (e.get("id"), e.get("start"))
        if key in seen:
            continue
        seen.add(key)
        end = parse_dt(e.get("end"))
        all_day = bool(e.get("allDay"))
        url = (e.get("url") or "").split("?")[0]
        title = html.unescape(e.get("title") or "").strip()
        full_desc = text(e.get("eventDescription"))
        desc = (full_desc + "\n\n" + url).strip() if url else full_desc
        uid = hashlib.sha1(f"{e.get('id')}-{e.get('start')}".encode()).hexdigest() + "@creativephl.org"

        # The site marks many timed events "all day"; recover the time from the text.
        if all_day:
            found = clock_from_text(full_desc)
            if found:
                st, en = found
                start = dt.datetime.combine(start.date(), st)
                end = dt.datetime.combine(start.date(), en) if en else None
                if end and end <= start:
                    end += dt.timedelta(days=1)
                all_day = False

        through = None
        if not all_day:
            if not end or end <= start:
                end = start + dt.timedelta(hours=DEFAULT_HOURS)
            start, end, through = collapse_span(start, end, default_hours=DEFAULT_HOURS)
        else:
            s = start.date()
            last = end.date() if end and end.date() > s else s  # site's end date is the last day
            if last > s:
                through, last = last, s
        if through:
            title += f" (through {through:%b %-d})"

        out += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{now}"]
        if all_day:
            out += [f"DTSTART;VALUE=DATE:{s:%Y%m%d}",
                    f"DTEND;VALUE=DATE:{s + dt.timedelta(days=1):%Y%m%d}"]
        else:
            out += [f"DTSTART;TZID={TZID}:{start:%Y%m%dT%H%M%S}",
                    f"DTEND;TZID={TZID}:{end:%Y%m%dT%H%M%S}"]
        out.append(f"SUMMARY:{esc(title)}")
        if desc:
            out.append(f"DESCRIPTION:{esc(desc)}")
        if url:
            out.append(f"URL:{url}")
        out.append("END:VEVENT")
        n += 1
    out.append("END:VCALENDAR")

    if os.path.dirname(a.out):
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", newline="") as f:
        f.write("\r\n".join(fold(l) for l in out) + "\r\n")
    print(f"{len(raw)} occurrences on the site; {n} written to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
