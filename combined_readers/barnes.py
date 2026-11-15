"""
Barnes Foundation — events reader for https://www.barnesfoundation.org/whats-on

Source: the "What's On" page (Craft CMS, server-rendered; robots.txt only rules out /craft/)
and the pages behind its "View More" button. The button's link is /whats-on/p2; the site's
own script requests it as `/whats-on/p2?ajax=1` and gets just the next six cards plus the
next link (a plain /whats-on/p2 answers with page 1 again). Four requests covered six months
when this was written; at most 6 are made per run. There is no feed, and neither the listing
nor the event pages carry schema.org Event data.

Each card is `<div class="m-card-event vevent">` with `m-card-event__type` ("Free / Talks"),
`m-card-event__title` (link), one or two `m-card-event__date` lines and a summary. The date
line is prose, and only some cards are dated events:

    "Wednesday, December 2, 6 – 7pm"                    -> Dec 2, 6:00-7:00 PM
    "Tuesday, November 17" + "11am – 1pm or 3 – 5pm"    -> Nov 17, 11:00 AM-1:00 PM (first session)
    "Wednesdays, February 10 – February 17, 2 – 4pm"    -> Feb 10 2:00 PM, run ends Feb 17 4:00 PM
    "February 21 – May 9, 2027"  (upcoming exhibition)  -> all-day Feb 21, through May 9
    "Until January 18, 2027"     (current exhibition)   -> skipped: the page gives no opening day
    "Ongoing", "Thursday–Monday, 1pm", "Mondays & Thursdays, 2pm"  (standing tours)  -> skipped

The built-in `text` method turns the "Until ..." closing days into events; that is why this
reader exists.

Checked on 2026-11-15 against the site: In Conversation: Brandon Shimoda and Rea Tajiri
(card and event page both "Wednesday, December 2, 6 – 7pm"; the page's ticket link carries
date=2026-12-02T18:00:00), First Friday (Friday, December 4, 6 – 9pm), Members-Only Gallery
Talk (Sunday, November 22, 10:15 – 11am).

Known failure modes:
  * No year in most date lines. The year is the neighbouring one in which the printed weekday
    fits ("Wednesday, December 2" is 2026); with no weekday and no year, the next such date.
  * Only the first session is used when a line offers alternatives ("11am – 1pm or 3 – 5pm"),
    and a class that meets weekly is one entry from its first meeting, shown by the feed as
    "(through <last day>)". The description starts with the date line exactly as printed.
  * Location is not on the cards. Cards whose type or title says "Online" get "Online"; all
    others get the Barnes (`onsite_venue` in the source entry). A program held elsewhere
    would be mislabelled.
  * Standing tours and current exhibitions are left out on purpose (no single date).
  * A date line in a new wording is skipped rather than guessed; if the `m-card-event*`
    classes change, the reader returns nothing.
"""
import datetime as dt
import html
import re
import urllib.parse

import combined_to_ics as C

MAX_PAGES = 6
ONSITE = "Barnes Foundation, 2025 Benjamin Franklin Pkwy, Philadelphia, PA 19130"
MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
WEEKDAYS = {d: i for i, d in enumerate("mon tue wed thu fri sat sun".split())}
MONTH = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
DAY_RX = re.compile(r"(?:\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,\s*)?\b" + MONTH + r"\s+(\d{1,2})\b(?:,\s*(20\d{2}))?", re.I)
# what may follow the first date to make it a run: "– February 17", "– May 9, 2027", "– 6" (then a comma or the end)
TO_RX = re.compile(r"\s*[–—-]\s*(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,\s*)?(?:" + MONTH + r"\s+(\d{1,2})\b(?:,\s*(20\d{2}))?"
                   r"|(\d{1,2})(?=\s*(?:,|$)))", re.I)
CARD_RX = re.compile(r'<div class="m-card-event vevent[^"]*">')


def _plain(s):
    return C.clean(re.sub(r"<[^>]+>", " ", s or ""))


def _day(weekday, month, day, year, today):
    """A date from what is printed: the given year, else the neighbouring year in which the
    weekday fits, else the next such date."""
    try:
        if year:
            return dt.date(int(year), month, day)
    except ValueError:
        return None
    want = WEEKDAYS.get((weekday or "")[:3].lower())
    if want is not None:
        for y in (today.year, today.year + 1, today.year - 1):
            try:
                d = dt.date(y, month, day)
            except ValueError:
                continue
            if d.weekday() == want:
                return d
    return C.normalize.infer_year(month, day, today)


def when(line, today):
    """Date line -> (start, end, all_day), or None when it names no single date."""
    if re.match(r"\s*(until|through|thru|ongoing)\b", line, re.I):
        return None
    m = DAY_RX.search(line)
    if not m:
        return None
    rest = line[m.end():]
    to = TO_RX.match(rest)
    first_year, last = m.group(4), None
    if to:
        rest = rest[to.end():]
        end_month = MONTHS[to.group(1)[:3].lower()] if to.group(1) else MONTHS[m.group(2)[:3].lower()]
        end_day = int(to.group(2) or to.group(4))
        if to.group(3):                                   # "February 21 – May 9, 2027": the year closes the run
            try:
                last = dt.date(int(to.group(3)), end_month, end_day)
            except ValueError:
                return None
            if not first_year:
                first_year = last.year if (MONTHS[m.group(2)[:3].lower()], int(m.group(3))) <= (end_month, end_day) \
                    else last.year - 1
    first = _day(m.group(1), MONTHS[m.group(2)[:3].lower()], int(m.group(3)), first_year, today)
    if not first:
        return None
    if to and not last:
        for y in (first.year, first.year + 1):
            try:
                cand = dt.date(y, end_month, end_day)
            except ValueError:
                continue
            if cand >= first:
                last = cand
                break
    if last and last <= first:
        last = None
    clock = C.clock_from_text(DAY_RX.sub(" ", rest))
    if not clock:
        return first, last, True
    start = dt.datetime.combine(first, clock[0])
    end = dt.datetime.combine(last or first, clock[1]) if clock[1] else None
    if end and end <= start:
        end = None
    return start, end, False


def next_page(body, page_url):
    m = re.search(r'm-card-event-list__more\b.*?<a\b[^>]*href="([^"]+)"', body, re.S)
    if not m:
        return ""
    url = urllib.parse.urljoin(page_url, html.unescape(m.group(1)))
    return url + ("&" if "?" in url else "?") + "ajax=1"       # as the site's "View More" script asks for it


def parse(body, src, today=None):
    """One page of cards (the full page or a "View More" fragment) -> dated events."""
    today = today or dt.datetime.now().date()
    marks = list(CARD_RX.finditer(body))
    out = []
    for i, c in enumerate(marks):
        block = body[c.end():marks[i + 1].start() if i + 1 < len(marks) else len(body)]
        link = re.search(r'm-card-event__title\b[^>]*>\s*<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        lines = [_plain(x) for x in re.findall(r'm-card-event__date\b[^>]*>(.*?)</div>', block, re.S)]
        line = ", ".join(x for x in lines if x)
        if not link or not line:
            continue
        got = when(line, today)
        if not got:
            continue
        start, end, all_day = got
        kind = re.search(r'm-card-event__type\b[^>]*>(.*?)</div>', block, re.S)
        kind = _plain(kind.group(1)) if kind else ""
        title = _plain(link.group(2))
        summary = re.search(r'm-card-event__summary\b[^>]*>(.*?)</div>', block, re.S)
        url = urllib.parse.urljoin(src["url"], html.unescape(link.group(1)))
        online = bool(re.search(r"\bonline\b", f"{kind} {title}", re.I))
        desc = "\n\n".join(x for x in (kind, line, C.text(summary.group(1)) if summary else "") if x)
        day = start.date() if isinstance(start, dt.datetime) else start
        e = C.event(src, f"{url}|{day}", title, start, end, all_day, "Online" if online else src.get("onsite_venue", ONSITE),
                    url, desc)
        if e:
            out.append(e)
    return out


def read(src, ctx):
    out, seen, url, pages = [], set(), src["url"], set()
    for _ in range(MAX_PAGES):
        if not url or url in pages:
            break
        pages.add(url)
        try:
            body = C.get_text(url)
        except Exception as ex:
            if not out and len(pages) == 1 or type(ex).__name__ == "BlockedError":   # first page, or a 403/406
                raise
            break
        for e in parse(body, src, ctx["today"]):
            if e["key"] not in seen:
                seen.add(e["key"])
                out.append(e)
        url = next_page(body, url)
    return out
