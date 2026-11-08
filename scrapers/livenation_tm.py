"""Ticketmaster / Live Nation houses via the official Ticketmaster Discovery API.

Covers what public pages can't: the Met's and the Foundry's dates past the ~36 the
venue sites embed, Xfinity Mobile Arena (whose detail pages refuse ordinary
requests), and acts as a cross-check for the Queen and the Mann.

Needs a free key from developer.ticketmaster.com in the TM_API_KEY environment
variable (5,000 calls/day). Without it this module returns [] and says so.

Venue IDs are resolved once by keyword and cached in docs/venues/tm_venues.json.
Doors time is not a Discovery field; it is read from `info`/`pleaseNote` text when present.
"""
import datetime as dt
import json
import os
import re
import sys

from common import http
from common.normalize import first_time, record

API = "https://app.ticketmaster.com/discovery/v2"
CACHE = os.path.join(os.path.dirname(__file__), "..", "docs", "venues", "tm_venues.json")
VENUES = {  # display name -> (search keyword, state)
    "The Met Philadelphia": ("The Met Philadelphia", "PA"),
    "The Fillmore Philadelphia": ("The Fillmore Philadelphia", "PA"),
    "The Foundry": ("The Foundry at The Fillmore", "PA"),
    "Xfinity Mobile Arena": ("Xfinity Mobile Arena", "PA"),
    "The Queen": ("The Queen", "DE"),
    "Highmark Mann": ("Mann", "PA"),
}


def _venue_ids(key):
    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE) as f:
            cache = json.load(f)
    changed = False
    for name, (kw, state) in VENUES.items():
        if name in cache:
            continue
        data = http.get_json(f"{API}/venues.json", params={"apikey": key, "keyword": kw, "stateCode": state})
        found = (data.get("_embedded") or {}).get("venues") or []
        if found:
            cache[name] = found[0]["id"]
            changed = True
    if changed:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, "w") as f:
            json.dump(cache, f, indent=1, sort_keys=True)
    return cache


def parse(data, venue):
    out = []
    for e in (data.get("_embedded") or {}).get("events", []):
        start = (e.get("dates") or {}).get("start") or {}
        if not start.get("localDate"):
            continue
        t = start.get("localTime")
        show = t[:5] if t and not start.get("timeTBA") and not start.get("noSpecificTime") else None
        note = " ".join(x for x in (e.get("info"), e.get("pleaseNote")) if x)
        doors = re.search(r"doors?[^.\d]{0,15}(\d{1,2}(?::\d{2})?\s*[ap]\.?m)", note, re.I)
        acts = [a.get("name") for a in (e.get("_embedded") or {}).get("attractions", [])]
        pr = (e.get("priceRanges") or [{}])[0]
        price = f"${pr['min']:g} to ${pr['max']:g}" if pr.get("min") is not None and pr.get("max") is not None else None
        out.append(record(venue, e.get("name"), dt.date.fromisoformat(start["localDate"]),
                          show_time=show, doors_time=first_time(doors.group(1)) if doors else None,
                          subtitle=", ".join(acts[1:]) or None, url=e.get("url") or "",
                          ticket_url=e.get("url"), price=price, source="tm-discovery"))
    return out


def fetch():
    key = os.environ.get("TM_API_KEY")
    if not key:
        print("livenation_tm: TM_API_KEY not set - skipped", file=sys.stderr)
        return []
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    for venue, vid in _venue_ids(key).items():
        page = 0
        while True:
            data = http.get_json(f"{API}/events.json", params={
                "apikey": key, "venueId": vid, "size": 200, "sort": "date,asc",
                "startDateTime": now, "page": page})
            out += parse(data, venue)
            pages = (data.get("page") or {}).get("totalPages", 1)
            page += 1
            if page >= pages:
                break
    return list({(e["venue"], e["date"], e["title"]): e for e in out}.values())


if __name__ == "__main__":
    ev = fetch()
    print(len(ev), "records;", sum(e["needs_manual"] for e in ev), "need manual")
    for e in ev[:3]:
        print(e)
