"""myGwork — global LGBTQ+ business community events on https://mygwork.com/en/events.

Fetched via curl_cffi TLS impersonation (fetch_cloudflare_protected) because
mygwork.com answers 403 to standard Python requests.
"""
import datetime as dt
import re
import urllib.parse
from bs4 import BeautifulSoup

import combined_to_ics as C
from combined_readers import qt_common as Q

STAMP_RX = re.compile(
    r"([A-Za-z]+\s+\d{1,2},\s+20\d{2})\s+at\s+(\d{1,2}:\d{2}\s*[AP]M)\s+([A-Z]{2,5})",
    re.I,
)


def _parse_stamp(text: str) -> dt.datetime | None:
    m = STAMP_RX.search(text)
    if not m:
        return None
    date_str, time_str, tz_abbr = m.groups()
    tz = Q.TZ_MAP.get(tz_abbr.upper(), Q.EASTERN)
    try:
        dt_val = dt.datetime.strptime(f"{date_str} {time_str.upper()}", "%B %d, %Y %I:%M %p")
    except ValueError:
        return None
    return dt_val.replace(tzinfo=tz).astimezone(Q.EASTERN).replace(tzinfo=None)


def parse(soup: BeautifulSoup, src: dict) -> list[dict]:
    out, seen = [], set()
    for h4 in soup.find_all("h4"):
        title = h4.get_text(" ", strip=True)
        if not title:
            continue
        card = h4.find_parent("div", class_=lambda c: c and "w-full" in c) or h4.find_parent(["div", "article", "li"])
        if not card:
            continue
        a = card.find("a", href=True)
        href = a["href"] if a else ""
        url = urllib.parse.urljoin("https://mygwork.com", href) if href else src["url"]
        if url in seen:
            continue
        strings = [s.strip() for s in card.stripped_strings if s.strip()]
        text = " ".join(strings)
        if "Start:" not in text:
            continue
        after_start = text.split("Start:", 1)[1]
        parts = after_start.split("End:", 1)
        dt_start = _parse_stamp(parts[0])
        if not dt_start:
            continue
        dt_end = _parse_stamp(parts[1]) if len(parts) > 1 else None
        loc = strings[-1] if strings else "Online"
        if STAMP_RX.search(loc) or loc in ("Start:", "End:", "at"):
            loc = "Online"
        p_tag = card.find("p")
        blurb = p_tag.get_text(" ", strip=True) if p_tag else ""
        seen.add(url)
        e = C.event(src, url, title, dt_start, dt_end, False, Q.place(loc), url, blurb, rsvp=url)
        if e:
            out.append(e)
    return out


def read(src, ctx):
    soup = Q.fetch_cloudflare_protected(src["url"])
    return parse(soup, src)
