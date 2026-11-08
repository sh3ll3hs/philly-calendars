"""Parx Casino, Bensalem (Xcite Center, 360, Liberty Bell Gastropub, ...).

The calendar page is client-rendered from plain same-origin JSON, which answers
ordinary requests:
    GET /bensalem/calendar/days?page=N   (14 days per page)
    -> {"pagination": {"next": ...}, "data": [{"date","month","year", "events": [
         {"id","title","subtitle","start_time":"8:00pm","time_string","locations":[{"title"}],
          "tags":[{"title"}], ...}]}]}
`category`/`tag` URL params don't filter, so filtering is done here on tags.
Only entertainment is kept (not promotions, racing, drawings).
"""
import datetime as dt
import sys

from common import http
from common.normalize import first_time, month_num, record

VENUE = "Parx Casino"
URL = "https://www.parxcasino.com/bensalem/calendar/days?page={}"
PAGE_URL = "https://www.parxcasino.com/bensalem/calendar"
KEEP_TAGS = {"Entertainment", "Comedy", "Band", "Dj"}
MAX_PAGES = 60


def parse(data):
    out = []
    for day in data.get("data", []):
        try:
            m = month_num(str(day.get("month"))) or int(day.get("month"))
            d = dt.date(int(day["year"]), m, int(day["date"]))
        except (KeyError, TypeError, ValueError):
            continue
        for e in day.get("events", []):
            tags = {t.get("title") for t in e.get("tags", [])}
            if not tags & KEEP_TAGS:
                continue
            rooms = [l.get("title") for l in e.get("locations", []) if l.get("title")]
            show = first_time(e.get("start_time") or "") or first_time(e.get("time_string") or "")
            out.append(record(VENUE, e.get("title"), d, show_time=show, subtitle=e.get("subtitle") or None,
                              url=PAGE_URL, source="json", room=rooms[0] if rooms else None))
    return out


def fetch():
    out = []
    for n in range(1, MAX_PAGES + 1):
        r = http.get(URL.format(n), headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"})
        if "json" not in (r.headers.get("content-type") or ""):
            # Past the end of the calendar the site serves a bot-check page instead of
            # JSON. That is the stopping point - it is never answered or worked around.
            print(f"parx: page {n} was not JSON; stopping", file=sys.stderr)
            break
        data = r.json()
        if not data.get("data"):
            break
        out += parse(data)
        pag = data.get("pagination") or {}
        # `total` counts down the pages still to come; `next` is never empty.
        if not pag.get("next") or int(pag.get("total") or 0) <= 1:
            break
    return list({(e["date"], e["title"], e["show_time"]): e for e in out}.values())


if __name__ == "__main__":
    ev = fetch()
    print(len(ev), "records;", sum(e["needs_manual"] for e in ev), "need manual")
    for e in ev[:3]:
        print(e)
    sys.exit(0)
