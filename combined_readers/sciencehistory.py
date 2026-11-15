"""
Science History Institute (315 Chestnut St) — events reader.

Source: https://www.sciencehistory.org/visit/events/ and its /page/2/ ... pages (WordPress,
custom "events" post type, server-rendered, 28 cards a page, soonest first).

Why a reader of its own: there is no Events Calendar plugin (/wp-json/tribe/... is 404), the
REST collection /wp-json/wp/v2/events carries no event date (only the post date; `acf` is
empty), the pages have no schema.org Event data, the filter form posts to admin-ajax with a
nonce, and the built-in `text` method reads 1 of 28 cards because a card writes its date as
three separate boxes (month "Nov", day "18", weekday "Wed").

A card gives: link, title, start date (and an end date for a multi-day programme), the time
as text ("12pm-12:45pm", "11:30am", none), type labels ("Free", "Tours", "Online", "Hybrid")
and a one-line summary. Cards carry no year, so the year is the one in which that month and
day fall on the card's weekday (unique among last year, this year and next year).
Location: a card labelled "Online" is "Online"; every other event is at the Institute (the
entry's `venue`), with "(also online)" added for "Hybrid".

Requests per run: the first page, then following pages only while a "next" link exists and
the last card read is still inside the window (2 of the site's 4 pages on 2026-11-15, never
more than 6).

Checked on 2026-11-15 against event pages: "Othmer Library Tour" (page: "Wednesday, November
18, 2026 | 12pm-12:45pm EST", Science History Institute, 315 Chestnut Street) and "The
Electrical Grid in Flux" ("Thursday, November 19, 2026 | 1pm-2pm EST", "Online") match their
cards. Times are written as local wall-clock text, so there is no time-zone step.

Known failure modes:
  * A card with no time text is an all-day entry; a start time with no end gets the feed's
    default length.
  * A multi-day card ("Jan 04 Mon" to "Jan 07 Thu", "10am-1pm") is one entry from the first
    day's start to the last day's end; the feed shows it on the first day as "(through Jan 7)".
  * A card without a weekday falls back to "this year, or next year if that is over 30 days
    ago".
  * "Online"/"Hybrid" come from the card's labels; an online event that is not labelled gets
    the Institute's address.
  * If the theme's class names change (`shi-archive-event-item__*`) the reader returns nothing.
"""
import datetime as dt
import re
import urllib.parse

import combined_to_ics as C

CARD = '<div class="archive-list--item shi-archive-event-item">'
MAX_PAGES = 6
MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
DAYS = {d: i for i, d in enumerate("mon tue wed thu fri sat sun".split())}
BOX_RX = re.compile(r'date-container_(start|end)\b(.*?)(?=shi-archive-event-item__date-container\b|'
                    r'shi-archive-event-item__times|shi-archive-event-item__terms|$)', re.S)


def _part(chunk, name):
    m = re.search(r'class="shi-archive-event-item__%s"[^>]*>(.*?)</(?:div|h3|p)>' % name, chunk, re.S)
    return C.clean(re.sub(r"<[^>]+>", " ", m.group(1))) if m else ""


def _day(chunk, today):
    """A date box (month / day / weekday) -> date, or None."""
    mon = MONTHS.get(_part(chunk, "month")[:3].lower())
    num = re.match(r"\d{1,2}$", _part(chunk, "date"))
    if not mon or not num:
        return None
    wd = DAYS.get(_part(chunk, "day")[:3].lower())
    if wd is None:
        return C.normalize.infer_year(mon, int(num.group(0)), today)
    for year in (today.year, today.year + 1, today.year - 1):
        try:
            d = dt.date(year, mon, int(num.group(0)))
        except ValueError:
            continue
        if d.weekday() == wd:
            return d
    return None


def next_page(body, page_url):
    m = re.search(r'<a[^>]*class="next page-numbers"[^>]*href="([^"]+)"|<a[^>]*href="([^"]+)"[^>]*class="next page-numbers"', body)
    return urllib.parse.urljoin(page_url, C.clean(m.group(1) or m.group(2))) if m else ""


def parse(body, src, today=None):
    """One listing page -> events (in page order)."""
    today = today or dt.date.today()
    out = []
    for chunk in body.split(CARD)[1:]:
        chunk = chunk.split("<!-- /.archive-list-item")[0]
        link = re.search(r'href="([^"]+)"', chunk)
        title = _part(chunk, "title")
        boxes = {kind: _day(part, today) for kind, part in BOX_RX.findall(chunk)}
        start, last = boxes.get("start"), boxes.get("end")
        if not link or not title or not start:
            continue
        if last and last < start:
            last = None
        url = urllib.parse.urljoin(src["url"], C.clean(link.group(1)))
        terms = [C.clean(re.sub(r"<[^>]+>", " ", t))
                 for t in re.findall(r'class="shi-archive-event-item__term"[^>]*>(.*?)</div>', chunk, re.S)]
        low = {t.lower() for t in terms}
        loc = "Online" if "online" in low else ""
        if "hybrid" in low and src.get("venue"):
            loc = src["venue"] + " (also online)"
        m = re.search(r'class="shi-archive-event-item__excerpt"[^>]*>(.*?)</p>\s*<a\b', chunk, re.S)
        desc = "\n\n".join(x for x in (C.text(m.group(1)) if m else "", " · ".join(terms)) if x)
        clock = C.clock_from_text(_part(chunk, "times"))
        if clock:
            st = dt.datetime.combine(start, clock[0])
            # no end time on a multi-day card: end on the last day at the start time, which
            # the feed reads as "default length, through <last day>"
            en = dt.datetime.combine(last or start, clock[1]) if clock[1] else \
                (dt.datetime.combine(last, clock[0]) if last else None)
            if en and en <= st:
                en += dt.timedelta(days=1)
            e = C.event(src, url, title, st, en, False, loc, url, desc)
        else:
            e = C.event(src, url, title, start, last, True, loc, url, desc)
        if e:
            out.append(e)
    return out


def read(src, ctx):
    out, url, seen = [], src["url"], set()
    for _ in range(MAX_PAGES):
        body = C.get_text(url)
        got = parse(body, src, ctx["today"])
        out += [e for e in got if e["key"] not in seen]
        seen.update(e["key"] for e in got)
        url = next_page(body, url)
        last = got[-1]["start"] if got else None
        if not url or not got or (last.date() if isinstance(last, dt.datetime) else last) > ctx["hi"]:
            break
    return out
