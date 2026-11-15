"""
Delaware River Waterfront Corporation (delawareriverwaterfront.com) — events reader.

Human page: https://www.delawareriverwaterfront.com/what-to-do  (Apostrophe CMS, cards with a
date and a place name but no time and no year). The site has no robots.txt (404).

Source read here, one request per run: the page's own RSS view
    https://www.delawareriverwaterfront.com/what-to-do?feed=rss
Each item is one event: title, link, and a description that opens with a heading holding the
start and end exactly as the site prints them, e.g.
    <h4> Nov 27  11:00 am  &ndash;  Nov 29  11:00 pm </h4>
    <h4> Feb 13 '27  7:00 pm  &ndash;  Feb 13 '27  10:30 pm </h4>
A date carries a two-digit year only when it is not in the current year, so a date without
one is read as the year the feed was built (<lastBuildDate>).

Event pages (at most 12 new ones per run, cached for a week in ctx["detail"]) are opened only
for the location: the "Place: ..." line and the street address the page's "Add to Google
Calendar" link carries (location=101 South Columbus Boulevard, Philadelphia, PA 19106).

Checked on 2026-11-15, feed against event pages (visible text and the UTC instants in their
Google Calendar links): Holiday Tree Lighting (Sun Nov 29, 5:00 pm to 8:00 pm; link
20261129T220000Z/20261130T010000Z), Opening Weekend: RiverRink Winterfest (11/27 to 11/29,
11:00 am to 11:00 pm; link 20261127T160000Z/20261130T040000Z) and the Valentine's Day Fire &
Ice Party (Sat Feb 13 2027, 7:00 pm to 10:30 pm; link 20270214T000000Z/...) all agree.

Known failure modes:
  * An end that is not after the start ("Dec 31 6:00 pm - Dec 31 12:30 am": the site keeps
    the start's date for an end past midnight) is moved to the next day.
  * A heading with a date but no clock time is an all-day entry.
  * A run of several days is one entry (first day's start to last day's end); the feed shows
    it on its first day as "(through <last day>)". Weekly classes published as one long run
    (the summer yoga series) therefore appear once, on their first day, and not at all once
    that day is more than three days past.
  * An event with no "Place:" on its page (New Year's Eve fireworks) has no location; an
    event page that fails to load leaves the location empty until the next run.
  * Only 4 events were listed when this was written; the page has a "load more" control, and
    whether the RSS view returns more than its first page in summer is untested.
  * The per-event iCal link (/apos-events/vcal?slug=...) and the Google link repeat the same
    instants, so they are not read separately.
"""
import datetime as dt
import email.utils
import html
import re
import urllib.parse

import combined_to_ics as C

MAX_NEW_PAGES = 12
TTL_DAYS = 7
MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
DATE_RX = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:,?\s+(?:['’](\d{2})|(20\d{2})))?(?!\s*:|\d)")
CLOCK_RX = re.compile(r"\b(\d{1,2}):(\d{2})\s*([ap])\.?m\b", re.I)


def _tag(item, name):
    m = re.search(r"<%s\b[^>]*>(.*?)</%s>" % (name, name), item, re.S)
    if not m:
        return ""
    s = m.group(1).strip()
    c = re.match(r"^<!\[CDATA\[(.*)\]\]>$", s, re.S)
    return c.group(1) if c else html.unescape(s)


def _moment(part, year):
    """'Nov 27 11:00 am' / "Feb 13 '27 7:00 pm" / 'Nov 27' -> (date, time or None)."""
    d = DATE_RX.search(part)
    if not d or d.group(1)[:3].lower() not in MONTHS:
        return None, None
    y = 2000 + int(d.group(3)) if d.group(3) else int(d.group(4)) if d.group(4) else year
    try:
        day = dt.date(y, MONTHS[d.group(1)[:3].lower()], int(d.group(2)))
    except ValueError:
        return None, None
    t = CLOCK_RX.search(part[d.end():])
    if not t or not 1 <= int(t.group(1)) <= 12 or int(t.group(2)) > 59:
        return day, None
    return day, dt.time(int(t.group(1)) % 12 + (12 if t.group(3).lower() == "p" else 0), int(t.group(2)))


def parse(body, src, today=None):
    """The RSS view -> events (no locations; read() adds those from event pages)."""
    today = today or dt.date.today()
    year = today.year
    built = re.search(r"<lastBuildDate>([^<]+)</lastBuildDate>", body)
    if built:
        try:
            year = C.local(email.utils.parsedate_to_datetime(built.group(1).strip())).year
        except (TypeError, ValueError):
            pass
    root = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(src["url"]))
    out = []
    for item in re.findall(r"<item>(.*?)</item>", body, re.S):
        title, desc = _tag(item, "title"), _tag(item, "description")
        link = _tag(item, "link").strip()
        head = re.search(r"<h4[^>]*>(.*?)</h4>", desc, re.S)
        if not title or not head:
            continue
        when = C.clean(re.sub(r"<[^>]+>", " ", head.group(1)))
        halves = re.split(r"\s+[–—-]\s+", when, maxsplit=1)
        day, clock = _moment(halves[0], year)
        if not day:
            continue
        last, last_clock = _moment(halves[1], year) if len(halves) > 1 else (None, None)
        url = urllib.parse.urljoin(root + "/", urllib.parse.urlsplit(link).path) if link else src["url"]
        key = _tag(item, "guid").strip() or url
        text = C.text(desc[head.end():])
        if clock:
            st = dt.datetime.combine(day, clock)
            en = dt.datetime.combine(last or day, last_clock) if last_clock else None
            if en and en <= st:
                en += dt.timedelta(days=1)          # "6:00 pm - 12:30 am" printed with the start's date
            e = C.event(src, key, title, st, en, False, "", url, text)
        else:
            e = C.event(src, key, title, day, last if last and last > day else None, True, "", url, text)
        if e:
            out.append(e)
    return out


def parse_detail(body):
    """Event page -> {"loc": "Place name, street address"} ('' when the page names neither)."""
    head = body.find('class="event-meta-info"')
    seg = body[head:body.find("</header>", head)] if head >= 0 else ""
    place = ""
    m = re.search(r'<li class="icon location">(.*?)</li>', seg, re.S)
    if m:
        place = re.sub(r"^\s*Place:\s*", "", C.clean(re.sub(r"<[^>]+>", " ", m.group(1))))
    addr = ""
    m = re.search(r'href="([^"]*google\.com/calendar/event[^"]*)"', seg)
    if m:
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(html.unescape(m.group(1))).query)
        addr = C.clean((q.get("location") or [""])[0])
    return {"loc": C.address({"name": place, "address": addr}) if place or addr else ""}


def read(src, ctx):
    events = parse(C.get_text(src.get("feed") or src["url"].split("?")[0] + "?feed=rss"), src, ctx["today"])
    cache, today, opened = ctx["detail"], ctx["today"], 0
    for e in events:
        day = e["start"].date() if isinstance(e["start"], dt.datetime) else e["start"]
        if not (ctx["lo"] <= day <= ctx["hi"]):
            continue
        c = cache.get(e["url"])
        if not (c and (today - dt.date.fromisoformat(c["fetched"])).days < TTL_DAYS) and opened < MAX_NEW_PAGES:
            opened += 1
            try:
                info = parse_detail(C.get_text(e["url"]))
            except Exception as ex:
                if type(ex).__name__ == "BlockedError":      # a 403/406 stops the source; never worked around
                    raise
                info = None
            if info is not None:
                c = cache[e["url"]] = {"fetched": today.isoformat(), "events": [C.pack(info)]}
        if c and c.get("events") and c["events"][0].get("loc"):
            e["loc"] = c["events"][0]["loc"]
    return events
