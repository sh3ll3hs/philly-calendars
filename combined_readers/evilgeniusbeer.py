"""
Evil Genius Beer Company — events reader.

Source: https://evilgeniusbeer.com/calendar/  (one request per run; robots.txt allows it).
WordPress with a custom `events` post type. Its REST route (/wp-json/wp/v2/events, 876 posts)
has no event date in any field (only empty Event Tickets fields), The Events Calendar's own
API is not installed (404), and there is no feed or schema.org data, so the server-rendered
calendar page is the only source. It has four sections, each an `<h2 class="eg-events__cat-name">`
("Festivals", "Samplings", "Events At The Lab", "Bar Events") followed by items:

    <div class="eg-events__event-item" [data-events-display]>
      <span class="eg-events__event-item-weekday">Sunday</span>
      <span class="eg-events__event-item-date">11/ 15</span>
      <h3 class="eg-events__event-item-name">May The Brunch Be Ever In Your Favor</h3>
      <span class="eg-events__event-item-time">11:00 AM - 2:00 PM</span>
      <div class="eg-events__event-item-details-details-container"> ...description, ticket links... </div>

(items marked `data-events-display` are the ones behind the page's "show more" button; they
are in the HTML and are read too).

Checked on 2026-11-15 against the page: May The Brunch Be Ever In Your Favor (Sunday 11/15,
11:00 AM - 2:00 PM; its ticket link is dated 2026-11-15), Live Band Karaoke (Friday 11/20,
8:00 PM - 11:00 PM), PowerPop Girls Drag Brunch (Sunday 1/10, 11:00 AM - 2:00 PM; ticket
link dated 2027-01-10). The reference calendar had the Friday 8 PM shows at 7 PM; it ran
one hour early on every site in this batch where an event could be compared.

Known failure modes:
  * No year on the page. The year is worked out from the weekday printed beside the date
    ("Sunday 11/15" is 2026; within three neighbouring years only one fits). If the weekday
    is missing or fits no year, the next such date is assumed.
  * A time range the site prints backwards within a day ("11:00 PM - 2:00 PM" for a brunch
    on 11/22) is not guessed at: the event becomes all-day and the description starts with
    the time as printed. A range that runs past midnight ("9:00 PM - 1:00 AM") ends the next day.
  * Location: the page gives none per event. Items under "Events At The Lab" get the brewery
    (`lab_venue` in the source entry; the site's footer prints "1727 Front Street
    Philadelphia, PA 19122", and the street is N Front St). Items under the other sections
    (festivals, samplings, bar events are elsewhere) get no location and the section name
    in the description. Those three sections were empty when this was written, so their
    markup is assumed to match the Lab's.
  * Events have no pages of their own in the list, so every event links to the calendar page.
  * If the theme's `eg-events__*` classes change, the reader returns nothing.
"""
import datetime as dt
import re

import combined_to_ics as C

LAB_SECTION = "events at the lab"
LAB_VENUE = "Evil Genius Beer Company, 1727 N Front St, Philadelphia, PA 19122"
WEEKDAYS = {d: i for i, d in enumerate("mon tue wed thu fri sat sun".split())}
TOKEN_RX = re.compile(r'<h2\b[^>]*class="eg-events__cat-name"[^>]*>(.*?)</h2>|'
                      r'<div\b[^>]*class="eg-events__event-item(?:\s[^"]*)?"[^>]*>', re.S)


def _plain(s):
    return C.clean(re.sub(r"<[^>]+>", " ", s or ""))


def _field(block, name):
    m = re.search(r'class="eg-events__event-item-%s"[^>]*>(.*?)</(?:span|h3)>' % name, block, re.S)
    return _plain(m.group(1)) if m else ""


def day_for(weekday, month, day, today):
    """The date a "Sunday 11/15" means: the neighbouring year in which it is a Sunday."""
    want = WEEKDAYS.get(weekday[:3].lower())
    if want is not None:
        for year in (today.year, today.year + 1, today.year - 1):
            try:
                d = dt.date(year, month, day)
            except ValueError:
                continue
            if d.weekday() == want:
                return d
    return C.normalize.infer_year(month, day, today)


def parse(body, src, today=None):
    """Calendar page HTML -> events. `today` only matters for a date printed without a
    usable weekday (defaults to the current date)."""
    today = today or dt.datetime.now().date()
    tokens = list(TOKEN_RX.finditer(body))
    out, section = [], ""
    for i, t in enumerate(tokens):
        if t.group(1) is not None:
            section = _plain(t.group(1))
            continue
        block = body[t.end():tokens[i + 1].start() if i + 1 < len(tokens) else len(body)]
        title = _field(block, "name")
        md = re.match(r"^(\d{1,2})\s*/\s*(\d{1,2})$", _field(block, "date"))
        if not title or not md:
            continue
        day = day_for(_field(block, "weekday"), int(md.group(1)), int(md.group(2)), today)
        if not day:
            continue
        at_lab = section.lower() == LAB_SECTION
        loc = src.get("lab_venue", LAB_VENUE) if at_lab else ""
        details = re.search(r'class="eg-events__event-item-details-details-container"[^>]*>(.*)', block, re.S)
        notes = [] if at_lab or not section else [section]
        printed = _field(block, "time")
        clock = C.clock_from_text(printed)
        start = end = None
        if clock:
            start = dt.datetime.combine(day, clock[0])
            end = dt.datetime.combine(day, clock[1]) if clock[1] else None
            if end and end <= start:
                if clock[1].hour < 12:
                    end += dt.timedelta(days=1)                     # "9:00 PM - 1:00 AM"
                else:
                    start = end = None                              # "11:00 PM - 2:00 PM": not a time to trust
                    notes.append(f"Time as printed on the site: {printed}")
        desc = "\n\n".join(notes + ([C.text(details.group(1))] if details else []))
        key = f"{title}|{day}|{printed}"
        if start:
            e = C.event(src, key, title, start, end, False, loc, src["url"], desc)
        else:
            e = C.event(src, key, title, day, None, True, loc, src["url"], desc)
        if e:
            if not at_lab:
                e["loc"] = ""                                       # never the brewery for an event held elsewhere
            out.append(e)
    return out


def read(src, ctx):
    return parse(C.get_text(src["url"]), src, ctx["today"])
