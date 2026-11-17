"""Out & Equal — workplace-inclusion events, read from outandequal.org/events/.

One request: https://outandequal.org/events/?_period=upcoming-events (robots.txt,
2026-11-17: only /wp-admin/ and /wp-content/uploads/ are disallowed). Each event is a
`<li class="wp-block-post ...">` card with the title link (`<h4><a href>`), the date
line `<span class="event-date__text">Wed, Nov 18 – 12:00 PM ET</span>` and the place
`<span class="event-location__text">Virtual</span>` (or "Manila, Philippines").

The date line has no year: the year is the first one, from this year on, in which the
date falls on the printed weekday. The clock time is used only when the line names its
time zone ("ET"); it is then moved to Eastern. A time with no zone letters makes the
event all-day with the printed line quoted in the description.

Registration is on each event's own page (many are for partner companies only), so
the feed's sign-up line points there.

Checked 2026-11-17: Quarterly Partner Learning Meetup (Wed, Nov 18, 12:00 PM ET,
Virtual), Signal Through the Noise December Webinar (Thu, Dec 10, 12:00 PM ET; its
own page says 12:00 PM Eastern / 9:00 AM Pacific).

Known failure modes: renamed `event-date__text` / `event-location__text` classes
return nothing; a date line in another shape ("Mar 9-11") is read as its first day.
"""
import datetime as dt
import html
import re
import urllib.parse

import combined_to_ics as C
from common import normalize
from combined_readers import qt_common as Q
from combined_readers import zones

DAY_RX = re.compile(r"(?:\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s+)?\b(" + Q.MONTHS + r")\s+(\d{1,2})(?:,?\s+(20\d{2}))?", re.I)
ZONE_RX = re.compile(r"\b(\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?)\s+(" + "|".join(zones.ABBR) + r")\b", re.I)
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _plain(s):
    return C.clean(re.sub(r"<[^>]+>", " ", s or ""))


def day_from(m, today):
    """A DAY_RX match -> date, taking the year from the text, else from the weekday."""
    mon, day = normalize.month_num(m.group(2)), int(m.group(3))
    if not mon:
        return None
    if m.group(4):
        try:
            return dt.date(int(m.group(4)), mon, day)
        except ValueError:
            return None
    want = WEEKDAYS.index(m.group(1).lower()[:3]) if m.group(1) else None
    for year in range(today.year, today.year + 3):
        try:
            d = dt.date(year, mon, day)
        except ValueError:
            continue
        if d < today - dt.timedelta(days=45):
            continue
        if want is None or d.weekday() == want:
            return d
    return None


def parse(body, src, today):
    out = []
    for block in re.split(r'<li\b[^>]*class="[^"]*\bwp-block-post\b', body)[1:]:
        t = re.search(r'<h[2-5][^>]*>\s*<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        when = re.search(r'class="event-date__text"[^>]*>(.*?)</span>', block, re.S)
        if not (t and when):
            continue
        line = _plain(when.group(1))
        days = [d for d in (day_from(m, today) for m in DAY_RX.finditer(line)) if d]
        if not days:
            continue
        where = re.search(r'class="event-location__text"[^>]*>(.*?)</span>', block, re.S)
        loc = Q.place(_plain(where.group(1))) if where else ""
        url = urllib.parse.urljoin(src["url"], html.unescape(t.group(1)))
        tags = [_plain(x) for x in re.findall(r'class="(?:tag tag--[^"]*|taxonomy-pill taxonomy-pill--event-type)"[^>]*>(.*?)</span>', block, re.S)]
        start, end, all_day, note = days[0], (days[-1] if days[-1] > days[0] else None), True, ""
        clock, zone = C.clock_from_text(DAY_RX.sub(" ", line)), ZONE_RX.search(line)
        if clock and zone and end is None:
            z = zones.ABBR[zone.group(2).upper()]
            st = dt.datetime.combine(days[0], clock[0])
            en = dt.datetime.combine(days[0], clock[1]) if clock[1] else None
            start, end, all_day = zones.to_ny(st, z), zones.to_ny(en, z) if en else None, False
        elif clock:
            note = f"Time as listed: {line}"
        desc = "\n\n".join(x for x in (", ".join(dict.fromkeys(x for x in tags if x)), note) if x)
        e = C.event(src, url, _plain(t.group(2)), start, end, all_day, loc, url, desc)
        if e:
            out.append(e)
    return out


def read(src, ctx):
    return parse(C.get_text(src["url"]), src, ctx["today"])
