"""
Cherry Street Pier (121 N Christopher Columbus Blvd; run by the Delaware River Waterfront
Corporation) — events reader.

Listing, one request per run: https://www.cherrystreetpier.com/events/  (WordPress, custom
theme, server-rendered cards: a date line with no year and no time, a title, a link).
Event pages, at most 12 new ones per run, cached for a week in ctx["detail"]: the date with
its year, "Location: ..." (a spot on the pier) and "Time: ..." as plain text, e.g.
    Saturday / November 21 / 2026     Location: Cherry Street Pier     Time: 11am to 3pm
    May 1-December 4 / 2026           Location: Cherry Street Pier     Time: 4 pm to 9 pm

Why a reader of its own, and what is deliberately NOT used:
  * no Events Calendar plugin, no event route under /wp-json, no schema.org Event data;
  * /feed/calendar/ is an iCal feed, but it holds the ten most recently CREATED events (past
    ones included, long-running ones missing) and only dates, never times;
  * the "Add to Google Calendar" link on every event page says 16:00Z-24:00Z whatever the
    event's real hours are (Drink N' Draw: page "1pm to 3pm", link 11 am to 7 pm), so times
    are taken from the visible "Time:" line only.

How a page is read:
  * one day + a clock time in "Time:"            -> a timed entry;
  * one day, no readable time                    -> an all-day entry;
  * a run of days whose text lists its dates after "dates:" or "Schedule:" ("First Friday
    dates: March 6, April 3, ... and December 4.")  -> one entry per listed date inside the
    run, at the "Time:" hours (only on the weekdays "Time:" names, if it names any);
  * any other run of days ("November 6-26", "Time: Pier Operating Hours" or none)
                                                  -> one all-day entry on the first day that
    the feed labels "(through <last day>)"; with plain hours ("5 pm to 8 pm") it is timed.
  * an event page not read yet (over the 12-page budget, or it failed) -> an all-day entry
    from the card's date, replaced by the full one on a later run.
Location is "<Location line>, <venue>" (the entry's `venue` carries the pier's address).

Checked on 2026-11-15 against the event pages: Drink N' Draw Featuring a Live Cosplay Model
(Sunday November 15 2026, 1pm to 3pm, Amphitheater), DiasporaDNA Kinkeeping Summit & Holiday
Market (Saturday November 21 2026, 11am to 3pm) and First Friday presented by Fulton Bank
(listed date December 4, 4 pm to 9 pm).

Known failure modes:
  * A run that started more than three days ago and lists no dates (exhibitions, "Art
    Classes ... Times Vary") is outside the feed's window and does not appear.
  * Dates are listed in prose; a list worded differently ("every Sunday in December") is not
    expanded, and a list after "dates:" that means something else would be read as
    occurrences (lists introduced by closed/cancelled/except are ignored).
  * "Time:" with two different sets of hours gives all-day entries rather than a guess.
  * If the theme's class names change (`card-event`, `event-date`, `event-time`,
    `event-location`, `event-description`) the reader returns nothing or all-day entries.
"""
import datetime as dt
import re
import urllib.parse

import combined_to_ics as C

MAX_NEW_PAGES = 12
TTL_DAYS = 7
MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
WEEKDAY = r"(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?"
MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
DAYS = {d: i for i, d in enumerate("mon tue wed thu fri sat sun".split())}
SPAN_RX = re.compile(r"(?:\b(" + WEEKDAY + r"),?\s+)?\b" + MONTH + r"\s+(\d{1,2})\b"
                     r"(?:\s*[–—-]\s*(?:" + MONTH + r"\s+)?(\d{1,2})\b)?(?:,?\s*(20\d{2}))?", re.I)
LIST_CUE_RX = re.compile(r"\b(?:dates?|schedule)\s*:\s*", re.I)
LIST_ITEM_RX = re.compile(r"(?:and\s+)?(?:" + WEEKDAY + r",?\s+)?" + MONTH + r"\s+(\d{1,2})(?:st|nd|rd|th)?\b\s*[,;.]?\s*", re.I)
CLOCK_RX = re.compile(r"\b\d{1,2}(?::\d{2})?\s*[ap]\.?m\b", re.I)
DAYNAME_RX = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tues?|wed|thur?s?|fri|sat|sun)s?\b", re.I)
CARD_RX = re.compile(r'<div class="card card-event">\s*<a href="([^"]+)"[^>]*>(.*?)</a>', re.S)


def _plain(markup):
    return C.clean(re.sub(r"<[^>]+>", " ", str(markup or "")))


def _date(year, mon, day):
    try:
        return dt.date(year, mon, day)
    except ValueError:
        return None


def span(text, today):
    """'Saturday November 21 2026' / 'April 3-December 4 2026' / 'November 6-26' / 'Sunday,
    November 15' -> (first day, last day or None). Without a year: the year that fits the
    weekday, else this year (next year once the date is over 30 days past)."""
    m = SPAN_RX.search(_plain(text))
    if not m:
        return None, None
    wd, mon1, d1, mon2, d2, year = m.groups()
    mon1 = MONTHS[mon1[:3].lower()]
    mon2 = MONTHS[mon2[:3].lower()] if mon2 else mon1
    d1, d2 = int(d1), int(d2) if d2 else None
    if year:
        year = int(year)
        last = _date(year, mon2, d2) if d2 else None
        first = _date(year, mon1, d1)
        if first and last and first > last:              # "December 15-January 5 2027"
            first = _date(year - 1, mon1, d1)
        return first, last
    if d2 is None:
        if wd:
            for y in (today.year, today.year + 1, today.year - 1):
                d = _date(y, mon1, d1)
                if d and d.weekday() == DAYS[wd[:3].lower()]:
                    return d, None
        return C.normalize.infer_year(mon1, d1, today), None
    last = C.normalize.infer_year(mon2, d2, today)       # a run is listed until its last day
    if not last:
        return None, None
    first = _date(last.year, mon1, d1)
    if first and first > last:
        first = _date(last.year - 1, mon1, d1)
    return first, last


def listed_dates(text, first, last):
    """Dates written out after 'dates:' / 'Schedule:' that fall inside the run."""
    for cue in LIST_CUE_RX.finditer(text):
        if re.search(r"(closed|closure|cancel+ed|except)\W*(\w+\W+){0,3}$", text[max(0, cue.start() - 40):cue.start()], re.I):
            continue
        pos, found = cue.end(), []
        while True:
            m = LIST_ITEM_RX.match(text, pos)
            if not m:
                break
            found.append((MONTHS[m.group(1)[:3].lower()], int(m.group(2))))
            pos = m.end()
        if len(found) < 2:
            continue
        out = []
        for mon, day in found:
            for y in range(first.year, last.year + 1):
                d = _date(y, mon, day)
                if d and first <= d <= last and d not in out:
                    out.append(d)
        if out:
            return sorted(out)
    return []


def hours(time_text):
    """'Time: 11am to 3pm' -> ((start, end or None), weekdays named, plain?). No clock, or
    more than one set of hours, gives (None, set(), False)."""
    t = re.sub(r"^\s*time\s*:\s*", "", time_text, flags=re.I)
    clock = C.clock_from_text(t)
    if not clock or len(CLOCK_RX.findall(t)) > (2 if clock[1] else 1):
        return None, set(), False
    named = {DAYS[w[:3].lower()] for w in DAYNAME_RX.findall(t)}
    rest = re.sub(r"\d{1,2}(?::\d{2})?\s*(?:[ap]\.?m\.?)?|\b(from|to|at|until)\b|[–—-]", " ", t, flags=re.I)
    return clock, named, not re.search(r"[A-Za-z]", rest)


def _timed(src, key, title, day, clock, loc, url, desc, last=None):
    st = dt.datetime.combine(day, clock[0])
    en = dt.datetime.combine(last or day, clock[1]) if clock[1] else (dt.datetime.combine(last, clock[0]) if last else None)
    if en and en <= st:
        en += dt.timedelta(days=1)
    return C.event(src, key, title, st, en, False, loc, url, desc)


def parse_detail(body, src, url, title="", today=None):
    """One event page -> its events ([] when the page has no readable date)."""
    today = today or dt.date.today()
    m = re.search(r'<div class="event-details">(.*?)<div class="event-thumb"', body, re.S)
    box = m.group(1) if m else ""
    part = lambda cls: (re.search(r'<div class="%s">(.*?)</div>' % cls, box, re.S) or [None, ""])[1]
    first, last = span(re.sub(r"<br\s*/?>", " ", part("event-date")), today)
    if not first:
        return []
    if not title:
        h = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S)
        title = _plain(h.group(1)) if h else ""
    place = re.sub(r"^\s*location\s*:\s*", "", _plain(part("event-location")), flags=re.I)
    venue = src.get("venue", "")
    loc = venue if not place or place.lower() == venue.split(",")[0].strip().lower() else ", ".join(x for x in (place, venue) if x)
    m = re.search(r'<div class="event-description[^"]*">(.*?)</section>', body, re.S)
    body_html = m.group(1) if m else ""
    desc = C.text(body_html)
    clock, named, plain = hours(_plain(part("event-time")))
    if not last or last <= first:
        e = _timed(src, f"{url}|{first}", title, first, clock, loc, url, desc) if clock else \
            C.event(src, f"{url}|{first}", title, first, None, True, loc, url, desc)
        return [e] if e else []
    out = []
    for day in listed_dates(_plain(body_html), first, last):
        if clock and (not named or day.weekday() in named):
            e = _timed(src, f"{url}|{day}", title, day, clock, loc, url, desc)
        else:
            e = C.event(src, f"{url}|{day}", title, day, None, True, loc, url, desc)
        if e:
            out.append(e)
    if out:
        return out
    e = _timed(src, f"{url}|{first}", title, first, clock, loc, url, desc, last) if clock and plain else \
        C.event(src, f"{url}|{first}", title, first, last, True, loc, url, desc)
    return [e] if e else []


def cards(body, src):
    """Listing page -> [(url, title, date text)] in page order."""
    out = []
    for href, inner in CARD_RX.findall(body):
        title = re.search(r'<h5 class="card-title">(.*?)</h5>', inner, re.S)
        when = re.search(r'<h6 class="card-subtitle">(.*?)</h6>', inner, re.S)
        url = urllib.parse.urljoin(src["url"], C.clean(href))
        if title and _plain(title.group(1)) and url not in [u for u, _, _ in out]:
            out.append((url, _plain(title.group(1)), _plain(when.group(1)) if when else ""))
    return out


def parse(body, src, today=None, details=None):
    """Listing page -> events. `details` maps an event URL to the events parse_detail read
    from its page; a card without one becomes an all-day entry from the card's own date."""
    today = today or dt.date.today()
    details = details or {}
    out = []
    for url, title, when in cards(body, src):
        if url in details:
            out += details[url]
            continue
        first, last = span(when, today)
        if first:
            e = C.event(src, f"{url}|{first}", title, first, last if last and last > first else None, True, "", url,
                        "Hours not read yet; see the event page.")
            if e:
                out.append(e)
    return out


def read(src, ctx):
    body = C.get_text(src["url"])
    cache, today, opened, details = ctx["detail"], ctx["today"], 0, {}
    for url, title, when in cards(body, src):
        c = cache.get(url)
        if not (c and (today - dt.date.fromisoformat(c["fetched"])).days < TTL_DAYS) and opened < MAX_NEW_PAGES:
            opened += 1
            try:
                evs = parse_detail(C.get_text(url), src, url, title, today)
            except Exception as ex:
                if type(ex).__name__ == "BlockedError":      # a 403/406 stops the source; never worked around
                    raise
                evs = None                                   # keep whatever an earlier run cached
            if evs is not None:
                c = cache[url] = {"fetched": today.isoformat(), "events": [C.pack(e) for e in evs]}
        if c and c.get("events"):
            details[url] = [C.unpack(e) for e in c["events"]]
    return parse(body, src, today, details)
