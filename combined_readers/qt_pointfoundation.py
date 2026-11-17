"""Point Foundation — LGBTQ+ scholarship & leadership events on
https://pointfoundation.org/community/events.

Reads event cards on /community/events and opens their detail pages (via
fetch_cloudflare_protected / cached) to extract stated dates, times, and locations.
"""
import datetime as dt
import re
import urllib.parse
from bs4 import BeautifulSoup

import combined_to_ics as C
from common import normalize
from combined_readers import qt_common as Q
from combined_readers import zones

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
RANGE_RX = re.compile(
    r"(?:(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s+)?"
    r"(" + Q.MONTHS + r")\s+(\d{1,2})\s*(?:,?\s*(?:through|to|-|–)\s*"
    r"(?:(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s+)?"
    r"(?:(" + Q.MONTHS + r")\s+)?(\d{1,2}))?(?:,?\s+(20\d{2}))?",
    re.I,
)
YEAR_RX = re.compile(r"\b(20\d{2})\b")
LOC_RX = re.compile(r"\b(?:at the|at|in|Location:)\s+([A-Z][A-Za-z0-9\s.,'&-]{3,80}?)(?:\.\s|$)", re.I)


def parse_links(html_text: str, page_url: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html_text, "html.parser")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        u = urllib.parse.urljoin(page_url, a["href"]).split("#")[0]
        p = urllib.parse.urlsplit(u)
        if not p.path.startswith("/community/events/") or "/page/" in p.path:
            continue
        if u in seen:
            continue
        card = a.parent
        for _ in range(3):
            if card and card.parent and len(list(card.parent.stripped_strings)) < 20:
                card = card.parent
        h = card.find(["h1", "h2", "h3", "h4"]) if card else None
        title = h.get_text(" ", strip=True) if h else a.get_text(" ", strip=True)
        if not title or title.lower() in ("read more", "events") or "cancelled" in title.lower() or "thank you for attending" in title.lower():
            continue
        if re.search(r"\b202[0-4]\b", title):
            continue
        seen.add(u)
        out.append((u, title))
    return out


def parse_detail(html_text: str, url: str = "", card_title: str = "") -> dict:
    soup = BeautifulSoup(html_text, "html.parser")
    main = soup.find("main") or soup.find("article") or soup
    h1 = main.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else card_title
    if "registration" in title.lower() and "national leadership conference" in main.get_text(" ", strip=True).lower():
        m_y = YEAR_RX.search(title) or YEAR_RX.search(main.get_text(" ", strip=True))
        title = f"{m_y.group(1)} National Leadership Conference (NLC)" if m_y else "National Leadership Conference (NLC)"
    paras = []
    for el in main.find_all(["p", "li"]):
        t = " ".join(el.stripped_strings)
        if "Related Posts" in t or "When you sign up for the Point Foundation" in t:
            break
        if re.match(r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2},\s+", t):
            continue
        paras.append(t)
    body_text = "\n".join(paras)
    year_hint = None
    m_yr = YEAR_RX.search(title)
    if m_yr:
        year_hint = int(m_yr.group(1))
    start_day, end_day, clock, loc = None, None, None, ""
    for line in paras:
        if any(w in line.lower() for w in ("deadline", "register by", "raise $", "contact ", "graduating class")):
            continue
        for m in RANGE_RX.finditer(line):
            w1, m1, d1, w2, m2, d2, yr = m.groups()
            if not (w1 or yr or year_hint or d2):
                continue
            y = int(yr) if yr else year_hint
            if not y:
                continue
            try:
                s_date = dt.date(y, normalize.month_num(m1), int(d1))
                e_date = dt.date(y, normalize.month_num(m2 or m1), int(d2)) if d2 else None
            except (TypeError, ValueError):
                continue
            if w1 and s_date.weekday() != WEEKDAYS.index(w1.lower()[:3]):
                continue
            start_day, end_day = s_date, e_date
            clock = C.clock_from_text(line[m.end():]) or C.clock_from_text(line)
            break
        if start_day:
            break
    for line in paras:
        m_loc = re.search(r"Location:\s*([^\n.]+)", line, re.I)
        if m_loc:
            loc = C.clean(m_loc.group(1))
            break
        m_at = re.search(r"(?:through|to)\s+[A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+at\s+(?:the\s+)?([^\n.]+)", line, re.I)
        if m_at:
            loc = C.clean(m_at.group(1))
            break
        m_in = re.search(r"(?:through|to)\s+[A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2}\s+in\s+([A-Z][A-Za-z\s,]+?)(?:\s+in\s+|\.|$)", line)
        if m_in:
            loc = C.clean(m_in.group(1))
            break
    return {
        "title": title,
        "start": start_day.isoformat() if start_day else "",
        "end": end_day.isoformat() if end_day else "",
        "clock": [clock[0].isoformat(), clock[1].isoformat() if clock[1] else ""] if clock else None,
        "loc": loc,
        "blurb": paras[0] if paras else "",
    }


def build_event(url: str, info: dict, src: dict) -> dict | None:
    if not info or not info.get("start"):
        return None
    day = dt.date.fromisoformat(info["start"])
    end_day = dt.date.fromisoformat(info["end"]) if info.get("end") else None
    loc = Q.place(info.get("loc", ""))
    clock = info.get("clock")
    if clock and not end_day:
        t0 = dt.time.fromisoformat(clock[0])
        t1 = dt.time.fromisoformat(clock[1]) if clock[1] else None
        st = dt.datetime.combine(day, t0)
        en = dt.datetime.combine(day, t1) if t1 else None
        z = zones.zone_for(loc) or zones.zone_for(info.get("title", ""))
        if z:
            return C.event(src, url, info["title"], zones.to_ny(st, z), zones.to_ny(en, z) if en else None, False, loc, url, info.get("blurb", ""))
    return C.event(src, url, info["title"], day, end_day, True, loc, url, info.get("blurb", ""))


def read(src, ctx):
    soup = Q.fetch_cloudflare_protected(src["url"])
    links = parse_links( str(soup), src["url"])
    budget, out, seen = [int(src.get("detail_max", 12))], [], set()
    for u, card_title in links:
        info = Q.cached(ctx, u, budget, lambda body, url=u, ct=card_title: parse_detail(body, url, ct))
        if not info and budget[0] > 0:
            try:
                body = Q.fetch_cloudflare_text(u)
                info = parse_detail(body, u, card_title)
            except Exception:
                continue
        e = build_event(u, info, src)
        if e:
            k = (C.norm_title(e["title"]), e["start"])
            if k not in seen:
                seen.add(k)
                out.append(e)
    return out
