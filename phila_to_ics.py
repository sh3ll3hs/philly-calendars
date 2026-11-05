#!/usr/bin/env python3
"""
phila_to_ics.py — merge the City of Philadelphia's department calendars into one .ics.

phila.gov/the-latest/all-events is a front end over ~115 public Google Calendars,
one per department or program (listed by https://api.phila.gov/phila/calendars/v1).
This script pulls that list, downloads each calendar's native Google iCal feed, and
merges the upcoming events into a single feed, each tagged with its department.

The city API blocks some networks. When it does, the script falls back to the
calendar list saved by the last successful run (--list file), so the feed keeps
working; the list is refreshed whenever the API is reachable again.

Usage:
    python3 phila_to_ics.py                       # writes phila.ics + phila_calendars.json
    python3 phila_to_ics.py --out docs/phila.ics --list docs/phila_calendars.json
    python3 phila_to_ics.py --past-days 14 --days-ahead 365

Shares its iCalendar helpers with pgc_to_ics.py (keep both files together).
No third-party packages are needed.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from pgc_to_ics import VTIMEZONE, esc, fold

API = "https://api.phila.gov/phila/calendars/v1"
UA = "Mozilla/5.0 (phila_to_ics; personal calendar subscription)"


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def flatten(items, parent=""):
    """The API nests sub-calendars inside a department entry; flatten to one list."""
    out = []
    for it in items:
        cal = it.get("calendar")
        title = (it.get("post_title") or parent or "City of Philadelphia").strip()
        if isinstance(cal, list):
            out += flatten(cal, title)
        elif isinstance(cal, str):
            cal = re.sub(r"[​\s]", "", cal)  # a few IDs contain zero-width spaces
            if "@" in cal:
                out.append({"title": title, "calendar": cal,
                            "slug": it.get("category_slug") or "", "url": it.get("url") or ""})
    return out


def load_calendars(list_path):
    try:
        cals = flatten(json.loads(get(API, timeout=30)))
        if cals:
            if os.path.dirname(list_path):
                os.makedirs(os.path.dirname(list_path), exist_ok=True)
            with open(list_path, "w") as f:
                json.dump(cals, f, indent=1)
            return cals, "live"
    except Exception as e:
        print(f"city API unavailable ({e}); using saved list", file=sys.stderr)
    with open(list_path) as f:
        return json.load(f), "saved"


def ics_url(cal_id):
    return ("https://calendar.google.com/calendar/ical/"
            + urllib.parse.quote(cal_id, safe="") + "/public/basic.ics")


def unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text.replace("\r\n", "\n"))


def event_date(block):
    m = re.search(r"^DTSTART[^:]*:(\d{8})", block, re.M)
    return dt.date(int(m.group(1)[:4]), int(m.group(1)[4:6]), int(m.group(1)[6:8])) if m else None


def fetch_events(cal, lo, hi):
    """Return (department, [vevent blocks]) for one calendar, filtered to the window."""
    try:
        text = unfold(get(ics_url(cal["calendar"])))
    except Exception:
        return cal, []
    blocks = re.findall(r"^BEGIN:VEVENT\n(.*?)^END:VEVENT", text, re.S | re.M)
    keep = []
    for b in blocks:
        if re.search(r"^STATUS:CANCELLED", b, re.M):
            continue
        d = event_date(b)
        if d is None:
            continue
        rrule = re.search(r"^RRULE:(.*)$", b, re.M)
        if not rrule:
            if not (lo <= d <= hi):
                continue
        else:
            if d > hi:
                continue
            until = re.search(r"UNTIL=(\d{8})", rrule.group(1))
            if until:  # series already over
                u = until.group(1)
                if dt.date(int(u[:4]), int(u[4:6]), int(u[6:8])) < lo:
                    continue
        keep.append(b)
    return cal, keep


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="phila.ics")
    ap.add_argument("--list", default="phila_calendars.json", help="saved department calendar list")
    ap.add_argument("--past-days", type=int, default=14)
    ap.add_argument("--days-ahead", type=int, default=365)
    a = ap.parse_args()

    cals, source = load_calendars(a.list)
    today = dt.date.today()
    lo, hi = today - dt.timedelta(days=a.past_days), today + dt.timedelta(days=a.days_ahead)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda c: fetch_events(c, lo, hi), cals))

    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0",
           "PRODID:-//phila_to_ics//City of Philadelphia events//EN",
           "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
           "X-WR-CALNAME:City of Philadelphia Events",
           "X-WR-TIMEZONE:America/New_York",
           "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
           "X-PUBLISHED-TTL:PT12H"]
    out += VTIMEZONE.split("\n")

    n, active, seen = 0, 0, set()
    for cal, blocks in results:
        if blocks:
            active += 1
        dept = cal["title"]
        for b in blocks:
            uid = re.search(r"^UID:(.*)$", b, re.M)
            key = (uid.group(1) if uid else b[:80], cal["calendar"])
            if key in seen:
                continue
            seen.add(key)
            lines = []
            for line in b.strip("\n").split("\n"):
                if line.startswith(("DTSTAMP", "CATEGORIES", "SEQUENCE", "CREATED", "LAST-MODIFIED")):
                    continue
                if line.startswith("DESCRIPTION:"):
                    line = f"DESCRIPTION:{esc(dept)}\\n\\n" + line[len("DESCRIPTION:"):]
                lines.append(line)
            if not any(l.startswith("DESCRIPTION:") for l in lines):
                lines.append(f"DESCRIPTION:{esc(dept)}")
            lines.append(f"CATEGORIES:{esc(dept)}")
            lines.append(f"DTSTAMP:{now}")
            out += ["BEGIN:VEVENT"] + lines + ["END:VEVENT"]
            n += 1
    out.append("END:VCALENDAR")

    if os.path.dirname(a.out):
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", newline="") as f:
        f.write("\r\n".join(fold(l) for l in out) + "\r\n")
    print(f"{len(cals)} department calendars ({source} list), {active} with upcoming events; "
          f"{n} events written to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
