#!/usr/bin/env python3
"""
venue_sites.py — show times from venues' own public websites.

Several big ticketing platforms (Ticketmaster, AXS, Tixr, Etix) block automated
requests, so xpn_times.py can't read show times from their pages. The venues
themselves publish the same shows, with times, on their own sites. This module
scrapes those listing pages once per run and builds an index that xpn_times.py
consults for any show it couldn't time directly.

Two page styles are understood:
  * schema.org JSON-LD Event data (Ardmore Music Hall, MilkBoy, Underground Arts,
    118 North, and Live Nation venue sites like the Fillmore, the Met, TLA)
  * Rockhouse Partners cards with "Doors: 7 pm | Show: 8 pm" text
    (R5 Productions - Union Transfer / First Unitarian / PhilaMOCA - and Johnny Brenda's)

Matching is by ticket URL first (the venue page links to the same Tixr/
Ticketmaster/Etix page XPN does), then by date + artist-name overlap.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ET = ZoneInfo("America/New_York")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# Public listing pages. Add a venue here and it is covered on the next run.
LISTINGS = [
    "https://www.ardmoremusichall.com/",
    "https://www.118northwayne.com/calendar",
    "https://www.milkboyphilly.com/",
    "https://www.milkboyphilly.com/events",
    "https://undergroundarts.org/",
    "https://undergroundarts.org/events/",
    "https://www.thefillmorephilly.com/shows",      # The Fillmore + The Foundry
    "https://www.themetphilly.com/shows",
    "https://www.tlaphilly.com/shows",
    "https://www.brooklynbowl.com/philadelphia/shows",
    "https://johnnybrendas.com/events/",
    "https://www.st94.com/",                        # Sellersville Theater
    "https://r5productions.com/events/",            # First Unitarian, PhilaMOCA, Warehouse on Watts, Ukie Club
]

# AEG Presents venues publish their schedules as plain JSON on a public CDN
# (the same file their own website reads). Venue id -> label.
AEG_JSON = {
    "289": "Union Transfer",
    "133": "Franklin Music Hall",
}

CLOCK = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?", re.I)
STOP = {"the", "and", "with", "feat", "featuring", "presents", "welcomes", "wxpn", "tour", "a", "an",
        "of", "live", "night", "show", "in", "at", "xpn", "plus", "special", "guest", "guests", "w"}


def norm_url(u):
    """Strip scheme, www, query and trailing slash so the same ticket page matches."""
    if not u:
        return ""
    p = urllib.parse.urlsplit(u.strip())
    host = p.netloc.lower().removeprefix("www.")
    path = re.sub(r"/+$", "", p.path)
    # Etix: /ticket/p/<id>/<slug> -> the id is the identity
    m = re.match(r"/ticket/p/(\d+)", path)
    if "etix.com" in host and m:
        return f"etix:{m.group(1)}"
    return host + path.lower()


def tokens(title):
    t = re.sub(r"&[#\w]+;", " ", title or "")
    t = re.sub(r"[^a-z0-9 ]+", " ", t.lower())
    return {w for w in t.split() if w not in STOP and len(w) > 1}


def _time(h, m, ap):
    h = int(h)
    return None if h > 12 else dt.time(h % 12 + (12 if ap.lower() == "p" else 0), int(m or 0))


def parse_jsonld(soup):
    out = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for it in items:
            if not isinstance(it, dict) or "Event" not in str(it.get("@type", "")):
                continue
            start = it.get("startDate") or ""
            if "T" not in start:
                continue
            try:
                d = dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
            except ValueError:
                continue
            if d.tzinfo:
                d = d.astimezone(ET)
            if d.hour == 0 and d.minute == 0:
                continue  # date only, no real time
            out.append({"title": it.get("name") or "", "date": d.date(), "time": d.time().replace(second=0),
                        "url": it.get("url") or "", "doors": it.get("doorTime") or ""})
    return out


def parse_rockhouse(soup, year_hint):
    out = []
    for card in soup.select(".rhpSingleEvent"):
        date_el = card.select_one(".eventDateList, .eventDateListTop, .singleEventDate")
        time_el = card.select_one(".eventDoorStartDate, .eventDateDetails")
        title_el = card.select_one("#eventTitle, .rhp-event__title--list, h2, h3")
        if not (date_el and time_el):
            continue
        dm = re.search(r"([A-Z][a-z]{2})\w*\.?\s+(\d{1,2})", date_el.get_text(" ", strip=True))
        if not dm:
            continue
        try:
            month = dt.datetime.strptime(dm.group(1), "%b").month
        except ValueError:
            continue
        day = int(dm.group(2))
        # Listings run ~a year ahead; pick the year that keeps the date in the future-ish window
        today = dt.date.today()
        year = year_hint
        cand = dt.date(year, month, day)
        if cand < today - dt.timedelta(days=30):
            cand = dt.date(year + 1, month, day)
        txt = time_el.get_text(" ", strip=True)
        show = re.search(r"show\W{0,6}" + CLOCK.pattern, txt, re.I)
        doors = re.search(r"doors?\W{0,6}" + CLOCK.pattern, txt, re.I)
        if show:
            t, src = _time(*show.groups()), "show"
        elif doors:
            t0 = _time(*doors.groups())
            t, src = ((dt.datetime.combine(cand, t0) + dt.timedelta(hours=1)).time() if t0 else None), "doors+1h"
        else:
            continue
        if not t:
            continue
        links = [a["href"] for a in card.find_all("a", href=True)
                 if re.search(r"etix|ticket|tixr|axs|dice|eventbrite", a["href"], re.I)]
        out.append({"title": title_el.get_text(" ", strip=True) if title_el else "", "date": cand, "time": t,
                    "url": links[0] if links else "", "src": src})
    return out


def scrape_aeg(venue_id, label):
    url = f"https://aegwebprod.blob.core.windows.net/json/events/{venue_id}/events.json"
    try:
        data = requests.get(url, headers=HEADERS, timeout=30).json()
    except Exception:
        return url, []
    out = []
    for e in data.get("events", []) if isinstance(data, dict) else data:
        when = e.get("eventDateTime") or ""
        if "T" not in when:
            continue
        try:
            d = dt.datetime.fromisoformat(when)
        except ValueError:
            continue
        title = e.get("title") or {}
        if isinstance(title, dict):
            title = " ".join(re.sub(r"<[^>]+>", "", str(title.get(k) or "")) for k in ("headliners", "supportingActs", "eventName"))
        out.append({"title": str(title), "date": d.date(), "time": d.time().replace(second=0),
                    "url": ((e.get("ticketing") or {}).get("url") or ""), "host": f"aeg:{label}"})
    return url, out


def scrape(url):
    if url.startswith("aeg:"):
        vid = url.split(":", 1)[1]
        return scrape_aeg(vid, AEG_JSON[vid])
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return url, []
    except Exception:
        return url, []
    soup = BeautifulSoup(r.text, "html.parser")
    items = parse_jsonld(soup)
    items += parse_rockhouse(soup, dt.date.today().year)
    host = urllib.parse.urlsplit(url).netloc.removeprefix("www.")
    for it in items:
        it["host"] = host
    return url, items


SCRAPED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "venues", "events.json")


def load_scraped(path=SCRAPED):
    """Records written by run_all.py (scrapers/), converted to index items. Only
    records with a real show time are useful here."""
    if not os.path.exists(path):
        return []
    with open(path) as f:
        recs = json.load(f)
    out = []
    for r in recs:
        if not r.get("show_time") or not r.get("date"):
            continue
        h, m = map(int, r["show_time"].split(":"))
        base = {"title": r.get("title") or "", "date": dt.date.fromisoformat(r["date"]),
                "time": dt.time(h, m), "host": r.get("venue") or "scraper"}
        for link in {r.get("ticket_url"), r.get("url")} - {None, ""}:
            out.append({**base, "url": link})
    return out


class VenueIndex:
    def __init__(self):
        self.by_url, self.by_date = {}, {}
        sources = LISTINGS + [f"aeg:{vid}" for vid in AEG_JSON]
        with ThreadPoolExecutor(max_workers=6) as pool:
            for url, items in pool.map(scrape, sources):
                self._add(items)
        scraped = load_scraped()
        self._add(scraped)
        n = sum(len(v) for v in self.by_date.values())
        print(f"venue sites: indexed {n} shows from {len(sources)} listing pages "
              f"+ {len(scraped)} links from venue scrapers", file=sys.stderr)

    def _add(self, items):
        for it in items:
            k = norm_url(it["url"])
            if k:
                self.by_url.setdefault(k, it)
            day = self.by_date.setdefault(it["date"], [])
            if not any(x["title"] == it["title"] and x["host"] == it["host"] for x in day):
                day.append(it)

    def find(self, ticket_url, date, title):
        """Return (time, source) or None."""
        hit = self.by_url.get(norm_url(ticket_url))
        if hit:
            return hit["time"], f"venue-site:{hit['host']}"
        want = tokens(title)
        best, score = None, 0.0
        for it in self.by_date.get(date, []):
            have = tokens(it["title"])
            if not want or not have:
                continue
            s = len(want & have) / min(len(want), len(have))
            if s > score:
                best, score = it, s
        if best and score >= 0.6:
            return best["time"], f"venue-site:{best['host']} (name match)"
        return None
