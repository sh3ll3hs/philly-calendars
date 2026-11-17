"""Maven Youth — LGBTQ+ youth tech camps read from Wix Events on
https://www.mavenyouth.org/summer-camps and its /event-details/ pages.
"""
import json
import urllib.parse
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

import combined_to_ics as C
from combined_readers import qt_common as Q


def parse_detail_jsonld(html_text: str, href: str, src: dict) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    events = []
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Event" and data.get("startDate"):
            dt_start = date_parser.isoparse(data["startDate"]).astimezone(Q.EASTERN).replace(tzinfo=None)
            dt_end = date_parser.isoparse(data.get("endDate", data["startDate"])).astimezone(Q.EASTERN).replace(tzinfo=None)
            loc_obj = data.get("location") or {}
            loc = loc_obj.get("name", "Online / See page") if isinstance(loc_obj, dict) else "Online / See page"
            e = C.event(
                src,
                href,
                data.get("name", "Maven Youth Camp"),
                dt_start,
                dt_end,
                False,
                Q.place(loc),
                href,
                data.get("description", ""),
                rsvp=href,
            )
            if e:
                events.append(e)
    return events


def scrape_maven_youth(src: dict | None = None, ctx: dict | None = None) -> list[dict]:
    src = src or {"id": "qt_mavenyouth", "name": "Maven Youth", "url": "https://www.mavenyouth.org/summer-camps"}
    url = src.get("url") or "https://www.mavenyouth.org/summer-camps"
    html_text = C.get_text(url)
    soup = BeautifulSoup(html_text, "html.parser")
    events, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        p = urllib.parse.urlsplit(href)
        if not p.path.startswith("/event-details/") or href in seen:
            continue
        seen.add(href)
        try:
            detail_html = C.get_text(href)
        except Exception:
            continue
        events += parse_detail_jsonld(detail_html, href, src)
    return events


def read(src, ctx):
    return scrape_maven_youth(src=src, ctx=ctx)
