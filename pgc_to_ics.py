#!/usr/bin/env python3
"""
pgc_to_ics.py — turn PhillyGayCalendar.com into a subscribable .ics feed.

The site has no iCal feed, but its calendar page loads events from a JSON
endpoint (/wp-json/pgc/v1/agenda) that always returns the next ~8 days.
Run this once a day: each run merges the new window into a small history file,
so events stay on your calendar after they pass and new ones appear as the
window rolls forward.

Usage:
    python3 pgc_to_ics.py                       # writes feed.ics + pgc_history.json here
    python3 pgc_to_ics.py --out docs/feed.ics --history docs/pgc_history.json
    python3 pgc_to_ics.py --keep-days 90        # how long past events stay (default 60)

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

AGENDA = "https://phillygaycalendar.com/wp-json/pgc/v1/agenda"
UA = "Mozilla/5.0 (pgc_to_ics; personal calendar subscription)"
TZID = "America/New_York"
DEFAULT_HOURS = 2  # length used when the site gives only a start time

VTIMEZONE = """BEGIN:VTIMEZONE
TZID:America/New_York
BEGIN:DAYLIGHT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
TZNAME:EDT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
TZNAME:EST
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
END:VTIMEZONE"""

TIME_RX = re.compile(r"(\d{1,2}):(\d{2})\s*([AP]M)", re.I)


def fetch_agenda():
    req = urllib.request.Request(AGENDA, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def to_24h(h, m, ampm):
    h = int(h) % 12 + (12 if ampm.upper() == "PM" else 0)
    return dt.time(h, int(m))


def parse_times(day, text):
    """Return (start, end, all_day) for a day and a string like '8:00 PM – 2:00 AM'."""
    found = TIME_RX.findall(text or "")
    if not found:
        return day, day + dt.timedelta(days=1), True
    start = dt.datetime.combine(day, to_24h(*found[0]))
    if len(found) > 1:
        end = dt.datetime.combine(day, to_24h(*found[1]))
        if end <= start:  # runs past midnight
            end += dt.timedelta(days=1)
    else:
        end = start + dt.timedelta(hours=DEFAULT_HOURS)
    return start, end, False


def clean(s):
    return html.unescape(s or "").strip()


def esc(s):
    """Escape text for an iCalendar property value."""
    return (s.replace("\\", "\\\\").replace(";", "\\;")
             .replace(",", "\\,").replace("\r", "").replace("\n", "\\n"))


def fold(line):
    """Fold long lines at 75 octets as RFC 5545 requires."""
    b = line.encode("utf-8")
    if len(b) <= 75:
        return line
    parts, cur = [], b""
    for ch in line:
        c = ch.encode("utf-8")
        if len(cur) + len(c) > (75 if not parts else 74):
            parts.append(cur.decode("utf-8"))
            cur = b""
        cur += c
    parts.append(cur.decode("utf-8"))
    return "\r\n ".join(parts)


LD_START = re.compile(r'"startDate"\s*:\s*"(\d{4}-\d{2}-\d{2}T(\d{2}):(\d{2}))')


def measure_shift(agenda, samples=5):
    """The agenda endpoint's clock times are off (as of Oct 2026 they read 4 h early,
    a timezone bug). Each event page carries correct schema.org startDate data, so
    compare a few events and return the most common difference in minutes.
    If the site fixes the bug this measures 0 and nothing is shifted."""
    diffs = []
    for day in agenda.get("days", []):
        for it in day.get("items", []):
            m = TIME_RX.search(it.get("time") or "")
            if not m or not it.get("permalink"):
                continue
            try:
                req = urllib.request.Request(it["permalink"], headers={"User-Agent": UA})
                page = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
            except Exception:
                continue
            ld = LD_START.search(page)
            if not ld:
                continue
            a = to_24h(*m.groups())
            d = (int(ld.group(2)) * 60 + int(ld.group(3))) - (a.hour * 60 + a.minute)
            diffs.append(d % (24 * 60))
            if len(diffs) >= samples:
                break
        if len(diffs) >= samples:
            break
    if not diffs:
        return 0
    best = max(set(diffs), key=diffs.count)
    return best - 24 * 60 if best > 12 * 60 else best


def collect(agenda, shift_min=0):
    events = {}
    shift = dt.timedelta(minutes=shift_min)
    for day in agenda.get("days", []):
        date = dt.datetime.strptime(day["date"], "%B %d, %Y").date()
        for it in day.get("items", []):
            start, end, all_day = parse_times(date, it.get("time"))
            if not all_day and shift:
                start, end = start + shift, end + shift
                date_key = start.date()
            else:
                date_key = date
            key = f"{it['id']}-{date_key.isoformat()}"
            events[key] = {
                "id": it["id"],
                "date": date_key.isoformat(),
                "title": clean(it.get("title")),
                "venue": clean(it.get("venue")),
                "address": clean(it.get("address")),
                "time": clean(it.get("time")),
                "cats": [clean(c) for c in it.get("cats") or []],
                "desc": clean(it.get("desc")),
                "performers": clean(it.get("performers")),
                "ticket": it.get("ticket") or "",
                "url": it.get("permalink") or "",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "all_day": all_day,
            }
    return events


def build_ics(events):
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0",
           "PRODID:-//pgc_to_ics//PhillyGayCalendar//EN",
           "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
           "X-WR-CALNAME:Philly Gay Calendar",
           f"X-WR-TIMEZONE:{TZID}",
           "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
           "X-PUBLISHED-TTL:PT6H"]
    out += VTIMEZONE.split("\n")
    for key, e in sorted(events.items(), key=lambda kv: kv[1]["start"]):
        uid = hashlib.sha1(key.encode()).hexdigest() + "@phillygaycalendar.com"
        loc = ", ".join(x for x in (e["venue"], e["address"]) if x)
        desc = []
        if e["performers"]:
            desc.append(f"With: {e['performers']}")
        if e["desc"]:
            desc.append(e["desc"])
        if e["cats"]:
            desc.append("Tags: " + ", ".join(e["cats"]))
        if e["ticket"]:
            desc.append(f"Tickets/info: {e['ticket']}")
        if e["url"]:
            desc.append(e["url"])
        out += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{now}"]
        if e["all_day"]:
            s = dt.date.fromisoformat(e["start"][:10])
            out += [f"DTSTART;VALUE=DATE:{s:%Y%m%d}",
                    f"DTEND;VALUE=DATE:{s + dt.timedelta(days=1):%Y%m%d}"]
        else:
            s, en = dt.datetime.fromisoformat(e["start"]), dt.datetime.fromisoformat(e["end"])
            out += [f"DTSTART;TZID={TZID}:{s:%Y%m%dT%H%M%S}",
                    f"DTEND;TZID={TZID}:{en:%Y%m%dT%H%M%S}"]
        out.append(f"SUMMARY:{esc(e['title'])}")
        if loc:
            out.append(f"LOCATION:{esc(loc)}")
        if desc:
            out.append(f"DESCRIPTION:{esc(chr(10).join(desc))}")
        if e["url"]:
            out.append(f"URL:{e['url']}")
        if e["cats"]:
            out.append(f"CATEGORIES:{','.join(esc(c) for c in e['cats'])}")
        out.append("END:VEVENT")
    out.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in out) + "\r\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="feed.ics")
    ap.add_argument("--history", default="pgc_history.json")
    ap.add_argument("--keep-days", type=int, default=60)
    a = ap.parse_args()

    history = {}
    if os.path.exists(a.history):
        with open(a.history) as f:
            history = json.load(f)

    agenda = fetch_agenda()
    shift = measure_shift(agenda)
    fresh = collect(agenda, shift)
    win_start = agenda.get("range", {}).get("start", "")
    win_end = agenda.get("range", {}).get("end", "")
    # Inside the live window the site is authoritative: drop anything it no longer lists
    # (cancelled or moved); outside the window keep what earlier runs saw.
    history = {k: v for k, v in history.items() if not (win_start <= v["date"] <= win_end)}
    history.update(fresh)
    cutoff = (dt.date.today() - dt.timedelta(days=a.keep_days)).isoformat()
    history = {k: v for k, v in history.items() if v["date"] >= cutoff}

    for path in (a.out, a.history):
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
    with open(a.history, "w") as f:
        json.dump(history, f, indent=1, sort_keys=True)
    with open(a.out, "w", newline="") as f:
        f.write(build_ics(history))
    print(f"{len(fresh)} events in window {win_start} to {win_end} "
          f"(time correction {shift:+d} min); {len(history)} total written to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
