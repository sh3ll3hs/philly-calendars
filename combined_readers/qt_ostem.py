"""oSTEM (Out in Science, Technology, Engineering, and Mathematics) —
reads https://ostem.org/events/event_list.asp and the Atomcal schedule hub
https://atomcal.com/ostem-2023-2024-events-atomcal-discord-server-schedule-hub-ca49cf/
via fetch_cloudflare_protected (curl_cffi chrome120 TLS impersonation).
"""
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

import combined_to_ics as C
from combined_readers import qt_common as Q

OSTEM_LIST_URL = "https://ostem.org/events/event_list.asp"
OSTEM_ATOMCAL_URL = "https://atomcal.com/ostem-2023-2024-events-atomcal-discord-server-schedule-hub-ca49cf/"


def parse_atomcal(soup: BeautifulSoup, src: dict, page_url: str = OSTEM_ATOMCAL_URL) -> list[dict]:
    out = []
    for card in soup.select("[data-lpc-snapshot-event]"):
        if card.get("data-phase") == "ended" or card.get("data-ended") == "1":
            continue
        start_raw = card.get("data-start") or ""
        if not start_raw:
            continue
        end_raw = card.get("data-end") or ""
        title = card.get("data-title") or card.get_text(" ", strip=True) or "oSTEM Event"
        try:
            dt_start = date_parser.isoparse(start_raw).astimezone(Q.EASTERN).replace(tzinfo=None)
            dt_end = date_parser.isoparse(end_raw).astimezone(Q.EASTERN).replace(tzinfo=None) if end_raw else None
        except (ValueError, TypeError):
            continue
        e = C.event(src, f"{title}|{start_raw}", title, dt_start, dt_end, False, "Online", page_url, "", rsvp=page_url)
        if e:
            out.append(e)
    return out


def parse_event_list(soup: BeautifulSoup, src: dict, today, hi) -> list[dict]:
    html_text = str(soup)
    if "There are currently no calendar entries" in html_text:
        return []
    return C.jsonld_events(src, html_text, src["url"]) or C.text_events(src, html_text, src["url"], today, hi)


def read(src, ctx):
    out = []
    list_url = src.get("url") or OSTEM_LIST_URL
    atomcal_url = src.get("atomcal_url") or OSTEM_ATOMCAL_URL
    soup = Q.fetch_cloudflare_protected(list_url)
    out += parse_event_list(soup, src, ctx["today"], ctx["hi"])
    if atomcal_url:
        atom_soup = Q.fetch_cloudflare_protected(atomcal_url)
        out += parse_atomcal(atom_soup, src, atomcal_url)
    return out
