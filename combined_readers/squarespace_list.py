"""
Glen Foerd — events reader for a Squarespace "events list" page, read from its HTML.

Source: https://www.glenfoerd.org/events  (one request per run).
Why not the built-in `squarespace` method: it asks for `<page>?format=json`, and this
site's robots.txt (the standard Squarespace one) has `Disallow:/*?format=json` and
`Disallow:/*?format=ical` for every crawler. The plain page is allowed and already carries
everything, server-rendered, one `<article class="eventlist-event ...">` per event:
  * title and link        `a.eventlist-title-link`
  * day                   `<time class="event-date" datetime="2026-11-20">Friday, November 20, 2026</time>`
  * start / end           `<time class="event-time-localized-start" ...>7:00 PM</time>` / `...-end`
                          (an event that ends on another day shows two `event-date` + `event-time-localized` pairs)
  * place                 `li.eventlist-meta-address` ("Glen Foerd") and its map link (`?q=5001 Grant Avenue ...`)
  * blurb                 `div.eventlist-excerpt`
The built-in `text` method misreads this page (titles come out as "(map)", entries doubled).
The same markup is what every Squarespace events-list page uses, so this reader should work
for other Squarespace sites whose robots.txt rules out `?format=json`.

Checked on 2026-11-15 against the page: Fall Concert by Settlement Music School (Fri Nov 20,
7:00-8:00 PM), Monthly Guided Tour (Sun Dec 6, 11:00 AM-12:30 PM), Winter Solstice Celebration
(Sun Dec 20, 3:00-6:00 PM), all "Glen Foerd (map)" -> 5001 Grant Avenue. The page's own
"Google Calendar" links give the same instants in UTC (20261121T000000Z = 7:00 PM Eastern),
so the times on the page are Eastern.

Known failure modes:
  * Times are the visible text. A block with a date but no readable clock time becomes an
    all-day event.
  * A run that ends on a later day (a play, Feb 10 7:00 PM to Feb 28 2:00 PM) is one entry
    from its first start to its last end; the feed shows it on opening day "(through Feb 28)".
  * The page lists every upcoming event and about 30 past ones; past ones are returned too
    and dropped by the feed's date window.
  * If Squarespace renames the `eventlist-*` / `event-date` / `event-time-*` classes, or the
    site switches the page to a calendar-grid layout (drawn by script), nothing is returned.
"""
import datetime as dt
import html
import re
import urllib.parse

import combined_to_ics as C

ARTICLE_RX = re.compile(r'<article\b[^>]*class="[^"]*\beventlist-event\b[^"]*"[^>]*>(.*?)</article>', re.S)
TIME_RX = re.compile(r'<time\b[^>]*class="(event-[a-z0-9-]+)"[^>]*datetime="(\d{4})-(\d{2})-(\d{2})"[^>]*>(.*?)</time>', re.S)


def _plain(s):
    return C.clean(re.sub(r"<[^>]+>", " ", s or ""))


def _location(block):
    m = re.search(r'<li\b[^>]*class="[^"]*\beventlist-meta-address\b[^"]*"[^>]*>(.*?)</li>', block, re.S)
    if not m:
        return ""
    name = _plain(re.sub(r"<a\b.*?</a>", " ", m.group(1), flags=re.S))
    q = re.search(r'href="https?://maps\.google\.com/?\?q=([^"]*)"', m.group(1))
    street = re.sub(r",?\s*United States$", "", C.clean(urllib.parse.unquote_plus(html.unescape(q.group(1))))) if q else ""
    return C.address({"name": name, "address": street})


def parse(body, src):
    """Events-list HTML -> events (upcoming and the past ones the page still lists)."""
    out = []
    for m in ARTICLE_RX.finditer(body):
        block = m.group(1)
        link = re.search(r'<a\b[^>]*href="([^"]+)"[^>]*class="eventlist-title-link"[^>]*>(.*?)</a>', block, re.S) or \
            re.search(r'<a\b[^>]*class="eventlist-title-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not link:
            continue
        url = urllib.parse.urljoin(src["url"], html.unescape(link.group(1)))
        stamps = [(cls, dt.date(int(y), int(mo), int(d)), _plain(txt)) for cls, y, mo, d, txt in TIME_RX.findall(block)]
        days = [day for cls, day, _ in stamps if cls == "event-date"]
        if not days:
            continue
        clocks = [(cls, day, C.clock_from_text(txt)) for cls, day, txt in stamps if cls.startswith("event-time")]
        for kind in ("12hr", "localized"):                 # one family when the page prints the time twice (12 h and 24 h)
            if any(kind in cls for cls, _, _ in clocks):
                clocks = [c for c in clocks if kind in c[0]]
                break
        clocks = [(cls, day, c[0]) for cls, day, c in clocks if c]
        first = next((c for c in clocks if c[0].endswith("-start")), clocks[0] if clocks else None)
        last = next((c for c in clocks if c[0].endswith("-end")), None)
        if first and not last and len(clocks) > 1 and clocks[-1] is not first:
            last = clocks[-1]
        excerpt = re.search(r'<div class="eventlist-excerpt">(.*?)</div>', block, re.S)
        loc, desc = _location(block), excerpt.group(1) if excerpt else ""
        if first:
            start = dt.datetime.combine(first[1], first[2])
            end = dt.datetime.combine(last[1], last[2]) if last else None
            if end and end <= start:
                end = None
            e = C.event(src, url, link.group(2), start, end, False, loc, url, desc)
        else:
            e = C.event(src, url, link.group(2), days[0], days[-1] if days[-1] > days[0] else None, True, loc, url, desc)
        if e:
            out.append(e)
    return out


def read(src, ctx):
    return parse(C.get_text(src["url"]), src)
