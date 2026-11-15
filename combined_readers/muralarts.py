"""
Mural Arts Philadelphia — events reader (dedications, paint days, talks, open houses).

Source: https://muralarts.org/events/  (WordPress, custom theme; no Events Calendar plugin,
no feed, no schema.org Event data; the built-in `text` method reads nothing from it).

Listing (one request per run): the page carries the data its own calendar view is drawn
from, as inline JSON:
    window.events = [{"id":27629,"title":"Philadelphia Stars Community Paint Day",
                      "start":"11\\/17\\/2026","end":"11\\/17\\/2026","time":"6:00 pm","url":"https://muralarts.org/events/.../"}, ...]
That gives the title, the day(s), the start time and the event page, but no end time and
no place.

Event pages (at most 12 new ones per run, cached for a week in ctx["detail"]): the place
("Address /" block), the cost, the first lines of the description and the site's own
"Add to Calendar" Google link, which states start and end as Eastern wall time:
    ...&dates=20261117T180000%2F20261117T200000&...&ctz=America%2FNew_York     (timed)
    ...&dates=20261114%2F20261116&...                                          (all day, end exclusive)
robots.txt allows everything but asks for `Crawl-delay: 10`, so the reader waits before
each event page (a first run with 11 events takes about two minutes; later runs open only
new or changed events).

Checked on 2026-11-15 against what the pages show a visitor: Philadelphia Stars Community
Paint Day ("November 17, 2026 / 6:00 PM - 8:00 PM", 1101 N 38th St), Restorative Justice
Month at City Hall ("November 19, 2026 / 10:00 AM - 3:00 PM", Philadelphia City Hall),
Eco-Social Realism Open House at TILT ("November 14, 2026", no time: all-day) and Tacony
Lab's Third Annual KNIT-A-THON ("November 14 - 15, 2026", no time: all-day, two days).
In each case the calendar link agrees with the visible text.

Known failure modes:
  * A multi-day event has a "time" in the listing data (KNIT-A-THON: "12:00 pm") that the
    event page does not show; the page wins, so such an event is all-day over its days.
    Without the event page it is all-day too (the listing time is not used for a range).
  * Without its event page (page budget used up, or the page failed) a one-day event has
    its start time from the listing, no end time and no location until a later run.
  * A cached event page is dropped as soon as the listing shows another day or start time
    for that event (rescheduled); otherwise place and end time can be up to a week old.
  * Addresses are passed on as written; many have no city ("1441 Sansom Street",
    "2024 Reed Street 19146"). With `"city": "Philadelphia, PA"` in the source entry that
    text is appended to an address that names neither Philadelphia nor a state, which
    would be wrong for an event held outside the city under a bare street address.
  * If `window.events` disappears from the listing the reader returns nothing.
"""
import datetime as dt
import html
import json
import re
import time
import urllib.parse
from zoneinfo import ZoneInfo

import combined_to_ics as C

MAX_NEW_PAGES = 12
TTL_DAYS = 7
CRAWL_DELAY = 10          # seconds between requests, from the site's robots.txt
GCAL_RX = re.compile(r'href="(https://calendar\.google\.com/calendar/render\?[^"]+)"')
CITY_RX = re.compile(r"philadelphia|\bonline\b|\bvirtual\b|\bzoom\b", re.I)
STATE_RX = re.compile(r",\s*[A-Z]{2}\b(?:,|\s+\d{5}|\s*$)")           # ", PA", ", NJ 08102", ", PA, USA"
BLOCK_RX = re.compile(r'<div class="type-tag-sans\s*">\s*%s\s*/\s*</div>\s*<div class="type-display-sm">(.*?)</div>', re.S)


def _items(body):
    """The inline `window.events = [...]` list, or []."""
    m = re.search(r"window\.events\s*=\s*", body)
    if not m:
        return []
    try:
        data, _ = json.JSONDecoder().raw_decode(body, m.end())
    except ValueError:
        return []
    return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []


def _mdy(s):
    m = re.match(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$", str(s or ""))
    try:
        return dt.date(int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else None
    except ValueError:
        return None


def _stamp(day, clock, zone):
    d = dt.datetime.strptime(day + clock[:6], "%Y%m%d%H%M%S")
    if clock.endswith("Z"):
        return C.local(d.replace(tzinfo=dt.timezone.utc))
    if zone and zone != "America/New_York":
        try:
            return C.local(d.replace(tzinfo=ZoneInfo(zone)))
        except Exception:
            return None
    return d


def _block(body, label):
    m = re.search(BLOCK_RX.pattern % re.escape(label), body, re.S)
    return C.clean(re.sub(r"<[^>]+>", " ", m.group(1))) if m else ""


def parse_detail(body):
    """Event page -> {"start", "end", "all_day", "loc", "desc"} (start None if the page
    has no readable "Add to Calendar" link)."""
    out = {"start": None, "end": None, "all_day": False, "loc": "", "desc": ""}
    g = GCAL_RX.search(body)
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(html.unescape(g.group(1))).query) if g else {}
    dates, zone = (q.get("dates") or [""])[0], (q.get("ctz") or [""])[0]
    m = re.match(r"^(\d{8})T(\d{6}Z?)/(\d{8})T(\d{6}Z?)$", dates)
    if m:
        try:
            st, en = _stamp(m.group(1), m.group(2), zone), _stamp(m.group(3), m.group(4), zone)
        except ValueError:
            st = en = None
        if st:
            out["start"], out["end"] = st, en if en and en > st else None
    else:
        m = re.match(r"^(\d{8})/(\d{8})$", dates)
        if m:
            try:
                first = dt.datetime.strptime(m.group(1), "%Y%m%d").date()
                last = dt.datetime.strptime(m.group(2), "%Y%m%d").date() - dt.timedelta(days=1)   # end is exclusive
            except ValueError:
                first = last = None
            if first:
                out["start"], out["end"], out["all_day"] = first, last if last and last > first else None, True
    loc = _block(body, "Address")
    if not loc:
        loc = C.clean(re.sub(r"<[^>]+>", " ", (q.get("location") or [""])[0]))
    out["loc"] = loc
    notes = []
    cost = _block(body, "Cost")
    if cost:
        notes.append("Cost: " + cost)
    w = re.search(r'<div class="wysiwyg\s*">(.*?)</div>', body, re.S)
    if w:
        notes.append(C.text(w.group(1)))
    out["desc"] = "\n\n".join(x for x in notes if x)
    return out


def _agrees(item, info):
    """Does a (possibly cached) event page still describe what the listing shows?"""
    st = info.get("start")
    if st is None:
        return False
    first = _mdy(item.get("start"))
    if (st.date() if isinstance(st, dt.datetime) else st) != first:
        return False
    clock = C.clock_from_text(str(item.get("time") or ""))
    if clock and isinstance(st, dt.datetime) and (_mdy(item.get("end")) or first) == first:
        return st.time() == clock[0]
    return True


def _with_city(loc, city):
    """Append the entry's `city` to an address that names neither Philadelphia nor a state."""
    if not loc or not city or CITY_RX.search(loc) or STATE_RX.search(loc):
        return loc
    return f"{loc}, {city}"


def parse(body, src, details=None):
    """Listing page -> events. `details` maps an event URL to what parse_detail read from
    that page; without it an event carries only what the listing states."""
    details = details or {}
    out = []
    for it in _items(body):
        first = _mdy(it.get("start"))
        if not first or not it.get("title"):
            continue
        last = _mdy(it.get("end")) or first
        url = urllib.parse.urljoin(src["url"], str(it.get("url") or "")) or src["url"]
        key = str(it.get("id") or f"{url}|{first}")
        info = details.get(url) or {}
        loc, desc = _with_city(info.get("loc", ""), src.get("city")), info.get("desc", "")
        if info and _agrees(it, info):
            e = C.event(src, key, it["title"], info["start"], info.get("end"), bool(info.get("all_day")), loc, url, desc)
        else:
            clock = C.clock_from_text(str(it.get("time") or ""))
            if clock and last == first:
                e = C.event(src, key, it["title"], dt.datetime.combine(first, clock[0]), None, False, loc, url, desc)
            else:
                e = C.event(src, key, it["title"], first, last if last > first else None, True, loc, url, desc)
        if e:
            out.append(e)
    return out


def read(src, ctx):
    body = C.get_text(src["url"])
    cache, today, opened, details = ctx["detail"], ctx["today"], 0, {}
    for it in _items(body):
        first = _mdy(it.get("start"))
        url = urllib.parse.urljoin(src["url"], str(it.get("url") or ""))
        if not first or not url or url in details or not (ctx["lo"] <= (_mdy(it.get("end")) or first) and first <= ctx["hi"]):
            continue
        c = cache.get(url)
        if c and c.get("events") and (today - dt.date.fromisoformat(c["fetched"])).days < TTL_DAYS:
            info = C.unpack(c["events"][0])
            if info.get("start") is None or _agrees(it, info):     # a page with no calendar link is not asked for again
                details[url] = info
                continue
        if opened >= MAX_NEW_PAGES:
            continue
        opened += 1
        time.sleep(max(0, CRAWL_DELAY - 1.5))                 # C.get_text adds its own 1.5 s
        try:
            info = parse_detail(C.get_text(url))
        except Exception as ex:
            if type(ex).__name__ == "BlockedError":            # a 403/406 stops the source; never worked around
                raise
            continue
        cache[url] = {"fetched": today.isoformat(), "events": [C.pack(info)]}
        details[url] = info
    return parse(body, src, details)
