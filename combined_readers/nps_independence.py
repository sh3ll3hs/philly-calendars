"""
National Park Service, Philadelphia units (Independence NHP and its neighbours) — events reader.

Human page: https://www.nps.gov/inde/planyourvisit/calendar.htm  (an empty <div id="nps-calendar">
filled in by /theme/assets/vendor/nps-calendar/nps-calendar.js).

Source read here: the public JSON service that script calls, no key and no login:
    https://home.nps.gov/common/components/nps/eventcalendar/EventCalendarService.cfc
        ?method=getEvents&dateStart=YYYY-MM-DD&dateEnd=YYYY-MM-DD&expandRecurring=false
        &pageSize=50&pageNumber=1&parkCode=inde,edal,thko,glde
One request per run covers the whole window: with expandRecurring=false every event (or every
stretch of a repeating event) is one row whose `dates` lists each day it happens inside the
window and whose `times` lists the day's start/end clock times ("12:00 PM"). robots.txt on
www.nps.gov and home.nps.gov only disallows /ns/, /search/ and loader.cfm.
(The keyed API at developer.nps.gov/api/v1/events?parkCode=inde is the same data; not needed.)

What one row becomes: one calendar entry per day in `dates`, at the day's FIRST listed time
(start and end as published). When a day has more sessions ("12:00 PM, 1:00 PM, 2:00 PM,
3:00 PM", 30 minutes each) the later ones are named at the top of the description
("Also at 1:00 PM, 2:00 PM and 3:00 PM.") instead of becoming four entries a day.

Checked on 2026-11-15 against the site's own event pages
(https://www.nps.gov/planyourvisit/event-details.htm?id=...): "First Bank of the US Guided
Ranger Talk" reads "Every day at 12:00 PM, 1:00 PM, 2:00 PM, and 3:00 PM from November 01,
2026 to November 25, 2026 ... Duration: 30 minutes ... Location 120 S 3rd Street", which is
what the service returns. Times are local wall-clock strings, so there is no time-zone step.

Known failure modes:
  * `isAllDay`, a sunrise/sunset slot, or a row with no readable clock time gives an all-day
    entry (never a guessed time).
  * Dates named in `cancelledDateList` are skipped; the field was empty in every row seen, so
    its exact format (list or comma-separated text) is handled both ways but untested live.
  * `location` is free text ("120 S 3rd Street"). The park's name and the entry's `city` are
    appended unless the text already names a city/state; a wrong `city` in the entry would
    be repeated on every event.
  * A daily programme with ten or more days in the window is folded by the feed into one
    "(daily through ...)" entry, like every other source.
  * The service is undocumented: if NPS renames it the reader raises and the source reports
    an error (the keyed developer.nps.gov API would be the replacement).
"""
import datetime as dt
import json
import re
import urllib.parse

import combined_to_ics as C

API = "https://home.nps.gov/common/components/nps/eventcalendar/EventCalendarService.cfc"
DETAIL = "https://www.nps.gov/planyourvisit/event-details.htm?id="
PAGE_SIZE = 50
MAX_PAGES = 4
CLOCK_RX = re.compile(r"^\s*0?(\d{1,2}):(\d{2})\s*([AP])\.?M\.?\s*$", re.I)
PLACE_RX = re.compile(r"\b(Philadelphia|[A-Z]{2}\s+\d{5})\b|,\s*[A-Z]{2}\b")


def _clock(s):
    m = CLOCK_RX.match(str(s or ""))
    if not m:
        return None
    h, minute = int(m.group(1)), int(m.group(2))
    if not (1 <= h <= 12 and minute < 60):
        return None
    return dt.time(h % 12 + (12 if m.group(3).upper() == "P" else 0), minute)


def _label(t):
    """dt.time -> '1:00 PM' (how the site writes it, without the leading zero)."""
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def _slots(row):
    """[(start, end or None)] for the row's readable clock times, in the site's order."""
    out = []
    for t in row.get("times") or []:
        if not isinstance(t, dict) or t.get("sunriseStart"):
            continue
        st = _clock(t.get("timeStart"))
        if st:
            out.append((st, None if t.get("sunsetEnd") else _clock(t.get("timeEnd"))))
    return out


def _location(row, src):
    loc = C.clean(re.sub(r"^\s*event location\s*:\s*", "", str(row.get("location") or ""), flags=re.I))
    park = C.clean(row.get("parkFullName"))
    if loc and PLACE_RX.search(loc):
        return loc                                   # already a full address
    parts = [loc] if loc else []
    if park and park.lower() not in loc.lower():
        parts.append(park)
    if src.get("city"):
        parts.append(src["city"])
    return ", ".join(parts)


def _cancelled(row):
    c = row.get("cancelledDateList")
    if isinstance(c, list):
        return {str(x)[:10] for x in c}
    return set(re.findall(r"\d{4}-\d{2}-\d{2}", str(c or "")))


def _join(words):
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def parse(body, src):
    """The service's JSON (text or already-decoded dict) -> events."""
    data = json.loads(body) if isinstance(body, (str, bytes)) else body
    out, seen = [], set()
    for row in data.get("data") or []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        slots = [] if row.get("isAllDay") else _slots(row)
        off = _cancelled(row)
        loc = _location(row, src)
        url = DETAIL + urllib.parse.quote(str(row["id"]))
        notes = []
        if len(slots) > 1:
            notes.append("Also at " + _join([_label(s) for s, _ in slots[1:]]) + ".")
        fee = C.clean(C.text(row.get("feeInfo")))
        if fee:
            notes.append(fee)
        elif row.get("isFree"):
            notes.append("Free.")
        desc = "\n\n".join(x for x in (" ".join(notes), C.text(row.get("description"))) if x)
        for d in row.get("dates") or [row.get("date")]:
            m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(d or ""))
            if not m or m.group(0) in off or (row["id"], m.group(0)) in seen:
                continue
            seen.add((row["id"], m.group(0)))
            day = dt.date(*map(int, m.groups()))
            key = f"{row['id']}|{day.isoformat()}"
            if slots:
                st = dt.datetime.combine(day, slots[0][0])
                en = dt.datetime.combine(day, slots[0][1]) if slots[0][1] else None
                if en and en <= st:
                    en += dt.timedelta(days=1)
                e = C.event(src, key, row.get("title"), st, en, False, loc, url, desc)
            else:
                e = C.event(src, key, row.get("title"), day, None, True, loc, url, desc)
            if e:
                out.append(e)
    return out


def read(src, ctx):
    out, page = [], 1
    while page <= MAX_PAGES:
        q = {"method": "getEvents", "dateStart": ctx["lo"].isoformat(), "dateEnd": ctx["hi"].isoformat(),
             "expandRecurring": "false", "pageSize": PAGE_SIZE, "pageNumber": page,
             "parkCode": src.get("parks") or "inde"}
        data = C.get_json(src.get("api", API) + "?" + urllib.parse.urlencode(q, safe=","))
        if data.get("errors"):
            raise RuntimeError(f"NPS event service: {str(data['errors'])[:120]}")
        out += parse(data, src)
        if page * PAGE_SIZE >= int(data.get("total") or 0):
            break
        page += 1
    return out
