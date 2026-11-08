"""The Queen, Wilmington DE.

The /shows/ page fills its list client-side, and there's no WP REST events route
(404 rest_no_route) or events-sitemap.xml. But the Yoast sitemap index lists
fad_tm_event-sitemap.xml with every event page, and each event page is
server-rendered:
    Schedule | Saturday · December 5 · 08:00PM | ... The Crown at The Queen | AGES: All Ages | DOORS: 7:00 PM
plus a ticketmaster.com/.../event/<ID> link.
"""
import datetime as dt
import re
import sys

from bs4 import BeautifulSoup

from common import http
from common.normalize import first_time, infer_year, month_num, record

VENUE = "The Queen"
SITEMAP = "https://thequeenwilmington.com/fad_tm_event-sitemap.xml"
ROOMS = ("The Main Hall", "The Crown", "The Lounge")
SCHED = re.compile(r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\s*·\s*([A-Z][a-z]+)\s+(\d{1,2})\s*·\s*(\d{1,2}:\d{2}\s*[AP]M)")


def parse_sitemap(xml):
    return [u for u in re.findall(r"<loc>([^<]+)</loc>", xml) if "/events/" in u]


def parse_detail(html, url, today=None):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    m = SCHED.search(text)
    if not m:
        return []
    d = infer_year(month_num(m.group(1)), int(m.group(2)), today, lookback_days=0)
    if not d:
        return []
    h1 = soup.find("h1")
    doors = re.search(r"DOORS:\s*(\d{1,2}:\d{2}\s*[AP]M)", text, re.I)
    sup = re.search(r"About the Event\s+(with [^.]{3,120}?)\s+(?:Please Note|The )", text)
    tm = soup.find("a", href=re.compile(r"ticketmaster\.com/.*event/"))
    room = next((r for r in ROOMS if r in text), None)
    return [record(VENUE, h1.get_text(" ", strip=True) if h1 else "", d, show_time=first_time(m.group(3)),
                   doors_time=first_time(doors.group(1)) if doors else None,
                   subtitle=sup.group(1) if sup else None, url=url,
                   ticket_url=tm["href"] if tm else None, source="html", room=room)]


def fetch():
    out = []
    for u in parse_sitemap(http.get_text(SITEMAP)):
        try:
            out += parse_detail(http.get_text(u), u)
        except Exception as e:
            print(f"queen: {u}: {e}", file=sys.stderr)
    return out


if __name__ == "__main__":
    ev = fetch()
    print(len(ev), "records;", sum(e["needs_manual"] for e in ev), "need manual")
    for e in ev[:3]:
        print(e)
