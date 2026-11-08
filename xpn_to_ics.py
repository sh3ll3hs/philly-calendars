#!/usr/bin/env python3
"""
xpn_to_ics.py — turn WXPN's concert calendar into a subscribable .ics.

xpn.org's own iCal export (/concert-and-events/?ical=1) stops at 30 events.
The site's Events Calendar REST API has all of them (hundreds, months ahead),
so this script pages through that and writes one all-day event per show.
XPN lists dates but not show times. Rather than all-day events (which pile up
in the all-day band), each show gets a placeholder evening slot (default
8:00-11:00 PM) and a note to check the ticket link for the real time.

Usage:
    python3 xpn_to_ics.py                                  # all regions -> xpn.ics
    python3 xpn_to_ics.py --regions "Philadelphia Area"    # just Philly shows
    python3 xpn_to_ics.py --out docs/xpn.ics --days-ahead 180
    python3 xpn_to_ics.py --all-day                        # old behaviour
    python3 xpn_to_ics.py --start 19:30 --hours 3

Shares its iCalendar helpers with pgc_to_ics.py (keep both files together).
No third-party packages are needed.
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import re
import os
import sys
import urllib.parse
import urllib.request

from pgc_to_ics import VTIMEZONE, TZID, esc, fold

API = "https://xpn.org/wp-json/tribe/events/v1/events"
UA = "Mozilla/5.0 (xpn_to_ics; personal calendar subscription)"
REGIONS = {"Philadelphia Area", "New Jersey", "Delaware", "Lehigh Valley",
           "Central PA", "Poconos", "Jersey Shore"}


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def fetch_all(start, end):
    events, page = [], 1
    while True:
        q = urllib.parse.urlencode({"per_page": 50, "page": page,
                                    "start_date": start, "end_date": end})
        try:
            d = get_json(f"{API}?{q}")
        except urllib.error.HTTPError as e:
            if e.code == 400 and page > 1:  # past the last page
                break
            raise
        events += d.get("events", [])
        if page >= int(d.get("total_pages") or 1):
            break
        page += 1
    return events


def text(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="xpn.ics")
    ap.add_argument("--days-ahead", type=int, default=365)
    ap.add_argument("--regions", default="",
                    help='comma-separated regions to keep, e.g. "Philadelphia Area,New Jersey" (default: all)')
    ap.add_argument("--all-day", action="store_true", help="write all-day events instead of a placeholder slot")
    ap.add_argument("--start", default="20:00", help="placeholder start time, HH:MM (default 20:00)")
    ap.add_argument("--hours", type=float, default=3, help="placeholder length in hours (default 3)")
    a = ap.parse_args()
    keep = {r.strip() for r in a.regions.split(",") if r.strip()}
    slot = dt.time(*map(int, a.start.split(":")))

    today = dt.date.today()
    raw = fetch_all(today.isoformat(), (today + dt.timedelta(days=a.days_ahead)).isoformat())
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0",
           "PRODID:-//xpn_to_ics//WXPN Concerts//EN",
           "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
           "X-WR-CALNAME:WXPN Concert Calendar",
           "X-WR-TIMEZONE:America/New_York",
           "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
           "X-PUBLISHED-TTL:PT12H"]
    if not a.all_day:
        out += VTIMEZONE.split("\n")

    n, seen = 0, set()
    for e in raw:
        cats = [c["name"] for c in e.get("categories", [])]
        region = next((c for c in cats if c in REGIONS), "")
        if keep and region not in keep:
            continue
        if e["id"] in seen:
            continue
        seen.add(e["id"])
        start = dt.date.fromisoformat(e["start_date"][:10])
        end = dt.date.fromisoformat(e["end_date"][:10])
        title = text(e.get("title"))
        venue = text((e.get("venue") or {}).get("venue"))
        url = e.get("url") or ""
        tickets = e.get("website") or ""
        extras = [c for c in cats if c not in REGIONS]  # e.g. "WXPN Welcomes", "Free At Noon"
        desc = "\n".join(x for x in (
            "" if a.all_day else "Show time not listed by XPN - check the ticket link.",
            f"Venue: {venue}" if venue else "",
            f"Region: {region}" if region else "",
            ", ".join(extras),
            f"Tickets: {tickets}" if tickets else "",
            url) if x)
        uid = hashlib.sha1(f"xpn-{e['id']}".encode()).hexdigest() + "@xpn.org"
        out += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{now}"]
        if a.all_day:
            out += [f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
                    f"DTEND;VALUE=DATE:{end + dt.timedelta(days=1):%Y%m%d}"]
        else:
            s = dt.datetime.combine(start, slot)
            en = s + dt.timedelta(hours=a.hours)
            out += [f"DTSTART;TZID={TZID}:{s:%Y%m%dT%H%M%S}",
                    f"DTEND;TZID={TZID}:{en:%Y%m%dT%H%M%S}"]
        out.append(f"SUMMARY:{esc(title)}")
        if venue:
            out.append(f"LOCATION:{esc(venue)}")
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
    print(f"{len(raw)} shows from XPN; {n} written to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
