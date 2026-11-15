"""
The Navy Yard (PIDC) — events reader.

Source: https://navyyard.org/events/ and the pages its `<link rel="next">` points to
(/events/page/2/ ...; 12 cards a page, at most 3 pages per run; robots.txt allows everything).
WordPress with its own `event` post type: the REST API (/wp-json/wp/v2/event) and the RSS
feed carry no event dates, event pages have no schema.org Event data, and there is no
calendar feed, so the server-rendered cards are the only source:

    <article class="... card-event ..." id="post-9986">
      <div class="card-event__date"><p>Nov</p><p>17</p></div>
      <p class="card-event__title">Navy Yard Running Club</p>
      <p class="card-event__location">Meet at Vincera Institute, 12th &amp; Constitution Avenue</p>
      <p class="card-event__time"><p>5:45 pm </p></p>          (or "5:30 pm — 6:30 pm")
      <p class="card-event__description">...</p>
      <a href="https://navyyard.org/events/navy-yard-running-club-24/" class="card-event__link">

Checked on 2026-11-15 against the site: Navy Yard Running Club (Tue Nov 17, 5:45 pm, Meet at
Vincera Institute, 12th & Constitution Avenue), Navy Yard Night @ the Flyers (the page's
"Featured Event" block prints it in full: "11/17/2026 7:00 pm"; Xfinity Mobile Arena) and
Camp Out for Hunger Drive (event page: "Oct 14, 12:00 pm — Nov 18, 4:00 pm", Multiple
Drop-off Locations).

Known failure modes:
  * THE YEAR IS INFERRED. Cards give only "Nov 17". The list runs in date order from
    events already under way to the furthest ahead, so the cards are read as one rising
    sequence (a jump back of more than a month, "Dec 30" then "Apr 24", starts the next
    year) and the starting year is the one that puts the most cards between a week ago
    and a year ahead. A listing that stops being in date order would be dated wrongly.
  * A card shows only the first day of a multi-day event (Camp Out for Hunger, Oct 14 to
    Nov 18, appears as Oct 14, 12:00-4:00 pm); the closing day is on the event page only
    and is not read.
  * A card with no readable clock time becomes an all-day event; one with only a start
    time gets the feed's default length.
  * Locations are the short names the site uses ("Marine Parade Grounds"), not street
    addresses.
  * If the theme's `card-event__*` classes change, the reader returns nothing.
"""
import datetime as dt
import html
import re
import urllib.parse

import combined_to_ics as C

MAX_PAGES = 3
MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
CARD_RX = re.compile(r'<article\b[^>]*class="[^"]*\bcard-event\b[^"]*"[^>]*>(.*?)</article>', re.S)
PART_RX = re.compile(r'class="card-event__(date|title|location|time|description|link)\b')


def _plain(s):
    return C.clean(re.sub(r"<[^>]+>", " ", s or ""))


def cards(body):
    """Listing HTML -> one dict per card, exactly as written (no year yet)."""
    out = []
    for m in CARD_RX.finditer(body):
        block = m.group(0)
        marks = list(PART_RX.finditer(block))
        part = {}
        for i, p in enumerate(marks):
            chunk = block[p.end():marks[i + 1].start() if i + 1 < len(marks) else len(block)]
            chunk = chunk[chunk.find(">") + 1:]                       # rest of the opening tag
            chunk = chunk[:chunk.rfind("<")] if "<" in chunk else chunk   # the next part's opening "<p" / "<a"
            part.setdefault(p.group(1), chunk)
        date = re.findall(r"<p[^>]*>\s*([^<]+?)\s*</p>", part.get("date", ""))
        href = re.search(r'<a\b[^>]*href="([^"]+)"[^>]*class="card-event__link', block) or \
            re.search(r'class="card-event__link[^"]*"[^>]*href="([^"]+)"', block)
        post = re.search(r'id="post-(\d+)"', block)
        if len(date) < 2 or not MONTHS.get(date[0][:3].lower()) or not date[1].isdigit():
            continue
        out.append({"month": MONTHS[date[0][:3].lower()], "day": int(date[1]), "title": _plain(part.get("title")),
                    "loc": _plain(part.get("location")), "time": _plain(part.get("time")),
                    "desc": _plain(part.get("description")), "url": html.unescape(href.group(1)) if href else "",
                    "id": post.group(1) if post else ""})
    return out


def _date(year, month, day):
    try:
        return dt.date(year, month, day)
    except ValueError:                                                # Feb 29 outside a leap year
        return None


def assign_years(rows, today):
    """Dates for cards listed in date order. Returns a list of dates (None where a card's day
    does not exist in its year)."""
    best = None
    for first in (today.year - 1, today.year, today.year + 1):
        year, prev, dates = first, None, []
        for r in rows:
            md = (r["month"], r["day"])
            if prev is None or md >= prev:
                prev = md
            elif (dt.date(2000, *prev) - dt.date(2000, *md)).days > 31:
                year, prev = year + 1, md                             # "Dec 30" then "Apr 24": the next year has begun
            # else: a card a few days out of order stays in the same year
            dates.append(_date(year, *md))
        near = sum(1 for d in dates if d and today - dt.timedelta(days=7) <= d <= today + dt.timedelta(days=366))
        if best is None or near > best[0]:
            best = (near, dates)
    return best[1] if best else []


def build(rows, src, today):
    out = []
    for r, day in zip(rows, assign_years(rows, today)):
        if not day or not r["title"]:
            continue
        url = urllib.parse.urljoin(src["url"], r["url"]) if r["url"] else src["url"]
        key = f"{r['id'] or url}|{day}"
        clock = C.clock_from_text(r["time"])
        if clock:
            start = dt.datetime.combine(day, clock[0])
            end = dt.datetime.combine(day, clock[1]) if clock[1] else None
            if end and end <= start:
                end = None
            e = C.event(src, key, r["title"], start, end, False, r["loc"], url, r["desc"])
        else:
            e = C.event(src, key, r["title"], day, None, True, r["loc"], url, r["desc"])
        if e:
            out.append(e)
    return out


def parse(body, src, today=None):
    """One listing page -> events. `today` anchors the year (defaults to the current date)."""
    return build(cards(body), src, today or dt.datetime.now().date())


def next_page(body, page_url):
    m = re.search(r'<link\b[^>]*rel=["\']next["\'][^>]*href=["\']([^"\']+)["\']', body) or \
        re.search(r'<link\b[^>]*href=["\']([^"\']+)["\'][^>]*rel=["\']next["\']', body)
    return urllib.parse.urljoin(page_url, html.unescape(m.group(1))) if m else ""


def read(src, ctx):
    rows, url, seen = [], src["url"], set()
    for _ in range(MAX_PAGES):
        if not url or url in seen:
            break
        seen.add(url)
        try:
            body = C.get_text(url)
        except Exception as ex:
            if not rows or type(ex).__name__ == "BlockedError":   # first page, or a 403/406: report it
                raise
            break
        rows += cards(body)
        url = next_page(body, url)
    return build(rows, src, ctx["today"])
