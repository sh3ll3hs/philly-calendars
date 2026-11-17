"""Independence Business Alliance (Greater Philadelphia's LGBTQ+ chamber of commerce) —
the event cards on the home page, https://thinkiba.com/ (one request; robots.txt
allows everything, 2026-11-17).

The chamber's full calendar is at members.thinkiba.com, which answers 403 to scripts,
so it is not read. The home page carries a card for each of the next few events:
    <p class="small">Thursday, November 19, 2026</p>
    <h4 class="card-title">November ConnX: with Philly Pride Visitor Center</h4>
    <div class="card-text"> ...blurb...
        <p>November 19, 2026<br>5:30 PM – 7:00 PM<br>Philly Pride Visitor Center<br>
           12th and Locust<br>Philadelphia, PA 19107</p></div>
    <div class="card-footer"><a href="https://members.thinkiba.com/ap/Events/Register/...">Learn More</a>
The time is the clock range in the card (Eastern: the chamber and its venues are in
the Philadelphia region); the place is the lines that follow the time; the link is
the registration page. A card with no clock range is an all-day event.

Checked 2026-11-17 against the page: November ConnX (Nov 19, 5:30-7:00 PM, Philly
Pride Visitor Center, 12th and Locust), Prosperity Planning Series (Nov 17,
12:00-1:00 PM, Zoom).

Known failure modes: only the events the home page shows are in the feed (three on
the day this was written); a card whose details paragraph is laid out differently
loses its place or, with no clock range, its time.
"""
import datetime as dt
import html
import re
import urllib.parse

import combined_to_ics as C
from common import normalize
from combined_readers import qt_common as Q

DATE_RX = re.compile(r"\b(" + Q.MONTHS + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})", re.I)
CLOCK_RX = re.compile(r"\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?", re.I)


def _plain(s):
    return C.clean(re.sub(r"<[^>]+>", " ", s or ""))


def parse(body, src):
    out = []
    for block in re.split(r'<div class="card">', body)[1:]:
        t = re.search(r'class="card-title"[^>]*>(.*?)</h\d>', block, re.S)
        d = DATE_RX.search(_plain((re.search(r'<p class="small">(.*?)</p>', block, re.S) or [None, ""])[1]))
        if not (t and d):
            continue
        try:
            day = dt.date(int(d.group(3)), normalize.month_num(d.group(1)), int(d.group(2)))
        except (TypeError, ValueError):
            continue
        body_html = (re.search(r'<div class="card-text">(.*?)</div>', block, re.S) or [None, ""])[1]
        paras = re.findall(r"<p[^>]*>(.*?)</p>", body_html, re.S)
        clock, loc = None, ""
        for p in paras:
            rows = [_plain(x) for x in re.split(r"<br\s*/?>", p)]
            hit = next((i for i, r in enumerate(rows) if CLOCK_RX.search(r) and len(r) < 40), None)
            if hit is None:
                continue
            clock = C.clock_from_text(rows[hit])
            where = [r for r in rows[hit + 1:] if r]
            loc = "Online (Zoom)" if where and re.match(r"\W*zoom\b", where[0], re.I) else Q.place(", ".join(where))
            break
        a = re.search(r'<div class="card-footer">.*?<a\b[^>]*href="([^"]+)"', block, re.S)
        link = urllib.parse.urljoin(src["url"], html.unescape(a.group(1))) if a else src["url"]
        blurb = next((_plain(p) for p in paras if len(_plain(p)) > 40 and not CLOCK_RX.search(_plain(p)[:60])), "")
        if clock:
            st = dt.datetime.combine(day, clock[0])
            en = dt.datetime.combine(day, clock[1]) if clock[1] else None
            e = C.event(src, f"{_plain(t.group(1))}|{day}", _plain(t.group(1)), st, en, False, loc, link, blurb, rsvp=link)
        else:
            e = C.event(src, f"{_plain(t.group(1))}|{day}", _plain(t.group(1)), day, None, True, loc, link, blurb, rsvp=link)
        if e:
            out.append(e)
    return out


def read(src, ctx):
    return parse(C.get_text(src["url"]), src)
