"""SOUTH Jazz Club (southjazzkitchen.com).

Source: the /jazz-club/ listing page (/event-directory/ redirects there). Each show
is a block linking to /event/<slug>/ with a pipe-delimited line:
    PHER | Sun Nov 8 | 6:00PM & 8:30PM
    ARPEGGIO ... | FRI, SAT & SUN NOV 13, 14 & 15 | SHOWTIMES VARY BY DAY
    SPUR OF THE MOMENT | THURSDAY NOVEMBER 12 | presented by UNSCRIPTED JAZZ
The third field holds the set times when they're fixed. Multi-day runs are expanded
to one record per date. "Showtimes vary" and lines with no time get needs_manual.
The slug sometimes carries the times too (pher-sun-nov-8-600pm-830pm), used as a fallback.

Not used: the Tock reservation widget (slots run ~1h before the set, not show times)
and the Tribe REST API (403 to ordinary requests).
"""
import re
import sys
import urllib.parse

from bs4 import BeautifulSoup

from common import http
from common.normalize import expand_dates, normalize_time, record

VENUE = "SOUTH Jazz Club"
URL = "https://www.southjazzkitchen.com/jazz-club/"
BASE = "https://www.southjazzkitchen.com"


def _slug_times(slug):
    """'...-600pm-830pm' -> ['18:00', '20:30']"""
    out = []
    for hhmm, ap in re.findall(r"(?<![\d])(\d{3,4})(am|pm)\b", slug):
        h, m = int(hhmm[:-2]), int(hhmm[-2:])
        out += normalize_time(f"{h}:{m:02d}{ap}")
    return out


def parse(html, today=None):
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for a in soup.find_all("a", href=re.compile(r"/event/[^/]+/?$")):
        href = urllib.parse.urljoin(BASE, a["href"])
        if href in seen:
            continue
        block, line = a, None
        for _ in range(8):  # climb to the block that holds the pipe line
            block = block.parent
            if block is None:
                break
            for el in block.find_all(string=re.compile(r"\|")):
                if el.count("|") >= 2:
                    line = re.sub(r"\s+", " ", el).strip()
                    break
            if line:
                break
        if not line:
            continue
        seen.add(href)
        parts = [p.strip() for p in line.split("|")]
        title, when = parts[0], parts[1] if len(parts) > 1 else ""
        third = " | ".join(parts[2:])
        sets = normalize_time(third) or _slug_times(href.rstrip("/").rsplit("/", 1)[-1])
        varies = bool(re.search(r"vary", third, re.I))
        subtitle = third if (third and not sets and not varies) else None
        for d in expand_dates(when, today):
            out.append(record(VENUE, title, d, set_times=[] if varies else sets, subtitle=subtitle,
                              url=href, source="html"))
    return out


_WD = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_DAYGROUP = re.compile(
    r"((?:(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?\s*(?:&|,|-|–|and|through|thru)?\s*)+)showtimes?\s*:?\s*"
    r"((?:\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?\s*(?:&|,|and|/)?\s*)+)", re.I)


def parse_day_times(html):
    """Detail page text like 'FRIDAY & SATURDAY SHOWTIMES 7:00PM & 9:30PM | SUNDAY SHOWTIMES 6:00PM & 8:30PM'
    -> {4: ['19:00','21:30'], 5: [...], 6: ['18:00','20:30']}  (weekday index -> set times)"""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "select", "form", "noscript"]):
        t.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    out = {}
    for days, times in _DAYGROUP.findall(text):
        sets = normalize_time(times)
        found = [_WD.index(d[:3].lower()) for d in re.findall(r"(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*", days, re.I)]
        if re.search(r"-|–|through|thru", days) and len(found) == 2:  # FRI-SUN
            a, b = found
            found = list(range(a, b + 1)) if a <= b else found
        for wd in found:
            out.setdefault(wd, sets)
    return out


def fetch():
    out = parse(http.get_text(URL))
    # "Showtimes vary by day": the event page lists the times per weekday.
    for url in dict.fromkeys(e["url"] for e in out if e["needs_manual"] and not e["subtitle"]):
        try:
            by_day = parse_day_times(http.get_text(url))
        except Exception as ex:
            print(f"south: {url}: {ex}", file=sys.stderr)
            continue
        for e in out:
            if e["url"] != url:
                continue
            sets = by_day.get(__import__("datetime").date.fromisoformat(e["date"]).weekday())
            if sets:
                e.update(set_times=sets, show_time=sets[0], needs_manual=False, source="html-detail")
    # the listing links some shows twice; keep one record per show-date
    return list({(e["date"], e["title"].lower()): e for e in out}.values())


if __name__ == "__main__":
    ev = fetch()
    print(len(ev), "records;", sum(e["needs_manual"] for e in ev), "need manual")
    for e in ev[:3]:
        print(e)
    sys.exit(0)
