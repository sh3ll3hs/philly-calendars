"""
Parks on Tap (Philadelphia's traveling beer garden, a different city park each week) — reader.

Source: https://www.parksontap.com/locations  (Squarespace events collection, read from
the page's own HTML; one request per run).
Why not the built-in `squarespace` method: it asks for `<page>?format=json`, and this
site's robots.txt (the standard Squarespace one) has `Disallow: /*?format=json` for every
crawler. The HTML page itself is allowed and carries the same events. The built-in `text`
method reads nothing from it.

Each stop is one `<article class="eventlist-event ...">` with
    <a class="eventlist-title-link" href="/locations/...">Columbus Square Park</a>
    <time class="event-date" datetime="2026-10-07">Wed, Oct 7, 2026</time>  <time class="event-time-12hr" ...>4:00 PM</time>
    <time class="event-date" datetime="2026-10-12">Mon, Oct 12, 2026</time> <time class="event-time-12hr" ...>10:00 PM</time>
and an excerpt that starts with the opening hours:
    HOURS:  WEDNESDAY - FRIDAY | 4 - 10PM   SATURDAY - SUNDAY | 12 - 10PM
A stop runs several days, so the reader writes one event per open day with that day's
hours from the HOURS lines ("Parks on Tap: Columbus Square Park", Wed 4-10 PM ... Sat 12-10 PM).

SEASONAL: the garden runs from about April to mid October. On 2026-11-15 the page listed
only past stops (the last one, Columbus Square Park, ended Oct 12), so the source yields
nothing until the next season is posted; upcoming stops use the same markup
(`eventlist-event--upcoming` instead of `--past`).

Checked on 2026-11-15 against the page text and its own "Google Calendar" links (UTC):
Columbus Square Park, Wed Oct 7 4:00 PM to Mon Oct 12 10:00 PM (link 20261007T200000Z/
20261013T020000Z); Stephen Girard Park, Wed Sep 30 4:00 PM to Sun Oct 4 10:00 PM; Penn
Treaty, Sep 2 to Sep 7 with "LABOR DAY, MONDAY 12 - 10PM". Shown times are Eastern.

Known failure modes:
  * A day of the run whose weekday is not in the HOURS lines is treated as closed, except
    the first day (kept with the published start time, no end) and the last day when the
    published end is in the afternoon or evening (kept as an all-day entry, because the
    page states no opening time for it; Columbus Square Park's Monday Oct 12 is the example).
  * Some stops publish an end such as "Sun, Sep 27 4:00 AM" (Cliveden Park); the HOURS
    lines win for that day, so Sunday is 12-10 PM.
  * With no readable HOURS lines, or a run longer than 21 days, the stop is one entry
    from the published start to the published end (the feed shows "through <date>").
  * The page gives no street address; the location is the park's name plus
    "Philadelphia, PA" unless Squarespace's address line is filled in.
  * A weather closure announced elsewhere (Instagram) is not known here.
"""
import datetime as dt
import html
import re
import urllib.parse

import combined_to_ics as C

PREFIX = "Parks on Tap: "
MAX_RUN_DAYS = 21
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_DAY = r"(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?"
_CLOCK = r"\d{1,2}(?::\d{2})?\s*(?:[ap]\.?m\.?)?\s*(?:-|–|—|to)\s*\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?"
HOURS_RX = re.compile(r"\b" + _DAY + r"(?:\s*(?:-|–|—|to|through|thru)\s*" + _DAY + r")?[\s|:,]*(" + _CLOCK + r")", re.I)
ARTICLE_RX = re.compile(r'<article\b[^>]*class="[^"]*\beventlist-event\b[^"]*"[^>]*>(.*?)</article>', re.S)
TIME_RX = re.compile(r"<time\b([^>]*)>([^<]*)</time>")
CLOCK_RX = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*([AP])M\s*$", re.I)


def _attr(attrs, name):
    m = re.search(r'\b%s="([^"]*)"' % name, attrs)
    return html.unescape(m.group(1)) if m else ""


def _clock(text):
    m = CLOCK_RX.match(re.sub(r"[\s \xa0]+", " ", html.unescape(text)))
    if not m:
        return None
    hour = int(m.group(1)) % 12 + (12 if m.group(3).upper() == "P" else 0)
    return dt.time(hour, int(m.group(2)))


def _plain(markup):
    s = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", markup, flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", " ", s))


def opening_hours(excerpt):
    """'HOURS: WEDNESDAY - FRIDAY | 4 - 10PM ...' -> {weekday number: (open, close)}."""
    txt = _plain(excerpt)
    m = re.search(r"\bhours\b\s*:?(.*?)(?:\babout\b\s*:|$)", txt, re.I | re.S)
    if not m:
        return {}
    block = re.sub(r"\s+", " ", m.group(1))[:400]
    out = {}
    for h in HOURS_RX.finditer(block):
        clock = C.clock_from_text(h.group(3))
        if not clock or not clock[1]:
            continue
        first = DAYS.index(h.group(1).lower())
        last = DAYS.index(h.group(2).lower()) if h.group(2) else first
        n = first
        while True:
            out[n] = clock
            if n == last:
                break
            n = (n + 1) % 7
    return out


def parse(body, src):
    """The /locations page -> events (past stops included; the caller keeps the window)."""
    out = []
    for art in ARTICLE_RX.finditer(body):
        a = art.group(1)
        link = re.search(r'<a\b([^>]*\beventlist-title-link\b[^>]*)>(.*?)</a>', a, re.S)
        if not link:
            continue
        park = C.clean(re.sub(r"<[^>]+>", " ", link.group(2)))
        url = urllib.parse.urljoin(src["url"], _attr(link.group(1), "href"))
        dates, clocks = [], []
        for t in TIME_RX.finditer(a):
            cls, when = _attr(t.group(1), "class"), _attr(t.group(1), "datetime")[:10]
            if cls == "event-date" and re.match(r"\d{4}-\d{2}-\d{2}$", when):
                dates.append(dt.date.fromisoformat(when))
            elif cls.startswith("event-time-12hr"):
                clocks.append(_clock(t.group(2)))
        if not park or not dates:
            continue
        first, last = dates[0], dates[-1]
        opens = clocks[0] if clocks else None
        closes = clocks[-1] if len(clocks) > 1 else None
        ex = re.search(r'class="eventlist-excerpt"[^>]*>(.*?)(?:<a\b[^>]*\beventlist-button\b|<div\b[^>]*\beventlist-actions\b|$)', a, re.S)
        excerpt = re.sub(r"</div>\s*$", "", ex.group(1).strip()) if ex else ""
        addr = re.search(r'<li\b[^>]*\beventlist-meta-address\b[^>]*>(.*?)</li>', a, re.S)
        loc = C.clean(re.sub(r"\(\s*map\s*\)", "", _plain(addr.group(1)), flags=re.I)) if addr else ""
        loc = loc or f"{park}, Philadelphia, PA"
        title = park if "parks on tap" in park.lower() else PREFIX + park
        hours = opening_hours(excerpt)

        def add(key, start, end=None, all_day=False):
            e = C.event(src, key, title, start, end, all_day, loc, url, excerpt)
            if e:
                out.append(e)

        if not opens:                                           # no time shown: an all-day entry
            add(url, first, last if last > first else None, True)
        elif last == first or not hours or (last - first).days > MAX_RUN_DAYS:
            end = dt.datetime.combine(last, closes) if closes else None
            add(url, dt.datetime.combine(first, opens), end if end and end > dt.datetime.combine(first, opens) else None)
        else:
            day = first
            while day <= last:
                key = f"{url}|{day}"
                if day.weekday() in hours:
                    o, c = hours[day.weekday()]
                    start, end = dt.datetime.combine(day, o), dt.datetime.combine(day, c)
                    add(key, start, end if end > start else end + dt.timedelta(days=1))
                elif day == first:
                    add(key, dt.datetime.combine(day, opens))
                elif day == last and closes and closes >= dt.time(12, 0):
                    add(key, day, None, True)
                day += dt.timedelta(days=1)
    return out


def read(src, ctx):
    got = parse(C.get_text(src["url"]), src)
    return [e for e in got if (e["start"].date() if isinstance(e["start"], dt.datetime) else e["start"]) >= ctx["lo"]]
