"""TransWork (a program of the Independence Business Alliance: jobs and business
support for trans and nonbinary people in the Philadelphia area) — transwork.org/events.

List page (one request): after "Upcoming Events", each event is a link to
/events/<slug> followed by its date ("November 10, 2026", or "January 23, 2025 to
February 26, 2025") and its title; past events stay on the page and are dropped by
the feed's date window. Event page (opened only for events inside the window, kept a
week, at most 12 new pages per run): "Event Details" then "November 10, 2026 - 4:00pm",
the write-up, and a "REGISTER HERE" link.

The time is Eastern (the program and its events are in Philadelphia). The place is a
street address found in the write-up ("605 S 3rd St, Philadelphia PA, 19147"),
"Online" when the title or the write-up says the event is virtual, else left out.

robots.txt (2026-11-17): the standard Drupal file; /events is not disallowed.

Checked 2026-11-17 against the site (past events, there being no upcoming one that
day): TransWork Happy Hour Networking at Val's Lesbian Bar, November 10, 2026, 4:00pm,
605 S 3rd St; Networking and Job-Search Resources, October 14, 2026.

Known failure modes: a changed list layout returns nothing; an address written in
another form is not found (the event then has no place, never a guessed one).
"""
import datetime as dt
import html
import re
import urllib.parse

import combined_to_ics as C
from common import normalize
from combined_readers import qt_common as Q

DATE_RX = re.compile(r"\b(" + Q.MONTHS + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})", re.I)
ADDR_RX = re.compile(r"\b(\d{1,5} [A-Z0-9][A-Za-z0-9 .'&-]{2,40}?,? (?:[A-Z][a-z]+ ){0,2}[A-Z][a-z]+,? (?:PA|NJ|DE),? \d{5})\b")


def _days(s):
    out = []
    for m in DATE_RX.finditer(s):
        try:
            out.append(dt.date(int(m.group(3)), normalize.month_num(m.group(1)), int(m.group(2))))
        except (TypeError, ValueError):
            pass
    return out


def parse_list(body, src):
    """-> [{day, end, title, url}] for every event the page lists."""
    L = Q.lines(body)
    start = next((i for i, l in enumerate(L) if Q.plain(l).lower() == "upcoming events"), 0)
    out = []
    for i in range(start, len(L) - 1):
        href = next((h for h in Q.links(L[i]) if re.match(r"^(https?://[^/]*transwork\.org)?/events/[^/?#]+$", h)), None)
        if not href:
            continue
        rows = [r for r in [Q.plain(L[i])] + [Q.plain(x) for x in L[i + 1:i + 6]] if r]
        days, title = [], ""
        for r in rows:                       # "January 23, 2025" / "to" / "February 26, 2025" / title
            if _days(r) and not DATE_RX.sub("", r).strip(" to-–,"):
                days += _days(r)
            elif days and r.lower() in ("to", "-", "–", "through"):
                continue
            elif days:
                title = r
                break
        if not (days and title):
            continue
        out.append({"day": days[0], "end": days[-1] if days[-1] > days[0] else None, "title": title,
                    "url": urllib.parse.urljoin(src["url"], html.unescape(href))})
    return out


def parse_detail(body):
    L = [l for l in Q.lines(body)]
    i = next((k for k, l in enumerate(L) if Q.plain(l).lower() == "event details"), None)
    when = Q.plain(L[i + 1]) if i is not None and i + 1 < len(L) else ""
    text = "\n".join(Q.plain(l) for l in (L[i + 2:i + 12] if i is not None else []))
    rsvp = ""
    for l in L:
        if Q.RSVP_TEXT.search(Q.plain(l)):
            rsvp = next((h for h in Q.links(l) if h.startswith("http")), "")
            if rsvp:
                break
    addr = ADDR_RX.search(text)
    return {"when": when, "rsvp": rsvp, "addr": C.clean(addr.group(1)) if addr else "",
            "blurb": text.split("\n")[0] if text else "", "virtual": bool(re.search(r"\b(virtual|zoom|online)\b", text[:600], re.I))}


def build(item, info, src):
    info = info or {}
    loc = info.get("addr") or ("Online" if info.get("virtual") or re.search(r"\b(virtual|online)\b", item["title"], re.I) else "")
    clock = C.clock_from_text(DATE_RX.sub(" ", info.get("when", ""))) if info.get("when") else None
    if clock and not item["end"]:
        st = dt.datetime.combine(item["day"], clock[0])
        en = dt.datetime.combine(item["day"], clock[1]) if clock[1] else None
        return C.event(src, item["url"], item["title"], st, en, False, loc, item["url"], info.get("blurb", ""), rsvp=info.get("rsvp", ""))
    return C.event(src, item["url"], item["title"], item["day"], item["end"], True, loc, item["url"],
                   info.get("blurb", ""), rsvp=info.get("rsvp", ""))


def read(src, ctx):
    budget, out, seen = [int(src.get("detail_max", 12))], [], set()
    for it in parse_list(C.get_text(src["url"]), src):
        if it["url"] in seen or not (ctx["lo"] <= (it["end"] or it["day"]) and it["day"] <= ctx["hi"]):
            continue
        seen.add(it["url"])
        e = build(it, Q.cached(ctx, it["url"], budget, parse_detail), src)
        if e:
            out.append(e)
    return out
