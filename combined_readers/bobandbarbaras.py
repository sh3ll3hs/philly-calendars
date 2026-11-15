"""
Bob & Barbara's Lounge (1509 South St) — events reader.

Source: https://www.bobandbarbaras.com/events  (Squarespace, but an ordinary text page,
not an Events collection: there is no feed, no JSON and no schema.org data, and the
built-in `text` method reads one wrong line from it, "CLOSED Thanksgiving").
One request per run; robots.txt allows the page.

The page is the bar's standing week, written out by hand under weekday headings:
    <h1>Monday: shakasounds</h1>   <p>Every 3rd Monday of the Month ... from 8 - 11 pm ...</p>
                                   <p>November 16</p> <p>December 21</p>
    <h1>Thursday: Miss Lisa Lisa's drag show</h1>  <p>... Two shows, 7:30 pm and 9:30 pm ...</p>
                                   <p>November 19</p> <p><a href="eventbrite...">7:30</a></p> <p><a ...>9:30</a></p>
                                   <p>November 26 CLOSED - Thanksgiving</p>
    <h1>Friday: The Crowd pleasers</h1>  <p>EVERY FRIDAY NIGHT</p> <p>9 pm - 1 am</p> <p>NO COVER!</p>
What the reader makes of it:
  * A section with written dates ("November 16") gives one event per date, at the time
    range the section states ("8 - 11 pm"), or all-day when the section states no time.
    Bare show times under a date ("7:30", "9:30") are read with the am/pm the section
    states for them ("7:30 pm and 9:30 pm") and link to that show's ticket page.
    A date marked CLOSED gives nothing.
  * A section with no dates that says "EVERY <WEEKDAY> ..." gives one event on each such
    weekday for the next 6 weeks (`"weeks"` in the source entry), at the stated hours,
    except on a date the page marks CLOSED and on a date another section under the same
    weekday heading lists by name (the Wednesday jam on a Dual Identity night).
  * "every 1st Saturday of the Month from 5 - 9 pm" inside a section whose dates fall on
    another weekday gives that monthly night too, over the same 6 weeks.
Standing nights are repeated from a standing statement, so their description says so.

Checked on 2026-11-15 against the page: ShakaSounds Mon Nov 16 "8 - 11 pm"; Mikey Mester
and Friends Wed Nov 18 "9 pm - 12 am"; Miss Lisa Lisa's Drag Show Thu Nov 19 7:30 and
9:30 pm, nothing on Nov 26 (CLOSED - Thanksgiving), Dec 3 again; The Crowd Pleasers every
Friday "9 pm - 1 am"; The 3 Notes every Saturday "9 pm - 1 am"; Karaoke every Sunday
"9 pm - 2 am"; Jason Jeffries (Dec 1) and June's EQ (Nov 24, Dec 29) with no time: all-day.

Known failure modes:
  * Hand-written page: a new layout, headings without a weekday, or dates written another
    way ("11/16") will drop events without an error. Compare with the page now and then.
  * Dates have no year; the year is inferred, and a date more than 75 days ahead is
    dropped as a leftover from a stale page.
  * A standing night is assumed to happen every week: a holiday closure that the page
    does not mark is not known here (the page asks visitors to check Instagram).
  * Headings are typed in odd case ("tHe 3 Notes"); the title uses the spelling from the
    section's own text when the name appears there, otherwise simple capitalisation
    ("June's EQ", "Miss Lisa Lisa's Drag Show").
  * Events that are only on Instagram or Eventbrite are not on this page.
"""
import calendar
import datetime as dt
import html
import re
from zoneinfo import ZoneInfo

import combined_to_ics as C

VENUE = "Bob & Barbara's Lounge, 1509 South St, Philadelphia, PA 19146"
WEEKS = 6                 # how far ahead a standing night is written out
MAX_AHEAD = 75            # days; a written date further out is taken for a stale leftover
LOOKBACK = 30
NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_WD = "(" + "|".join(NAMES) + ")"
_CLOCK = r"\d{1,2}(?::\d{2})?\s*(?:[ap]\.?m\.?)?\s*(?:-|–|—|to)\s*\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?"
TOKEN_RX = re.compile(r"<(h[1-4]|p)\b[^>]*>(.*?)</\1>", re.S | re.I)
HEAD_RX = re.compile(r"^" + _WD + r"s?\b\s*:?\s*(.*)$", re.I)
DATE_RX = re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b[\s,:-]*(.{0,60})$", re.I)
BARE_RX = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(?:([ap])\.?m\.?)?$", re.I)
STATED_RX = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\b", re.I)
WEEKLY_RX = re.compile(r"\bevery\s+" + _WD + r"\b", re.I)
MONTHLY_RX = re.compile(r"\bevery\s+(1st|first|2nd|second|3rd|third|4th|fourth|last)\s+" + _WD
                        + r"\s+of\s+(?:the|every|each)\s+month\s+from\s+(" + _CLOCK + ")", re.I)
ORDINAL = {"1st": 0, "first": 0, "2nd": 1, "second": 1, "3rd": 2, "third": 2, "4th": 3, "fourth": 3, "last": -1}
SMALL = {"a", "an", "and", "at", "by", "for", "in", "of", "on", "or", "the", "to", "w/", "with"}
CLOSED_RX = re.compile(r"closed|cancel|no show", re.I)


def _plain(markup):
    s = re.sub(r"<[^>]+>", " ", markup)
    s = re.sub(r"\s+", " ", html.unescape(s)).strip()
    return re.sub(r"\s+([,.!?;:])", r"\1", s)


def _sections(body):
    """The page as [{"weekday", "name", "paras": [(text, [links])]}], in page order."""
    cut = body.find("<footer")
    out, weekday = [], None
    for t in TOKEN_RX.finditer(body if cut < 0 else body[:cut]):
        txt = _plain(t.group(2))
        if not txt:
            continue
        if t.group(1).lower() != "p":
            m = HEAD_RX.match(txt)
            if m:
                weekday = NAMES.index(m.group(1).lower())
            if weekday is None:
                continue                                    # site title and anything above the first weekday
            out.append({"weekday": weekday, "name": (m.group(2) if m else txt).strip(" :"), "paras": []})
        elif out:
            links = [html.unescape(h) for h in re.findall(r'<a\b[^>]*href="([^"]+)"', t.group(2))]
            out[-1]["paras"].append((txt, links))
    return out


def _title(sec):
    name = sec["name"]
    text = " ".join(t for t, _ in sec["paras"])
    if not name:
        day = NAMES[sec["weekday"]].capitalize()
        return f"{day} Jam Session" if re.search(r"jam session", text, re.I) else f"{day} Night"
    for m in re.finditer(re.escape(name), text, re.I):       # the section's own text usually spells it properly
        found = m.group(0)
        if found[:1].isupper() and found != found.upper():
            return found
    words = []
    for i, w in enumerate(name.split()):
        if w != w.lower() and w[:1].isupper():
            words.append(w)                                  # already capitalised ("Lisa", "Lisa’s")
        elif i and w.lower() in SMALL:
            words.append(w.lower())
        elif len(w) <= 2 and w.isalpha():
            words.append(w.upper())                          # "eq", "dj"
        else:
            words.append(w[:1].upper() + w[1:].lower())
    return " ".join(words)


def _nth_weekday(year, month, weekday, n):
    """n = 0 for the first such weekday of the month, -1 for the last; None if there is none."""
    hits = [d for d in calendar.Calendar().itermonthdates(year, month) if d.month == month and d.weekday() == weekday]
    return hits[n] if -len(hits) <= n < len(hits) else None


def parse(body, src, today=None):
    """The events page -> events. `today` (a date) anchors the year of written dates and
    the weeks a standing night is written out for; it defaults to the current day."""
    today = today or dt.datetime.now(ZoneInfo("America/New_York")).date()
    horizon = today + dt.timedelta(days=7 * int(src.get("weeks", WEEKS)))
    venue, page = src.get("venue") or VENUE, src["url"]
    secs = _sections(body)
    closed, named = set(), {}                                # named: weekday heading -> dates listed by name
    for sec in secs:
        sec["dated"], last = [], None
        for txt, links in sec["paras"]:
            m = DATE_RX.match(txt)
            if m:
                day = C.normalize.infer_year(C.normalize.month_num(m.group(1)), int(m.group(2)), today, LOOKBACK)
                last = {"date": day, "closed": bool(CLOSED_RX.search(m.group(3))), "shows": []}
                if day and day <= today + dt.timedelta(days=MAX_AHEAD):
                    sec["dated"].append(last)
                    if last["closed"]:
                        closed.add(day)
                    else:
                        named.setdefault(sec["weekday"], set()).add(day)
                continue
            b = BARE_RX.match(txt)
            if b and last is not None:
                last["shows"].append((b, links[0] if links else ""))
            else:
                last = None
    out = []
    for sec in secs:
        paras = [t for t, _ in sec["paras"]]
        if not paras:
            continue
        text = " ".join(paras)
        title = _title(sec)
        span = next((c for c in map(C.clock_from_text, paras) if c and c[1]), None) \
            or next((c for c in map(C.clock_from_text, paras) if c), None)
        stated = {(int(m.group(1)), int(m.group(2) or 0)): m.group(3).lower() for m in STATED_RX.finditer(text)}
        prose = [t for t in paras if len(t) > 40 and not DATE_RX.match(t)][:2]
        if re.search(r"\bno cover\b", text, re.I) and not any(re.search(r"\bno cover\b", t, re.I) for t in prose):
            prose.append("NO COVER!")
        desc = "\n\n".join(prose)

        def add(key, day, clock, url="", note=""):
            d = desc + ("\n\n" + note if note else "")
            if clock:
                start = dt.datetime.combine(day, clock[0])
                end = dt.datetime.combine(day, clock[1]) if clock[1] else None
                if end and end <= start:
                    end += dt.timedelta(days=1)              # "9 pm - 1 am"
                e = C.event(src, key, title, start, end, False, venue, url or page, d)
            else:
                e = C.event(src, key, title, day, None, True, venue, url or page, d)
            if e:
                out.append(e)

        for item in sec["dated"]:
            day = item["date"]
            if item["closed"]:
                continue
            shows = []
            for b, link in item["shows"]:
                hour, minute = int(b.group(1)), int(b.group(2) or 0)
                half = (b.group(3) or stated.get((hour, minute), "")).lower()
                if not half or hour > 12:
                    shows = None                             # a bare "7:30" the section never explains: no time
                    break
                shows.append((dt.time(hour % 12 + (12 if half == "p" else 0), minute), link))
            if shows:
                for clock, link in shows:
                    add(f"{title}|{day}|{clock:%H%M}", day, (clock, None), link)
            elif item["shows"] and shows is None:
                add(f"{title}|{day}", day, None)
            else:
                add(f"{title}|{day}", day, span)
        if not sec["dated"]:
            m = WEEKLY_RX.search(text)
            if m:
                weekday = NAMES.index(m.group(1).lower())
                note = f"A standing night on the events page (“{m.group(0)}”), not a dated listing."
                day = today + dt.timedelta(days=(weekday - today.weekday()) % 7)
                while day <= horizon:
                    if day not in closed and day not in named.get(sec["weekday"], ()):
                        add(f"{title}|{day}", day, span, note=note)
                    day += dt.timedelta(days=7)
        own_days = {i["date"].weekday() for i in sec["dated"] if i["date"]}
        for m in MONTHLY_RX.finditer(text):
            weekday, clock = NAMES.index(m.group(2).lower()), C.clock_from_text(m.group(3))
            if weekday in own_days or not clock:
                continue                                     # the section's written dates already cover it
            note = f"A standing night on the events page (“{m.group(0)}”), not a dated listing."
            for k in range(4):
                y, mo = divmod(today.month - 1 + k, 12)
                day = _nth_weekday(today.year + y, mo + 1, weekday, ORDINAL[m.group(1).lower()])
                if day and today <= day <= horizon and day not in closed:
                    add(f"{title}|{day}|{clock[0]:%H%M}", day, clock, note=note)
    return out


def read(src, ctx):
    return parse(C.get_text(src["url"]), src, ctx["today"])
