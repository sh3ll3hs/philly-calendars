"""Out in Tech — chapter events, read from outintech.com/events/ and each event's page.

List page (and /events/page/2/ ... while the page links to a next one, 4 pages at
most): one `<div class="single__post">` per event with the date `<h6>11.17.2026</h6>`,
title `<h3>`, a one-line blurb `<p>`, the address `<span class="link--location">` and
the link to the event page. The list gives no clock time.

Event page (opened once, kept for a week in the state file, at most "detail_max" new
pages per run, default 30): `<h4>November 17, 2026 5:30 pm - 7:30 pm</h4>`, the
sign-up link `<a ...>Register</a>` (Eventbrite or events.outintech.com) and
`<small>Venue:</small><p>address</p>`.

The clock time is local to the venue, so it is moved to Eastern by the address's time
zone (combined_readers/zones.py). When the zone cannot be told from the address (a
virtual event, an address with no state or country), or the event page has not been
read yet, the event is all-day and the printed time is quoted in the description.

robots.txt (2026-11-17): /events/ and /event/ are not disallowed. The site's
/wp-json/tribe/ API answers but is empty (events are a custom post type).

Not read: the same page also embeds an Accelevents widget (events.outintech.com),
drawn by script from that service's own API, where the organization now posts part
of its events. It has no feed and no page a script can read, so those events are
missing here; the list's "We've Moved!" placeholder entry is dropped by the registry
entry's "skip". Only the "Upcoming" part of the list has titles in <h3>; the "Past
Events" part is ignored.

Checked 2026-11-17 against the site: Out in Tech Denver November Monthly Mixer
(Nov 17, 5:30-7:30 pm at 525 Santa Fe Dr., Denver; its Eventbrite page gives
17:30-07:00, the same instant as 7:30 PM Eastern).

Known failure modes: a renamed `single__post` / `link--location` class or a moved
`<h4>` returns nothing or all-day events; an event edited after its page was read
keeps the old time for up to a week.
"""
import datetime as dt
import html
import re
import urllib.parse

import combined_to_ics as C
from combined_readers import qt_common as Q
from combined_readers import zones

MAX_PAGES = 4
DATE_WORDS = re.compile(r"\b" + Q.MONTHS + r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s+20\d{2}", re.I)


def _plain(s):
    return C.clean(re.sub(r"<[^>]+>", " ", s or ""))


def parse_list(body, src):
    """List page -> [{day, title, blurb, loc, url}] in page order."""
    out = []
    for block in re.split(r'<div\b[^>]*class="[^"]*\bsingle__post\b[^"]*"[^>]*>', body)[1:]:
        end = re.search(r'class="link--more"[^>]*>.*?</a>', block, re.S)      # a card ends with "View Event Page"
        block = block[:end.end()] if end else block[:900]                     # (the last card runs on into the footer)
        d = re.search(r"<h6[^>]*>\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*</h6>", block)
        t = re.search(r"<h3[^>]*>(.*?)</h3>", block, re.S)
        a = re.search(r'<a\b[^>]*href="([^"]+)"', block)
        if not (d and t and a):
            continue
        try:
            day = dt.date(int(d.group(3)), int(d.group(1)), int(d.group(2)))
        except ValueError:
            continue
        loc = re.search(r'class="[^"]*\blink--location\b[^"]*"[^>]*>(.*?)</span>', block, re.S)
        blurb = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
        out.append({"day": day, "title": _plain(t.group(1)), "blurb": _plain(blurb.group(1)) if blurb else "",
                    "loc": _plain(loc.group(1)) if loc else "",
                    "url": urllib.parse.urljoin(src["url"], html.unescape(a.group(1)))})
    return out


def next_page(body, n):
    m = re.search(r'href="([^"]*/events/page/%d/?)"' % (n + 1), body)
    return html.unescape(m.group(1)) if m else None


def parse_detail(body):
    """Event page -> {"when": the <h4> line, "rsvp": sign-up link, "venue": address}."""
    when = ""
    for h in re.findall(r"<h4[^>]*>(.*?)</h4>", body, re.S):
        if DATE_WORDS.search(_plain(h)):
            when = _plain(h)
            break
    rsvp = ""
    for href, label in re.findall(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', body, re.S):
        if Q.RSVP_TEXT.search(_plain(label)) and href.startswith("http"):
            rsvp = html.unescape(href)
            break
    v = re.search(r"<small[^>]*>\s*Venue:?\s*</small>\s*<p[^>]*>(.*?)</p>", body, re.S | re.I)
    return {"when": when, "rsvp": rsvp, "venue": _plain(v.group(1)) if v else ""}


def build(item, info, src):
    """One list entry plus (maybe) its event page -> a feed event."""
    loc = Q.place((info or {}).get("venue") or item["loc"])
    start, end, all_day, note = item["day"], None, True, ""
    clock = C.clock_from_text(DATE_WORDS.sub(" ", (info or {}).get("when", "")))
    if clock:
        st = dt.datetime.combine(item["day"], clock[0])
        en = dt.datetime.combine(item["day"], clock[1]) if clock[1] else None
        if en and en <= st:
            en += dt.timedelta(days=1)
        zone = zones.zone_for(loc)
        if zone:
            start, end, all_day = zones.to_ny(st, zone), zones.to_ny(en, zone) if en else None, False
        else:
            note = zones.unplaced(item["day"], st, en)
    desc = "\n\n".join(x for x in (item["blurb"], note) if x)
    return C.event(src, item["url"], item["title"], start, end, all_day, loc, item["url"], desc,
                   rsvp=(info or {}).get("rsvp", ""))


def read(src, ctx):
    items, url = [], src["url"]
    for n in range(1, MAX_PAGES + 1):
        try:
            body = C.get_text(url)
        except C.http.BlockedError:
            raise
        except Exception:
            if n == 1:
                raise
            break
        items += parse_list(body, src)
        url = next_page(body, n)
        if not url:
            break
    budget, out, seen = [int(src.get("detail_max", 30))], [], set()
    for it in items:
        if it["url"] in seen or not (ctx["lo"] <= it["day"] <= ctx["hi"]):
            continue
        seen.add(it["url"])
        e = build(it, Q.cached(ctx, it["url"], budget, parse_detail), src)
        if e:
            out.append(e)
    return out
