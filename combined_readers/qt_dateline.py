"""Conference pages that state an event as a heading, a date line and a place line:

    Club Leadership Summit            O4U Business             June 7-9, 2027 • New York
    April 10-11, 2026                 October 8-10, 2026       LWT Summit
    Dallas, TX                        New York City, NY

Used for Reaching Out MBA (reachingoutmba.org/events/), Out for Undergrad's conference
pages and the Lesbians Who Tech & Allies summit page: one request per page.

An event is a line that is nothing but a date with its year ("April 10-11, 2026",
"July 21, 2026 (one day only)", "June 7 - July 2, 2026"), optionally followed on the
same line by "• Place". Dates without a year are ignored, so nothing is guessed. The
title is the line above (or the registry entry's "title", for a page about a single
event; with "limit": 1 only the first date line is used). The place is the rest of the
date line, or the next line when it reads as "City, ST" or "Virtual". The link is the
first link in the three lines that follow, used as the sign-up link when its text says
register / apply / tickets, else as the event page. Events are all-day; a run of days
is shown on its first day with "(through ...)".

Checked 2026-11-17: Reaching Out MBA's page (Club Leadership Summit, April 10-11, 2026,
Dallas, TX; Boston Trek, July 21, 2026; ROMBA Conference 2026, October 1-3, 2026),
O4U Business (October 8-10, 2026, New York City, NY) and lwtsquad.com
(June 7-9, 2027, New York). All but the last were past that day.

Known failure modes: a page that moves the date into a sentence, or drops the year,
yields nothing; a heading other than the event's name above the date becomes the title.
"""
import datetime as dt
import re
import urllib.parse

import combined_to_ics as C
from common import normalize
from combined_readers import qt_common as Q

M = r"(" + Q.MONTHS + r")"
LINE_RX = re.compile(r"^" + M + r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*(?:-|–|—|to|through)\s*(?:" + M + r"\s+)?(\d{1,2})(?:st|nd|rd|th)?)?,?\s+(20\d{2})"
                     r"(?P<rest>(?:\s*[•|·(@,-].*)?)$", re.I)
PLACE_RX = re.compile(r"^(Virtual|Online|[A-Z][A-Za-z .'-]{1,30}, [A-Z]{2}|[A-Z][A-Za-z .'-]{1,30}, [A-Z][a-z]+)$")


def parse(body, src, page_url):
    L, out = Q.lines(body), []
    for i, raw in enumerate(L):
        m = LINE_RX.match(Q.plain(raw))
        if not m:
            continue
        try:
            y = int(m.group(5))
            first = dt.date(y, normalize.month_num(m.group(1)), int(m.group(2)))
            last = dt.date(y, normalize.month_num(m.group(3) or m.group(1)), int(m.group(4))) if m.group(4) else None
        except (TypeError, ValueError):
            continue
        rest = C.clean(re.sub(r"^[\s•|·@,-]+", "", m.group("rest") or ""))
        loc = "" if rest.startswith("(") else rest
        if not loc and i + 1 < len(L) and PLACE_RX.match(Q.plain(L[i + 1])):
            loc = Q.plain(L[i + 1])
        title = src.get("title") or next((Q.plain(x) for x in reversed(L[max(0, i - 2):i])
                                          if 2 < len(Q.plain(x)) <= 90 and not LINE_RX.match(Q.plain(x))), "")
        if not title:
            continue
        url, rsvp = page_url, ""
        for nxt in L[i:i + 4]:
            hrefs = [h for h in Q.links(nxt) if h and not h.startswith(("#", "mailto:", "tel:", "javascript:"))]
            if hrefs:
                target = urllib.parse.urljoin(page_url, hrefs[0])
                if Q.RSVP_TEXT.search(Q.plain(nxt)):
                    rsvp = target
                else:
                    url = target
                break
        e = C.event(src, f"{title}|{first}", title, first, last if last and last > first else None, True,
                    Q.place(loc), url, "", rsvp=rsvp)
        if e:
            out.append(e)
        if src.get("limit") and len(out) >= int(src["limit"]):
            break
    return out


def read(src, ctx):
    out = []
    for u in src.get("urls") or [src["url"]]:
        try:
            out += parse(C.get_text(u), dict(src, title=(src.get("titles") or {}).get(u, src.get("title"))), u)
        except C.http.BlockedError:
            raise
        except Exception:
            if u == (src.get("urls") or [src["url"]])[0]:
                raise
    return out
