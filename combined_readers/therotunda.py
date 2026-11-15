"""
The Rotunda (4014 Walnut St, West Philadelphia) — events reader.

Source: https://www.therotunda.org/events  (a Rails site, server-rendered month grid;
other months at /events?date=YYYY-MM-15, linked from the page as "nextMonth").
The site has no feed, no JSON and no schema.org data, and the built-in `text` method
reads only 2 of the month's 29 events (from dates that happen to be written out in a
description): a day cell holds only the day number, the month and year are in the page
heading. robots.txt allows everything.

One month page holds, per day cell (`<td>`; cells of the neighbouring months are
`<td class="notmonth">` and are skipped):
    <span class="day">16</span>
    <li class="anEvent" data-powertiptarget="eventData_3654"> 6:00 PM<a href="/event/...">Title</a></li>
    <div class="eventPop" id="eventData_3654"> <span> 6:00 PM -  8:30 PM</span> <span class="truncate">text</span></div>

Requests per run: the current month and the next one, then one more month at a time for
as long as the month just read has events, four pages at most (`"months"` in the source
entry changes the cap). On 2026-11-15 that was November to February (events up to Feb 17).

Checked on 2026-11-15 against the pages a visitor sees: FLATstrap Launch Party (Sun Nov 15,
12:00 PM - 4:00 PM), Comm University Vogue Commentating Class (Mon Nov 16, 6:00 PM - 8:30 PM;
the link slug ends -2026-11-16-18-00-00-0500, the same wall time), Bowerbird pres. Water Can
Assume Any Form (Fri Dec 4, 8:00 PM - 9:30 PM) and Trans Art Mart (Dec 5 and 6, 11:00 AM - 5:00 PM).

Known failure modes:
  * Titles on the site start with "In-person!" or "Online!". "In-person!" is dropped;
    an "Online!" event keeps its title with "(online)" added and gets the location
    "Online" instead of the hall.
  * Times are the visible "6:00 PM - 8:30 PM" text (Eastern wall time). An event with no
    readable time becomes all-day; an end at or before the start is read as after midnight.
  * Only the main grid (the first `table.calendar`) is read; the two small month tables
    further down the page carry no events.
  * If the grid's markup changes (`currentMonth`, `table.calendar`, `span.day`,
    `li.anEvent`) the reader returns nothing rather than guessing.
  * Events beyond the fourth month page, or behind an empty month, are not seen until
    their month comes within reach.
"""
import datetime as dt
import html
import re
import urllib.parse

import combined_to_ics as C

VENUE = "The Rotunda, 4014 Walnut St, Philadelphia, PA 19104"
MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}

MONTH_RX = re.compile(r'id="currentMonth"[^>]*>\s*([A-Za-z]+)\s+(20\d{2})')
NEXT_RX = re.compile(r'<a[^>]*id="nextMonth"[^>]*href="([^"]+)"|<a[^>]*href="([^"]+)"[^>]*id="nextMonth"')
TABLE_RX = re.compile(r'<table[^>]*class="[^"]*\bcalendar\b[^"]*"[^>]*>(.*?)</table>', re.S)
CELL_RX = re.compile(r"<td\b([^>]*)>")
DAY_RX = re.compile(r'<span[^>]*class="day"[^>]*>\s*(\d{1,2})\s*</span>')
ITEM_RX = re.compile(r'<li[^>]*class="[^"]*\banEvent\b[^"]*"[^>]*>(.*?)</li>', re.S)
KIND_RX = re.compile(r"^(?P<pre>(?:.{0,22}!\s+)?)(?P<kind>in[- ]person|online)\s*!+\s*(?P<rest>.+)$", re.I | re.S)


def month_of(body):
    """(year, month) of the grid on a page, or None."""
    m = MONTH_RX.search(body)
    if not m or m.group(1)[:3].lower() not in MONTHS:
        return None
    return int(m.group(2)), MONTHS[m.group(1)[:3].lower()]


def next_month_url(body, page_url):
    m = NEXT_RX.search(body)
    return urllib.parse.urljoin(page_url, html.unescape(m.group(1) or m.group(2))) if m else ""


def parse(body, src):
    """One month page -> events (every event of that month, past ones included)."""
    ym = month_of(body)
    table = TABLE_RX.search(body)
    if not ym or not table:
        return []
    grid = table.group(1)
    venue = src.get("venue") or VENUE
    cells = list(CELL_RX.finditer(grid))
    out = []
    for i, c in enumerate(cells):
        if re.search(r'class="[^"]*\bnotmonth\b', c.group(1)):
            continue
        cell = grid[c.end():cells[i + 1].start() if i + 1 < len(cells) else len(grid)]
        day = DAY_RX.search(cell)
        if not day:
            continue
        try:
            date = dt.date(ym[0], ym[1], int(day.group(1)))
        except ValueError:
            continue
        items = list(ITEM_RX.finditer(cell))
        for k, it in enumerate(items):
            link = re.search(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', it.group(1), re.S)
            if not link:
                continue
            title = C.clean(re.sub(r"<[^>]+>", " ", link.group(2)))
            url = urllib.parse.urljoin(src["url"], html.unescape(link.group(1)))
            rest = cell[it.end():items[k + 1].start() if k + 1 < len(items) else len(cell)]
            span = re.search(r"<span>\s*([^<]*?)\s*</span>", rest)
            clock = C.clock_from_text(span.group(1)) if span else None
            if not clock:                                   # the list line itself starts with the start time
                clock = C.clock_from_text(re.sub(r"<a\b.*", "", it.group(1), flags=re.S))
            desc = re.search(r'<span[^>]*class="truncate"[^>]*>(.*)', rest, re.S)
            desc = re.sub(r"</span>\s*</div>\s*(</ul>\s*)?$", "", desc.group(1).strip()) if desc else ""
            loc = venue
            kind = KIND_RX.match(title)
            if kind:
                title = (kind.group("pre") + kind.group("rest")).strip()
                if kind.group("kind").lower() == "online":
                    title, loc = title + " (online)", "Online"
            ident = re.search(r'data-powertiptarget="([^"]+)"', it.group(0))
            key = ident.group(1) if ident else f"{url}|{date}"
            if clock:
                start = dt.datetime.combine(date, clock[0])
                end = dt.datetime.combine(date, clock[1]) if clock[1] else None
                if end and end <= start:
                    end += dt.timedelta(days=1)
                e = C.event(src, key, title, start, end, False, loc, url, desc)
            else:
                e = C.event(src, key, title, date, None, True, loc, url, desc)
            if e:
                out.append(e)
    return out


def read(src, ctx):
    url, out, seen = src["url"], [], set()
    for n in range(max(1, int(src.get("months", 4)))):
        body = C.get_text(url)
        got = parse(body, src)
        out += [e for e in got if e["key"] not in seen]
        seen.update(e["key"] for e in got)
        ym, nxt = month_of(body), next_month_url(body, url)
        if not ym or not nxt or (n >= 1 and not got):
            break
        following = dt.date(ym[0] + (ym[1] == 12), ym[1] % 12 + 1, 1)
        if following > ctx["hi"]:
            break
        url = nxt
    return out
