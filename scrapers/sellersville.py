"""Sellersville Theater (st94.com). Server-rendered, paginated /upcoming-shows/, /p2/ ...

Each .eventCard:
    <p class="date">Sun, Nov 08</p>
    <p class="venue">Sellersville Theater 1894</p>   (or The Washington House)
    <h3>Title</h3>
    <p class="times">Show | 2:00PM // Doors | 1:30PM</p>   (dinners: "Show | 4:00PM" only)
    <p class="price range">$29.5 to $56.5</p>
    More Info -> /events/<slug>/ ; Buy -> etix.com/ticket/p/<id>/...
Cards carry no year; it is inferred by rolling forward from today. The list is not
strictly sorted, so past dates are filtered rather than assumed absent.
"""
import datetime as dt
import re
import sys

from bs4 import BeautifulSoup

from common import http
from common.normalize import infer_year, month_num, record

VENUE = "Sellersville Theater"
BASE = "https://www.st94.com/upcoming-shows/"
MAX_PAGES = 15
TIMES = re.compile(r"Show\s*\|\s*([\d:]+\s*[AP]M)(?:.*?Doors\s*\|\s*([\d:]+\s*[AP]M))?", re.I | re.S)


def parse(html, today=None):
    today = today or dt.date.today()
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for card in soup.select(".eventCard"):
        date_el, h3 = card.select_one("p.date"), card.find("h3")
        times_el = card.select_one("p.times")
        if not (date_el and h3):
            continue
        m = re.search(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})", date_el.get_text(" ", strip=True))
        d = infer_year(month_num(m.group(1)), int(m.group(2)), today, lookback_days=0) if m else None
        if not d:
            continue
        show = doors = None
        if times_el:
            tm = TIMES.search(times_el.get_text(" ", strip=True))
            if tm:
                from common.normalize import first_time
                show, doors = first_time(tm.group(1)), first_time(tm.group(2) or "")
        links = {a.get_text(strip=True).lower(): a["href"] for a in card.find_all("a", href=True)}
        detail = next((h for h in links.values() if "st94.com/events/" in h), "")
        ticket = next((h for h in links.values() if "etix.com" in h), None)
        room = card.select_one("p.venue")
        price = card.select_one("p.price")
        out.append(record(VENUE, h3.get_text(" ", strip=True), d, show_time=show, doors_time=doors,
                          url=detail, ticket_url=ticket, price=price.get_text(" ", strip=True) if price else None,
                          source="html", room=room.get_text(" ", strip=True) if room else None))
    return out


def fetch():
    out = []
    for n in range(1, MAX_PAGES + 1):
        url = BASE if n == 1 else f"{BASE}p{n}/"
        try:
            page = parse(http.get_text(url))
        except Exception as e:
            print(f"sellersville: {url}: {e}", file=sys.stderr)
            break
        if not page:
            break
        out += page
    return list({(e["date"], e["title"]): e for e in out}.values())


if __name__ == "__main__":
    ev = fetch()
    print(len(ev), "records;", sum(e["needs_manual"] for e in ev), "need manual")
    for e in ev[:3]:
        print(e)
