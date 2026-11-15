#!/usr/bin/env python3
"""
tribe_to_ics.py — full .ics feeds for sites running The Events Calendar (WordPress).

These sites publish a native iCal export (/events/?ical=1) but it is capped at
30 events. Their REST API (/wp-json/tribe/events/v1/events) has every event with
real start/end times, venue and links, so this script pages through that.

Built-in sites:
    grid          Grid Magazine (Philadelphia)            -> grid.ics
    delcoarts     Delaware County Arts Consortium         -> delcoarts.ics
    countylines   County Lines Magazine (Delco/Chesco/Main Line) -> countylines.ics
    phillyfamily  Philly Family                           -> phillyfamily.ics

Usage:
    python3 tribe_to_ics.py delcoarts --out docs/delcoarts.ics
    python3 tribe_to_ics.py grid --out docs/grid.ics --days-ahead 365

Each event carries:
    LOCATION     "Venue, street, city, ST zip" (whatever parts the site has)
    URL          the organizer's own event/ticket page when the site lists one,
                 otherwise the event's page on the calendar site
    DESCRIPTION  summary text, then "Event website: <organizer's link>" and
                 "Listing: <calendar-site page>"

Nightly/daily runs (markets, light shows, exhibitions listed every day) become
one entry on the opening day, titled "(daily through <date>)"; weekly classes
keep every date. Multi-day single events show on their first day as
"(through <date>)" so they don't sit across the top of every day.

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
import urllib.error
import urllib.parse
import urllib.request

from pgc_to_ics import VTIMEZONE, TZID, esc, fold, collapse_span

SITES = {
    "grid": ("https://gridphilly.com", "Grid Magazine Events"),
    "delcoarts": ("https://www.delcoarts.org", "Delco Arts Events"),
    "countylines": ("https://countylinesmagazine.com", "County Lines Magazine Events"),
    "phillyfamily": ("https://phillyfamily.com", "Philly Family Events"),
}
UA = "Mozilla/5.0 (tribe_to_ics; personal calendar subscription)"
DEFAULT_HOURS = 2
MAX_DESC = 500
DAILY_MIN = 10  # a title with this many occurrences may be a daily run (festival, market, light show)


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def fetch_all(base, start, end):
    events, page = [], 1
    while True:
        q = urllib.parse.urlencode({"per_page": 50, "page": page, "start_date": start, "end_date": end})
        try:
            d = get_json(f"{base}/wp-json/tribe/events/v1/events?{q}")
        except urllib.error.HTTPError as e:
            if e.code in (400, 404) and page > 1:
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


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(str(s or ""))).strip(" ,")


def location(venue):
    """'Venue, street, city, ST zip' from whatever parts the site provides."""
    if not isinstance(venue, dict):
        return ""
    name, street, city = clean(venue.get("venue")), clean(venue.get("address")), clean(venue.get("city"))
    state = clean(venue.get("state") or venue.get("stateprovince") or venue.get("province"))
    zipc = clean(venue.get("zip"))
    if not state and re.match(r"^\d{5}", zipc):   # fill a missing state from the ZIP
        z = int(zipc[:3])
        state = "PA" if 150 <= z <= 196 else "DE" if 197 <= z <= 199 else "NJ" if 70 <= z <= 89 else ""
    tail = " ".join(x for x in (state, zipc) if x)
    # Sites often repeat themselves: the street typed into the venue-name field,
    # "Suite 109" twice, the city inside the street line. Split everything on
    # commas and keep each piece once ("5150 Warren St" == "5150 Warren Street").
    parts, seen = [], []
    for piece in [p for chunk in (name, street, city, tail) for p in chunk.split(",")]:
        piece = piece.strip()
        key = _norm(piece)
        if not key or any(key == s or key in s for s in seen):
            continue
        seen.append(key)
        parts.append(piece)
    return ", ".join(parts)


_ABBR = {"street": "st", "avenue": "ave", "road": "rd", "drive": "dr", "boulevard": "blvd", "lane": "ln",
         "north": "n", "south": "s", "east": "e", "west": "w", "pennsylvania": "pa", "new jersey": "nj",
         "delaware": "de"}


def _norm(s):
    s = re.sub(r"[^\w ]+", "", s.lower())
    return " ".join(_ABBR.get(w, w) for w in s.split())


def good_url(u):
    u = html.unescape(u or "").strip()   # sites store "&amp;" in links
    if u and not re.match(r"^https?://", u, re.I):
        u = "https://" + u.lstrip("/") if re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", u, re.I) else ""
    return u if re.match(r"^https?://[^\s/]+\.[^\s/]+", u, re.I) else ""


def build(site, base, calname, raw):
    host = urllib.parse.urlsplit(base).netloc.removeprefix("www.")
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0",
           f"PRODID:-//tribe_to_ics//{calname}//EN",
           "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
           f"X-WR-CALNAME:{calname}",
           f"X-WR-TIMEZONE:{TZID}",
           "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
           "X-PUBLISHED-TTL:PT12H"]
    out += VTIMEZONE.split("\n")

    raw = sorted({e["id"]: e for e in raw}.values(), key=lambda e: e["start_date"])
    by_title = collections.defaultdict(list)
    for e in raw:
        by_title[clean(e.get("title"))].append(e)

    n = 0
    for e in raw:
        start, end = parse(e["start_date"]), parse(e["end_date"])
        title = clean(e.get("title"))
        series = by_title[title]
        loc = location(e.get("venue"))
        listing = good_url(e.get("url"))          # the page on the calendar site
        site_link = good_url(e.get("website"))    # the organizer's own page / tickets
        url = site_link or listing                # what the calendar app's link button opens
        cats = [clean(c["name"]) for c in e.get("categories", [])]
        desc = "\n\n".join(x for x in (
            text(e.get("description")),
            f"Event website: {site_link}" if site_link else "",
            f"Listing: {listing}" if listing and listing != site_link else "") if x)
        uid = hashlib.sha1(f"{site}-{e['id']}".encode()).hexdigest() + "@" + host

        if len(series) >= DAILY_MIN:
            dates = sorted({parse(x["start_date"]).date() for x in series})
            gaps = sorted((b - a).days for a, b in zip(dates, dates[1:]))
            daily = bool(gaps) and gaps[len(gaps) // 2] <= 2  # median gap: 1 = nightly run, 7 = weekly class
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
        if loc:
            out.append(f"LOCATION:{esc(loc)}")
        if desc:
            out.append(f"DESCRIPTION:{esc(desc)}")
        if url:
            out.append(f"URL:{url}")
        if cats:
            out.append(f"CATEGORIES:{','.join(esc(c) for c in cats)}")
        out.append("END:VEVENT")
        n += 1
    out.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in out) + "\r\n", n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site", choices=sorted(SITES))
    ap.add_argument("--out", default=None)
    ap.add_argument("--past-days", type=int, default=14)
    ap.add_argument("--days-ahead", type=int, default=365)
    a = ap.parse_args(argv)
    base, calname = SITES[a.site]
    out_path = a.out or f"{a.site}.ics"

    today = dt.date.today()
    raw = fetch_all(base, (today - dt.timedelta(days=a.past_days)).isoformat(),
                    (today + dt.timedelta(days=a.days_ahead)).isoformat())
    if not raw:
        print(f"{a.site}: the site returned no events; keeping the existing feed", file=sys.stderr)
        return 1
    ics, n = build(a.site, base, calname, raw)
    if os.path.dirname(out_path):
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="") as f:
        f.write(ics)
    print(f"{a.site}: {len(raw)} events from the site; {n} written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
