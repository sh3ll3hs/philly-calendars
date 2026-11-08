# Philly calendar feeds

Auto-updating iCal (`.ics`) subscriptions for Philadelphia event calendars that don't publish their own.
A GitHub Actions workflow rebuilds the feeds every 6 hours and publishes them via GitHub Pages.

| Calendar | Subscribe URL | Source |
|---|---|---|
| Philly DSA | `https://calendar.google.com/calendar/ical/baed11tvm1nnnb3am8ihpafq7c%40group.calendar.google.com/public/basic.ics` | native Google Calendar (no conversion needed) |
| Philly Gay Calendar | `https://sh3ll3hs.github.io/philly-calendars/feed.ics` | `pgc_to_ics.py` — site's agenda endpoint, 8-day rolling window + history |
| CreativePHL (OACCE arts) | `https://sh3ll3hs.github.io/philly-calendars/creativephl.ics` | `creativephl_to_ics.py` — calendar page's embedded event data, 6 months ahead |
| WKDU Philly Haps (concerts) | `https://sh3ll3hs.github.io/philly-calendars/wkdu.ics` | `wkdu_to_ics.py` — scrapes the listings table, venue addresses cached |
| WXPN concert calendar | `https://sh3ll3hs.github.io/philly-calendars/xpn.ics` | `xpn_to_ics.py` + `xpn_times.py` — site's Events Calendar REST API; show times scraped from ticket pages and venues' own sites (~83% of shows; see Venue scrapers below), 8–11 PM placeholder for the rest |
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
- `venue_sites.py` — indexes the venues' own public listings (JSON-LD on Ardmore / MilkBoy / Underground Arts / 118 North / Live Nation venue sites; Rockhouse "Doors | Show" cards on R5 and Johnny Brenda's; AEG's public events JSON for Union Transfer and Franklin Music Hall) plus everything in `docs/venues/events.json` from the venue scrapers below, and matches shows by ticket URL, then by date + artist name.
- `phila_to_ics.py` — builds `docs/phila.ics` from the city's department calendars (drops recurring series that already ended; falls back to the saved calendar list if the city API blocks the request).
- `calfind.py` — finds embedded calendar feeds on any site: `python3 calfind.py --deep URL`.

The feed scripts are plain Python 3; `xpn_times.py` and the venue scrapers need `pip install requests beautifulsoup4`.

## Venue scrapers (`scrapers/`)

Per-venue modules for venues whose shows don't get a time any other way. Each exposes `fetch() -> list[dict]` in one record shape (`venue, title, subtitle, date, show_time, doors_time, set_times, url, ticket_url, price, source, needs_manual`, plus `room` where relevant). Shared code: `common/http.py` (browser UA, retries with backoff, 1.5 s per-domain delay; a 403/406 raises `BlockedError` and is never worked around) and `common/normalize.py` (`normalize_time`, year inference, multi-date expansion).

```
python3 run_all.py --out-dir docs/venues     # writes events.json + events.csv, prints the per-venue gap
python3 -m scrapers.queen                    # one venue: count + first 3 records
python3 -m unittest discover -s tests -v     # parser tests against saved pages in tests/fixtures/
```

| Venue | Source | Known failure modes |
|---|---|---|
| **SOUTH Jazz Club** | `/jazz-club/` pipe lines (`ARTIST \| FRI, SAT & SUN NOV 13, 14 & 15 \| 7:00PM & 9:30PM`), multi-day runs expanded; for "showtimes vary", the event page's "FRIDAY & SATURDAY SHOWTIMES …" lines per weekday | Some shows publish no time anywhere (needs_manual). Tock reservation slots are deliberately ignored (they're ~1 h before the set). Tribe REST API returns 403. |
| **Highmark Mann** | `/events` + season pages → detail pages (`Doors \| 6:00PM \| Showtime \| 7:00PM`, stage, Ticketmaster link) | The add-to-calendar time on detail pages is wrong and ignored. Off-season the list is short. |
| **Sellersville Theater** | `/upcoming-shows/`, `/p2/` … (`Show \| 8:00PM // Doors \| 7:30PM`, room, price, Etix link) | No year on cards (inferred). List isn't sorted. |
| **Parx Casino** | same-origin JSON `/bensalem/calendar/days?page=N`, filtered to Entertainment/Comedy/Band/DJ tags | After ~10 pages the site serves an Incapsula bot check instead of JSON; the scraper stops there (≈140 days ahead). Endpoint may drift. |
| **Dawson Street Pub** | `http://beta.dawsonstreetpub.com/index.php`, `#eventschedule` table, one request per run | Times are almost never listed (needs_manual by design). Raises if `#eventschedule` disappears. The beta host could be retired. |
| **The Queen** | Yoast `fad_tm_event-sitemap.xml` → event pages (`Saturday · December 5 · 08:00PM`, `DOORS: 7:00 PM`, room, Ticketmaster link) | The `/shows/` list is client-rendered and there's no REST events route; the sitemap is the only full index. |
| **Ticketmaster houses** (`livenation_tm.py`) | Official Discovery API: Met, Fillmore, Foundry, Xfinity Mobile Arena, plus Queen/Mann cross-check | **Dormant until a `TM_API_KEY` repo secret exists** (free key from developer.ticketmaster.com). Doors only when `pleaseNote` mentions it. |

Not scraped, on purpose: **Keswick Theatre** and **Xfinity Mobile Arena** pages answer ordinary requests with 406. They only load when the request imitates a browser's fetch metadata, which is getting past bot protection, so they're left to the Discovery API (Xfinity) or the placeholder (Keswick, an AXS house). **Time** (Wix widget with no data in the page) also stays on the placeholder.
