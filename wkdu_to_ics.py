#!/usr/bin/env python3
"""
wkdu_to_ics.py — turn WKDU's "Philly Haps" concert listings into a subscribable .ics.

wkdu.org/phillyhaps/all is a plain HTML table (one table per day: show, time,
venue, age restriction) with no feed behind it. This script reads that page,
looks up each venue's street address once (cached in a small JSON file), and
writes a standard .ics file.

Usage:
    python3 wkdu_to_ics.py                                   # writes wkdu.ics
    python3 wkdu_to_ics.py --out docs/wkdu.ics --venues docs/wkdu_venues.json

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

from pgc_to_ics import VTIMEZONE, TZID, esc, fold

LIST_URL = "https://wkdu.org/phillyhaps/all"
SITE = "https://wkdu.org"
UA = "Mozilla/5.0 (wkdu_to_ics; personal calendar subscription)"
DEFAULT_HOURS = 3

DAY_TABLE = re.compile(
    r'<caption><span class="date-display-single">([^<]*)</span></caption>(.*?)</table>', re.S)
ROW = re.compile(r'<tr class="(?:odd|even)">(.*?)</tr>', re.S)
TITLE = re.compile(r'views-field-title-1"[^>]*>\s*<a href="([^"]+)">(.*?)</a>', re.S)
TIME = re.compile(r'views-field-field-time-value"[^>]*>.*?<span[^>]*>([^<]*)</span>', re.S)
VENUE = re.compile(r'views-field-field-venue-nid"[^>]*>\s*<a href="(/venue/\d+)">(.*?)</a>', re.S)
AGE = re.compile(r'views-field-field-age-restriction-value"[^>]*>(.*?)</td>', re.S)
TIME_RX = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)", re.I)


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def text(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def parse_day(label):
    label = label.replace("Sept", "Sep")
    for fmt in ("%A, %b %d, %Y", "%A, %B %d, %Y"):
        try:
            return dt.datetime.strptime(label.strip(), fmt).date()
        except ValueError:
            pass
    return None


def parse_time(s):
    m = TIME_RX.search(s or "")
    if not m:
        return None
    h = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "pm" else 0)
    return dt.time(h, int(m.group(2) or 0))


def venue_address(path, cache):
    """Street address for a /venue/NNN page, cached so each venue is fetched once."""
    if path in cache:
        return cache[path]
    addr = ""
    try:
        page = get(SITE + path, timeout=30)
        parts = []
        for cls in ("street-address", "locality", "region", "postal-code"):
            m = re.search(r'class="%s"[^>]*>(.*?)</' % cls, page, re.S)
            if m and text(m.group(1)):
                parts.append(text(m.group(1)))
        if parts:
            addr = parts[0] + (", " + " ".join(parts[1:]) if len(parts) > 1 else "")
    except Exception:
        pass
    cache[path] = addr
    return addr


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="wkdu.ics")
    ap.add_argument("--venues", default="wkdu_venues.json", help="venue address cache file")
    a = ap.parse_args()

    cache = {}
    if os.path.exists(a.venues):
        with open(a.venues) as f:
            cache = json.load(f)

    page = get(LIST_URL)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0",
           "PRODID:-//wkdu_to_ics//Philly Haps//EN",
           "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
           "X-WR-CALNAME:WKDU Philly Haps",
           f"X-WR-TIMEZONE:{TZID}",
           "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
           "X-PUBLISHED-TTL:PT12H"]
    out += VTIMEZONE.split("\n")

    n = 0
    for day_label, body in DAY_TABLE.findall(page):
        day = parse_day(day_label)
        if not day:
            continue
        for row in ROW.findall(body):
            t = TITLE.search(row)
            if not t:
                continue
            path, title = t.group(1), text(t.group(2))
            tm = TIME.search(row)
            start_t = parse_time(tm.group(1)) if tm else None
            v = VENUE.search(row)
            venue = text(v.group(2)) if v else ""
            addr = venue_address(v.group(1), cache) if v else ""
            ag = AGE.search(row)
            age = text(ag.group(1)) if ag else ""
            url = SITE + path
            uid = hashlib.sha1(f"{path}-{day.isoformat()}".encode()).hexdigest() + "@wkdu.org"

            out += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{now}"]
            if start_t:
                s = dt.datetime.combine(day, start_t)
                e = s + dt.timedelta(hours=DEFAULT_HOURS)
                out += [f"DTSTART;TZID={TZID}:{s:%Y%m%dT%H%M%S}",
                        f"DTEND;TZID={TZID}:{e:%Y%m%dT%H%M%S}"]
            else:
                out += [f"DTSTART;VALUE=DATE:{day:%Y%m%d}",
                        f"DTEND;VALUE=DATE:{day + dt.timedelta(days=1):%Y%m%d}"]
            out.append(f"SUMMARY:{esc(title)}")
            loc = ", ".join(x for x in (venue, addr) if x)
            if loc:
                out.append(f"LOCATION:{esc(loc)}")
            desc = "\n".join(x for x in (f"Venue: {venue}" if venue else "",
                                         f"Ages: {age}" if age else "", url) if x)
            out.append(f"DESCRIPTION:{esc(desc)}")
            out.append(f"URL:{url}")
            out.append("END:VEVENT")
            n += 1
    out.append("END:VCALENDAR")

    for path in (a.out, a.venues):
        if os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(a.venues, "w") as f:
        json.dump(cache, f, indent=1, sort_keys=True)
    with open(a.out, "w", newline="") as f:
        f.write("\r\n".join(fold(l) for l in out) + "\r\n")
    print(f"{n} shows written to {a.out} ({len(cache)} venues cached)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
