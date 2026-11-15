"""
Institute of Contemporary Art, University of Pennsylvania — calendar reader.

Source: https://icaphila.org/calendar/  (WordPress, server-rendered; /events/ redirects
here; one request per run; robots.txt disallows nothing). The site has no events feed, no
events REST route and no schema.org Event data (event pages are marked up as articles).

The page has three parts: "On View" (exhibitions with a closing date), an optional list
of today's events, and "Upcoming Events". Every event row holds
    <div class="event-date ..."><span class="upcoming">Wed, Dec 2, 2026, 6PM–8PM</span></div>
    <a href="https://icaphila.org/events/..." class="black-text title">Title</a>
    <ul class="... event_types"> <a>Artist Talk</a> </ul>   <div class="... locations"></div>
and this reader takes exactly those rows.

Why not the built-in `text` method: it reads the three events with the right dates and
start times, but it strips the punctuation out of the titles ("2026 2027 Visiting Artist
Lecture Series Elle Pérez"), has no end times, and turns the first exhibition's closing
date into an all-day event ("Through The Condition of Being Near", Feb 21). The `html`
method finds nothing (no schema.org data on event pages).

Checked on 2026-11-15 against the calendar page and one event page:
  Sachs Lecture in Contemporary Art History | Shivani Shedde ...   Wed, Dec 2, 2026, 6PM–8PM
  2026-2027 Visiting Artist Lecture Series: Elle Pérez             Thu, Dec 3, 2026, 6PM–8PM
      (its own page prints "Dec 3, 2026, 6PM–8PM")
  Performance | Wilmer Wilson IV: Skirl (III)                      Sat, Dec 5, 2026, 11AM–6PM

Known failure modes:
  * The place is not printed per event (the `locations` block was empty for every row
    seen); the source entry's `venue` (ICA, 118 S. 36th Street) is used. An off-site or
    Zoom-only programme would still be shown at ICA; a filled `locations` block is used
    when there is one.
  * A row whose date text has no year, or cannot be read, is skipped rather than guessed.
  * A row with two different dates (a run) becomes one all-day entry from the first date
    "through" the last; its clock times are not used because it is unclear which day
    they belong to. This format was not seen on the page and is handled defensively.
  * A row with no clock time becomes an all-day event.
  * Only what the page lists is read (three events on the day this was written); ICA posts
    programmes a few weeks ahead.
  * If the theme's class names change (`event-date`, `black-text title`) the reader
    returns nothing.
"""
import datetime as dt
import re
import urllib.parse

import combined_to_ics as C

MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
ROW_RX = re.compile(r'<div class="event-date\b[^"]*"[^>]*>(.*?)</div>', re.S)
TITLE_RX = re.compile(r'<a\b[^>]*?href="([^"]+)"[^>]*?class="[^"]*\bblack-text title\b[^"]*"[^>]*>(.*?)</a>', re.S)
TYPES_RX = re.compile(r'<ul class="[^"]*\bevent_types\b[^"]*"[^>]*>(.*?)</ul>', re.S)
PLACE_RX = re.compile(r'<div class="[^"]*\blocations\b[^"]*"[^>]*>(.*?)</div>', re.S)
DATE_RX = re.compile(r"\b([A-Z][a-z]{2})[a-z]*\.?\s+(\d{1,2})(?:,?\s+(20\d{2}))?")


def _plain(markup):
    return C.clean(re.sub(r"<[^>]+>", " ", markup or ""))


def when(text):
    """'Wed, Dec 2, 2026, 6PM–8PM' -> (start, end, all_day), or None when there is no full date."""
    found = [(MONTHS.get(m.group(1).lower()), int(m.group(2)), m.group(3), m.end()) for m in DATE_RX.finditer(text)]
    found = [f for f in found if f[0]]
    years = [int(f[2]) for f in found if f[2]]
    if not found or not years:
        return None
    days = []
    for mon, day, year, _ in found:
        try:
            d = dt.date(int(year) if year else years[-1], mon, day)
        except ValueError:
            return None
        if d not in days:
            days.append(d)
    if len(days) > 1:
        return (days[0], days[-1], True) if days[-1] > days[0] else None
    clock = C.clock_from_text(text[found[-1][3]:])
    if not clock:
        return days[0], None, True
    st = dt.datetime.combine(days[0], clock[0])
    en = dt.datetime.combine(days[0], clock[1]) if clock[1] else None
    if en and en <= st:
        en += dt.timedelta(days=1)
    return st, en, False


def parse(body, src):
    out, seen = [], set()
    rows = list(ROW_RX.finditer(body))
    for i, m in enumerate(rows):
        chunk = body[m.end():rows[i + 1].start() if i + 1 < len(rows) else m.end() + 4000]
        date_text = _plain(m.group(1))
        t = TITLE_RX.search(chunk)
        if not t or "{{" in date_text or "{{" in t.group(0):     # the page's script template
            continue
        got = when(date_text)
        title = _plain(t.group(2))
        if not got or not title:
            continue
        url = urllib.parse.urljoin(src["url"], C.clean(t.group(1)))
        key = f"{url}|{got[0].isoformat()}"
        if key in seen:
            continue
        seen.add(key)
        kinds = TYPES_RX.search(chunk)
        place = PLACE_RX.search(chunk)
        e = C.event(src, key, title, got[0], got[1], got[2], _plain(place.group(1)) if place else "", url,
                    ", ".join(_plain(x) for x in re.findall(r"<li\b.*?</li>", kinds.group(1), re.S)) if kinds else "")
        if e:
            out.append(e)
    return out


def read(src, ctx):
    return parse(C.get_text(src["url"]), src)
