"""
Curtis Institute of Music — performance calendar reader.

Source: https://www.curtis.edu/wp-json/curtis/v1/events  (one request per run, about 640 KB)
This is the JSON the site's own calendar page (https://www.curtis.edu/curtis-performances/calendar/)
loads in the browser: the page's script calls `${curtisCalendar.apiurl}/events`. robots.txt
disallows only search URLs. The answer is {"success": true, "data": [...]} with EVERY event
since 2017 (about 1,350); each has `title`, `date`, `datetime` (local wall time, no offset),
`time` ("7:30 p.m."), `venue` (a name such as "Curtis Institute of Music, Field Concert
Hall"; no street address), `categories` (slugs) and `url`. The endpoint takes no filters,
so `read` keeps the feed's window and drops the rest.

No built-in method fits: the calendar page is an empty React shell and the site has no
feed; single event pages do carry schema.org data, but the `html` method would open 12
pages a run to learn what this one request already says.

Checked on 2026-11-15 against the event pages and the "Upcoming Events" cards on them:
  Bowen, Prokofiev, and more        Nov 13, 2026, 7:30 p.m., Curtis Institute of Music, Field Concert Hall
  Bach, Brahms, and Schubert        Mon Nov 16 @ 7:30 p.m.   (Student Recital, Free)
  Strauss, Dowland, and more        Wed Nov 18 @ 5:00 p.m.
  Mozart, Prokofiev, and more       Fri Nov 20 @ 7:30 p.m.
The event page's schema.org startDate ("2026-11-13T19:30:00") equals the API's `datetime`.

Choices made here (change them in the source entry's "params" if they are wrong for you):
  * "curtis-on-tour" events are left out: they are out of town (North Carolina, Germany,
    Spain) and their times are local to the venue, not to Philadelphia.
    "params": {"skip": []} keeps them; any list of category slugs can be skipped.
  * A student recital whose title is only its programme ("Bach, Brahms, and Schubert")
    gets the site's own category label in front: "Student Recital: Bach, Brahms, and
    Schubert". Titles that already say "recital" or have a colon are left alone.
    "params": {"label": false} turns this off.

Known failure modes:
  * An item with no `time`, or with "12:00 a.m." (how the site stores "no time": on-demand
    and all-month items), becomes an all-day event; no time is guessed.
  * No end time is published; the feed's default length applies.
  * "YouTube" as the venue is an online broadcast and is passed through as written.
  * If the theme is rebuilt the endpoint may move; the source then reports an error
    (the path is named in the calendar page's `curtisCalendar.apiurl`).
"""
import datetime as dt
import json
import re
import urllib.parse

import combined_to_ics as C

SITE = "https://www.curtis.edu"
SKIP = ["curtis-on-tour"]
LABELS = {"free": "Free", "broadcast": "Livestream"}       # the words the site's cards use


def _label(slug):
    return LABELS.get(slug) or " ".join(w.capitalize() for w in str(slug).split("-"))


def parse(body, src):
    """The whole API answer -> events (every year; `read` applies the window)."""
    data = json.loads(body)
    items = data.get("data") if isinstance(data, dict) else data
    params = src.get("params") or {}
    skip = set(params["skip"] if isinstance(params.get("skip"), list) else SKIP)
    label = params.get("label", True)
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        cats = [c for c in it.get("categories") or [] if isinstance(c, str)]
        if skip.intersection(cats):
            continue
        title = C.clean(re.sub(r"<[^>]+>", "", str(it.get("title") or "")))
        when, clock = str(it.get("datetime") or ""), str(it.get("time") or "").strip()
        timed = bool(clock) and not clock.startswith("12:00 a") and "T" in when and not when.endswith("T00:00:00")
        st = C.parse_iso(when if timed else (it.get("date") or when[:10]))
        if not title or not st:
            continue
        if label and "student-recital" in cats and ":" not in title and "recital" not in title.lower():
            title = "Student Recital: " + title
        path = str(it.get("url") or "")
        url = urllib.parse.urljoin(SITE, path) if path else src.get("page") or SITE
        e = C.event(src, it.get("id") or url, title, st[0], None, st[1], it.get("venue") or "", url,
                    ", ".join(_label(c) for c in cats))
        if e:
            out.append(e)
    return out


def _day(e):
    return e["start"].date() if isinstance(e["start"], dt.datetime) else e["start"]


def read(src, ctx):
    return [e for e in parse(C.get_text(src["url"]), src) if ctx["lo"] <= _day(e) <= ctx["hi"]]
