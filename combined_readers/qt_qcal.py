"""Pride at Work Canada — public syndicated events read from Schema.org Event JSON-LD on qcal.app.

Bypasses prideatwork.ca (whose robots.txt turns away automated agents by name) by reading
Pride at Work Canada's public syndicated event pages and host listing on https://qcal.app.
"""
import json
import urllib.parse
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

import combined_to_ics as C
from combined_readers import qt_common as Q

QCAL_HOST_URL = "https://qcal.app/host/pride-at-work-canada"
QCAL_PRIDE_AT_WORK_URLS = [
    "https://qcal.app/event/matrices-trans-non-binary-agender-digital-connect",
    "https://qcal.app/event/trans-and-nonbinary-inclusion-and-safety-in-the-energy-sector-nov-19-toronto-on-ca",
]


def discover_qcal_urls(host_html: str, base_url: str = QCAL_HOST_URL) -> list[str]:
    """Extract upcoming event URLs from a QCal host page (skipping cards marked Ended)."""
    soup = BeautifulSoup(host_html, "html.parser")
    urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("/event/"):
            continue
        card = a.parent
        for _ in range(3):
            if card and card.parent and len(list(card.parent.stripped_strings)) < 15:
                card = card.parent
        texts = [t.strip() for t in (card.stripped_strings if card else [])]
        if "Ended" in texts:
            continue
        full = urllib.parse.urljoin(base_url, href)
        if full not in urls:
            urls.append(full)
    return urls


def parse_qcal_event_page(html_text: str, url: str, src: dict) -> list[dict]:
    """Parse Schema.org Event JSON-LD from a QCal event page."""
    soup = BeautifulSoup(html_text, "html.parser")
    events, seen = [], set()
    for script in soup.find_all("script", type="application/ld+json"):
        if not script.string:
            continue
        try:
            data = json.loads(script.string)
        except ValueError:
            continue
        for item in C.walk(data):
            if item.get("@type") != "Event":
                continue
            start_raw = item.get("startDate")
            end_raw = item.get("endDate")
            if not start_raw:
                continue
            dt_start = date_parser.isoparse(start_raw).astimezone(Q.EASTERN).replace(tzinfo=None)
            dt_end = (
                date_parser.isoparse(end_raw).astimezone(Q.EASTERN).replace(tzinfo=None)
                if end_raw
                else dt_start
            )
            title = item.get("name", "Pride at Work Event")
            dedup_key = (title, dt_start)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            loc_obj = item.get("location", {})
            if isinstance(loc_obj, dict):
                addr = loc_obj.get("address")
                addr_loc = addr.get("addressLocality", "Online") if isinstance(addr, dict) else (addr or "Online")
                loc_name = loc_obj.get("name") or addr_loc
            else:
                loc_name = "Online"
            offers = item.get("offers")
            rsvp_url = (offers.get("url") if isinstance(offers, dict) else None) or url
            e = C.event(
                src,
                f"{url}|{start_raw}",
                title,
                dt_start,
                dt_end,
                False,
                Q.place(loc_name),
                url,
                item.get("description", ""),
                rsvp=rsvp_url,
            )
            if e:
                events.append(e)
    return events


def scrape_qcal_events(
    urls: list[str] | None = None,
    source_name: str = "Pride at Work Canada",
    src: dict | None = None,
) -> list[dict]:
    src = src or {"id": "qt_prideatwork", "name": source_name, "url": QCAL_HOST_URL}
    target_urls = list(urls or QCAL_PRIDE_AT_WORK_URLS)
    host_url = src.get("url") or QCAL_HOST_URL
    if "/host/" in host_url:
        try:
            host_html = Q.fetch_cloudflare_text(host_url)
            for u in discover_qcal_urls(host_html, host_url):
                if u not in target_urls:
                    target_urls.append(u)
        except Exception:
            pass
    events, seen = [], set()
    for url in target_urls:
        try:
            html_text = Q.fetch_cloudflare_text(url)
            for e in parse_qcal_event_page(html_text, url, src):
                k = (e["title"], e["start"])
                if k not in seen:
                    seen.add(k)
                    events.append(e)
        except Exception as exc:
            print(f"[WARN] Failed QCal scrape for {url}: {exc}")
    return events


def read(src, ctx):
    urls = src.get("urls") or QCAL_PRIDE_AT_WORK_URLS
    return scrape_qcal_events(urls=urls, source_name=src.get("name", "Pride at Work Canada"), src=src)
