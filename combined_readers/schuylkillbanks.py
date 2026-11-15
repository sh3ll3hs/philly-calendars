"""
Schuylkill Banks (Schuylkill River Development Corporation) — events reader.

Source: https://www.schuylkillbanks.org/events/upcoming-events  (Drupal 11, server-rendered).
The site has no feed, no JSON:API (/jsonapi answers 404) and no schema.org data, and the
built-in `text` method reads nothing from it (cards write the date as "Fri 13 Nov").

Listing (one request per run): month headings `<h3>November 2026</h3>` followed by cards
(`node--type-event`) that carry the title, the series ("Community Events", "Movie Nights"),
the time as text ("2:00PM- 4:00PM" or "1:00PM"), the day ("Fri 13 Nov"), an optional
"Through November 15" line for multi-day events and canceled / sold-out fields.

Event pages (at most 12 new ones per run, cached for a week in ctx["detail"]): the place
(`field--field-location-description`, e.g. "Fairmount Water Works, 640 Waterworks Dr,
Philadelphia, PA 19130"), the description, and the closing day of a long run that the card
does not state ("Saturday, September 19 at 10:00am to Friday, January 8 at 10:00am").

Checked on 2026-11-15 against the site: Schuylkill Crossing Ribbon Cutting Ceremony
(Fri Nov 13, 2:00pm to 4:00pm, Grays Ferry Crescent Esplanade), Handmade Holidays at
Bartram's Garden (Sat Dec 5, 12:00PM-3:00PM) and ENIAC Endless Loop Walk (Sat Dec 12,
9:00AM-4:00PM) match the listing and their event pages.

Known failure modes:
  * Times are taken from the visible text only. The `<time datetime>` attribute on event
    pages is right for the start (true UTC) but wrong for the end (local wall time marked
    "Z"), so it is used for nothing but the year of a closing day.
  * The year comes from the month heading above a card; a card with no heading is skipped
    rather than guessed.
  * A card whose time text has no clock time becomes an all-day event.
  * An event with no end time gets the feed's default length; one that spans two days
    ("Through November 15") is one entry from the first day's start to the last day's end.
  * An event page that fails to load leaves that event without a location until the next run.
  * If the theme's class names change (`node--type-event`, `field--node-title`,
    `field--dynamic-token-fieldnode-event-time`, `field--date-start`) the reader returns nothing.
"""
import datetime as dt
import html
import re
import urllib.parse

import combined_to_ics as C

MAX_NEW_PAGES = 12
TTL_DAYS = 7
MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}

HEAD_RX = re.compile(r"<h3>\s*([A-Za-z]+)\s+(20\d{2})\s*</h3>")
CARD_RX = re.compile(r'<div class="card card--[^"]*\bnode--type-event\b[^"]*">')
TOKEN_RX = re.compile(HEAD_RX.pattern + "|" + CARD_RX.pattern)


def _field(chunk, cls):
    """Visible text of the first `field--<cls>` block in a chunk of markup."""
    m = re.search(r'class=["\']field field--%s\b[^"\']*["\'][^>]*>(.*?)</div>' % re.escape(cls), chunk, re.S)
    return C.clean(re.sub(r"<[^>]+>", " ", m.group(1))) if m else ""


def _month(word):
    return MONTHS.get(str(word or "")[:3].lower())


def parse_detail(body):
    """Event page -> {"loc", "desc", "end"}; `end` is the closing day (a date) when the
    page shows the event ending on a different day than it starts, else None."""
    out = {"loc": "", "desc": "", "end": None}
    m = re.search(r'field--field-location-description\b[^>]*>(.*?)</div>', body, re.S)
    if m:
        lines = [C.clean(re.sub(r"<[^>]+>", " ", x)) for x in re.split(r"<br\s*/?>|</p>", m.group(1), flags=re.I)]
        out["loc"] = ", ".join(x for x in lines if x)
    m = re.search(r'class="field field--body\b[^>]*>(.*?)</div>', body, re.S)
    if m:
        out["desc"] = C.text(m.group(1))
    m = re.search(r'class="end-date"[^>]*>\s*<time[^>]*datetime="(\d{4})-(\d{2})-(\d{2})[^"]*"[^>]*>([^<]*)</time>', body, re.S)
    if m:
        d = re.search(r"\b([A-Z][a-z]{2,8})\.?\s+(\d{1,2})\b", m.group(4))
        if d and _month(d.group(1)):
            # month and day from the visible text; the attribute only decides the year
            near = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            best = None
            for year in (near.year - 1, near.year, near.year + 1):
                try:
                    cand = dt.date(year, _month(d.group(1)), int(d.group(2)))
                except ValueError:
                    continue
                if best is None or abs(cand - near) < abs(best - near):
                    best = cand
            out["end"] = best
    return out


def parse(body, src, details=None):
    """Listing page -> events. `details` maps an event URL to what parse_detail read
    from that page (location, description, closing day); without it events carry
    only what the listing shows."""
    details = details or {}
    start_at = body.find("view-display-id-events_list")
    seg = body[start_at:] if start_at >= 0 else body
    stop = seg.find("</main")
    if stop >= 0:
        seg = seg[:stop]
    tokens = list(TOKEN_RX.finditer(seg))
    out, head = [], None
    for i, t in enumerate(tokens):
        if t.group(1):
            head = (_month(t.group(1)), int(t.group(2)))
            continue
        card = seg[t.end():tokens[i + 1].start() if i + 1 < len(tokens) else len(seg)]
        title = _field(card, "node-title")
        day = re.search(r'<span class="date">\s*(\d{1,2})\s*</span>', card)
        mon = re.search(r'<span class="month">\s*([A-Za-z]+)\s*</span>', card)
        if not title or not day or not mon or not _month(mon.group(1)) or not head or not head[0]:
            continue
        month, year = _month(mon.group(1)), head[1]
        if head[0] == 1 and month == 12:
            year -= 1
        elif head[0] == 12 and month == 1:
            year += 1
        try:
            date = dt.date(year, month, int(day.group(1)))
        except ValueError:
            continue
        canceled = _field(card, "field-canceled")
        if re.search(r"cancel", canceled, re.I):
            continue
        href = re.search(r'<a href="([^"]+)"', card)
        url = urllib.parse.urljoin(src["url"], html.unescape(href.group(1))) if href else src["url"]
        info = details.get(url) or {}
        last = info.get("end")
        if isinstance(last, dt.datetime):
            last = last.date()
        through = re.search(r"field--field-end-date['\"][^>]*>\s*Through\s+([A-Za-z]+)\.?\s+(\d{1,2})", card)
        if through and _month(through.group(1)):
            for y in (date.year, date.year + 1):
                try:
                    cand = dt.date(y, _month(through.group(1)), int(through.group(2)))
                except ValueError:
                    continue
                if cand >= date:
                    last = cand
                    break
        if last and last <= date:
            last = None
        notes = [x for x in (_field(card, "series"), _field(card, "field-sold-out"), canceled, info.get("desc")) if x]
        clock = C.clock_from_text(_field(card, "dynamic-token-fieldnode-event-time"))
        if clock:
            start = dt.datetime.combine(date, clock[0])
            end = dt.datetime.combine(last or date, clock[1]) if clock[1] else None
            if end and end <= start:
                end = None
            e = C.event(src, f"{url}|{date}", title, start, end, False, info.get("loc", ""), url, "\n\n".join(notes))
        else:
            e = C.event(src, f"{url}|{date}", title, date, last, True, info.get("loc", ""), url, "\n\n".join(notes))
        if e:
            out.append(e)
    return out


def read(src, ctx):
    body = C.get_text(src["url"])
    cache, today, opened, details = ctx["detail"], ctx["today"], 0, {}
    for e in parse(body, src):
        day = e["start"].date() if isinstance(e["start"], dt.datetime) else e["start"]
        if not (ctx["lo"] <= day <= ctx["hi"]) or e["url"] in details:
            continue
        c = cache.get(e["url"])
        if c and (today - dt.date.fromisoformat(c["fetched"])).days < TTL_DAYS:
            if c.get("events"):
                details[e["url"]] = C.unpack(c["events"][0])
        elif opened < MAX_NEW_PAGES:
            opened += 1
            try:
                info = parse_detail(C.get_text(e["url"]))
            except Exception as ex:
                if type(ex).__name__ == "BlockedError":      # a 403/406 stops the source; never worked around
                    raise
                continue
            cache[e["url"]] = {"fetched": today.isoformat(), "events": [C.pack(info)]}
            details[e["url"]] = info
    return parse(body, src, details)
