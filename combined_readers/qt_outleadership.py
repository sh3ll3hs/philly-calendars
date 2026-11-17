"""Out Leadership (LGBTQ+ business network) — summits and webinars listed on
outleadership.com/events/ (one request).

Each event is `<a href="https://outleadership.com/events/<slug>/" class="article js-ae">`
holding the title in `<h5>` and the date as three blocks, `<div class="month">Nov</div>
<div class="day">17</div><div class="year">2026</div>`. Past events stay on the page
(marked "Event Has Passed") and are dropped by the feed's date window.

The list gives no clock time, and an event's own page gives one without a time zone
("12:00 pm"), so every event is all-day: the date, the title and the link. Entries
with an empty title are skipped.

robots.txt (2026-11-17): for every agent only /wp-admin/ is disallowed.

Checked 2026-11-17 against the page: Virtual OutNEXT 2026 (Mar 01 2026), Global Town
Hall with John Flint and Ari Shaw (Oct 03 2025), 2025 Australia Summit (Oct 21 2025).

Known failure modes: renamed `article js-ae` / `month` / `day` / `year` classes
return nothing.
"""
import datetime as dt
import html
import re

import combined_to_ics as C
from common import normalize


def _plain(s):
    return C.clean(re.sub(r"<[^>]+>", " ", s or ""))


def parse(body, src):
    out = []
    for block in re.split(r'(?=<a\b[^>]*class="article js-ae\b)', body)[1:]:
        a = re.match(r'<a\b[^>]*href="([^"]+)"', block)
        t = re.search(r"<h5[^>]*>(.*?)</h5>", block, re.S)
        mon = re.search(r'class="month"[^>]*>(.*?)</div>', block, re.S)
        day = re.search(r'class="day"[^>]*>\s*(\d{1,2})\s*</div>', block, re.S)
        year = re.search(r'class="year"[^>]*>\s*(20\d{2})\s*</div>', block, re.S)
        title = _plain(t.group(1)) if t else ""
        if not (a and title and mon and day and year) or title.lower().startswith("http"):
            continue
        try:
            d = dt.date(int(year.group(1)), normalize.month_num(_plain(mon.group(1))), int(day.group(1)))
        except (TypeError, ValueError):
            continue
        cat = re.search(r'class="category"[^>]*>(.*?)</div>', block, re.S)
        url = html.unescape(a.group(1))
        e = C.event(src, url, title, d, None, True, "", url, _plain(cat.group(1)) if cat else "")
        if e:
            out.append(e)
    return out


def read(src, ctx):
    return parse(C.get_text(src["url"]), src)
