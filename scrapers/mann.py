"""Highmark Mann (highmarkmann.org; manncenter.org redirects here). Drupal 11.

Source: the /events list (links /events/YYYY-MM-DD/<slug>, plus the season pages),
then each detail page, which has labelled blocks:
    Skyline Stage | Select Event Date | April 24, 2027 - 7:00PM | ... | Doors | 6:00PM | Showtime | 7:00PM
Multi-night runs list every performance in the "Select Event Date" dropdown, so one
record is emitted per option. The page's add-to-calendar string has a wrong time
(15:00 for a 7 PM show) and is ignored.
"""
import datetime as dt
import re
import sys
import urllib.parse

from bs4 import BeautifulSoup

from common import http
from common.normalize import first_time, record

VENUE = "Highmark Mann"
BASE = "https://highmarkmann.org"
LISTS = ["/events", "/events/2026-season", "/events/2027-season"]
STAGES = ("TD Pavilion", "Skyline Stage", "Downstage")
LINK = re.compile(r"^(?:https://highmarkmann\.org)?/events/(\d{4}-\d{2}-\d{2})/[a-z0-9-]+/?$")


def parse_list(html):
    soup = BeautifulSoup(html, "html.parser")
    return list(dict.fromkeys(urllib.parse.urljoin(BASE, a["href"])
                              for a in soup.find_all("a", href=LINK)))


def _label(text, label):
    m = re.search(label + r"\s*\|\s*([^|]{2,20})", text, re.I)
    return first_time(m.group(1)) if m else None


def parse_detail(html, url):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" | ", strip=True))
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else ""
    doors, show = _label(text, r"Doors"), _label(text, r"Showtime")
    stage = next((s for s in STAGES if s in text), None)
    tm = soup.find("a", href=re.compile(r"ticketmaster\.com/.*event/"))
    sup = re.search(re.escape(title) + r"\s*\|\s*(with [^|]+)", text) if title else None
    # Every performance date from the dropdown: "April 24, 2027 - 7:00PM"
    perfs = []
    for opt in re.findall(r"([A-Z][a-z]+ \d{1,2}, \d{4})\s*-\s*(\d{1,2}:\d{2}\s*[AP]M)", text):
        try:
            d = dt.datetime.strptime(opt[0], "%B %d, %Y").date()
        except ValueError:
            continue
        if (d, opt[1]) not in perfs:
            perfs.append((d, opt[1]))
    if not perfs:
        m = LINK.match(urllib.parse.urlsplit(url).path)
        perfs = [(dt.date.fromisoformat(m.group(1)), None)] if m else []
    return [record(VENUE, title, d, show_time=first_time(t) if t else show, doors_time=doors,
                   subtitle=sup.group(1) if sup else None, url=url,
                   ticket_url=tm["href"] if tm else None, source="html", room=stage)
            for d, t in perfs]


def fetch():
    urls = []
    for path in LISTS:
        try:
            urls += parse_list(http.get_text(BASE + path))
        except Exception as e:
            print(f"mann: {path}: {e}", file=sys.stderr)
    out = []
    for u in dict.fromkeys(urls):
        try:
            out += parse_detail(http.get_text(u), u)
        except Exception as e:
            print(f"mann: {u}: {e}", file=sys.stderr)
    # season pages include past shows; de-dupe multi-night runs reached from several list links
    today = dt.date.today().isoformat()
    return list({(e["date"], e["title"]): e for e in out if e["date"] >= today}.values())


if __name__ == "__main__":
    ev = fetch()
    print(len(ev), "records;", sum(e["needs_manual"] for e in ev), "need manual")
    for e in ev[:3]:
        print(e)
