# Philly calendar feeds

Auto-updating iCal (`.ics`) subscriptions for Philadelphia event calendars that don't publish their own.
A GitHub Actions workflow rebuilds the feeds every 6 hours and publishes them via GitHub Pages.

| Calendar | Subscribe URL | Source |
|---|---|---|
| Philly DSA | `https://calendar.google.com/calendar/ical/baed11tvm1nnnb3am8ihpafq7c%40group.calendar.google.com/public/basic.ics` | native Google Calendar (no conversion needed) |
| Philly Gay Calendar | `https://sh3ll3hs.github.io/philly-calendars/feed.ics` | `pgc_to_ics.py` — site's agenda endpoint, 8-day rolling window + history |
| CreativePHL (OACCE arts) | `https://sh3ll3hs.github.io/philly-calendars/creativephl.ics` | `creativephl_to_ics.py` — calendar page's embedded event data, 6 months ahead |
| WKDU Philly Haps (concerts) | `https://sh3ll3hs.github.io/philly-calendars/wkdu.ics` | `wkdu_to_ics.py` — scrapes the listings table, venue addresses cached |
| WXPN concert calendar | `https://sh3ll3hs.github.io/philly-calendars/xpn.ics` | `xpn_to_ics.py` + `xpn_times.py` — site's Events Calendar REST API; show times scraped from ticket pages and venues' own sites (~78% of shows), 8–11 PM placeholder for the rest |
| City of Philadelphia events | `https://sh3ll3hs.github.io/philly-calendars/phila.ics` | `phila_to_ics.py` — merges ~146 department Google Calendars behind phila.gov/the-latest/all-events, tagged by department |
| Grid Magazine events | `https://sh3ll3hs.github.io/philly-calendars/grid.ics` | `grid_to_ics.py` — site's REST API (the native `/events/?ical=1` export is capped at 30 events); daily runs collapsed to opening day |

Checked and not worth converting: Northeast Times community calendar (prose, last updated Jan 2025),
Sound Advice newsletter (last issue June 2025), Visit Philly (editorial, stale dates),
Filmadelphia (bot-blocked ticketing), DIY PHL (site gone).

## Scripts

- `pgc_to_ics.py` — builds `docs/feed.ics` from phillygaycalendar.com (corrects the site's 4-hour timezone bug by checking event pages).
- `creativephl_to_ics.py` — builds `docs/creativephl.ics` from creativephl.org (`--days-ahead` to widen the window). Recovers start times from the description text when the site marks an event "all day"; multi-week exhibitions show on their opening day as "(through <date>)".
- `grid_to_ics.py` — builds `docs/grid.ics` from gridphilly.com's REST API. Nightly/daily runs (markets, light shows) become one opening-day entry; weekly classes keep every date.
- `wkdu_to_ics.py` — builds `docs/wkdu.ics` from wkdu.org/phillyhaps/all (shows default to 3 hours long).
- `xpn_to_ics.py` — builds `docs/xpn.ics` from xpn.org (`--regions "Philadelphia Area"` to filter; `--start 19:30 --hours 3` to change the placeholder slot; `--all-day` for the old behaviour; `--no-scrape` to skip ticket pages).
- `xpn_times.py` — follows each XPN show's ticket link with requests + BeautifulSoup and reads the show time from schema.org data or "Show/Doors" text; results cached in `docs/xpn_times.json`. Ticketmaster, AXS, Tixr and Etix block automated requests, so for those shows it falls back to `venue_sites.py`. Needs `pip install requests beautifulsoup4`.
- `venue_sites.py` — indexes the venues' own public listings (JSON-LD on Ardmore / MilkBoy / Underground Arts / 118 North / Live Nation venue sites; Rockhouse "Doors | Show" cards on R5 and Johnny Brenda's; AEG's public events JSON for Union Transfer and Franklin Music Hall) and matches shows by ticket URL, then by date + artist name. Add a listing URL or AEG venue id to cover another venue.

  Checked and not recoverable from public pages (shows there keep the 8 PM placeholder): **Time** (Wix calendar widget, no data in the page), **SOUTH Jazz Club** (event pages carry no set times), **The Queen / Keswick / later Met & Fillmore dates** (Live Nation sites embed only their first ~36 shows; the rest come from an authenticated API; Keswick's site rejects all requests), **Xfinity Mobile Arena, Mann Center, Sellersville, Parx, Dawson Street Pub** (JavaScript-rendered or no time data).
- `phila_to_ics.py` — builds `docs/phila.ics` from the city's department calendars (drops recurring series that already ended; falls back to the saved calendar list if the city API blocks the request).
- `calfind.py` — finds embedded calendar feeds on any site: `python3 calfind.py --deep URL`.

All plain Python 3, no dependencies.
