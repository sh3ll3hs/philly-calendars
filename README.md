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
| Grid Magazine events | `https://sh3ll3hs.github.io/philly-calendars/grid.ics` | `tribe_to_ics.py grid` — site's REST API (the native `/events/?ical=1` export is capped at 30 events) |
| Delaware County Arts Consortium | `https://sh3ll3hs.github.io/philly-calendars/delcoarts.ics` | `tribe_to_ics.py delcoarts` — same method |
| County Lines Magazine (Delco, Chester County, Main Line) | `https://sh3ll3hs.github.io/philly-calendars/countylines.ics` | `tribe_to_ics.py countylines` — same method |
| Philly Family | `https://sh3ll3hs.github.io/philly-calendars/phillyfamily.ics` | `tribe_to_ics.py phillyfamily` — same method |
| Bartram's Garden | `https://sh3ll3hs.github.io/philly-calendars/bartrams.ics` | `tribe_to_ics.py bartrams` — same method (the site's own `?ical=1` link triggers an "insecure connection" warning in Apple Calendar) |
| Free Library of Philadelphia | `https://sh3ll3hs.github.io/philly-calendars/flp.ics` | `flp_to_ics.py` — the library's per-branch RSS feeds (the calendar site itself is behind a Cloudflare challenge); accumulates daily |
| Everything else, combined | `https://sh3ll3hs.github.io/philly-calendars/combined.ics` | `combined_to_ics.py` — 160 sites listed in `combined_sources.json` (museums, parks, bars, galleries, theatres, neighborhood groups, Eventbrite organizers), each read by the best method it offers; see "Combined feed" below |
| Queer Tech Events (LGBTQ+ career, tech and business organizations, nationwide) | `https://sh3ll3hs.github.io/philly-calendars/queertech.ics` | `combined_to_ics.py --sources queertech_sources.json` — Out in Tech, Out Professionals, Independence Business Alliance, TransWork, StartOut, Out & Equal, Build Out Alliance, LGBT Tech, NGLCC, QueerTech, Unicorns in Tech, Queer Design Club, Out Leadership, Reaching Out MBA, Out for Undergrad, Lesbians Who Tech; every event has its place, its page and a sign-up line; see "Queer Tech Events feed" below |

Checked and not worth converting: Northeast Times community calendar (prose, last updated Jan 2025),
Sound Advice newsletter (last issue June 2025), Visit Philly (editorial, stale dates),
Filmadelphia (bot-blocked ticketing), DIY PHL (site gone).

## Scripts

- `pgc_to_ics.py` — builds `docs/feed.ics` from phillygaycalendar.com (corrects the site's 4-hour timezone bug by checking event pages).
- `creativephl_to_ics.py` — builds `docs/creativephl.ics` from creativephl.org (`--days-ahead` to widen the window). Recovers start times from the description text when the site marks an event "all day"; multi-week exhibitions show on their opening day as "(through <date>)".
- `tribe_to_ics.py <site>` — builds a full feed for any site running The Events Calendar plugin (`grid`, `delcoarts`, `countylines`, `phillyfamily`; add a line to `SITES` for another). Location is written once as "Venue, street, city, ST zip" (repeats removed, state filled from the ZIP). The event's link button opens the organizer's own page when the site lists one; the description ends with "Event website" and "Listing" links. Nightly/daily runs become one opening-day entry; weekly classes keep every date. `grid_to_ics.py` is kept as a shortcut for `tribe_to_ics.py grid`.
- `wkdu_to_ics.py` — builds `docs/wkdu.ics` from wkdu.org/phillyhaps/all (shows default to 3 hours long).
- `xpn_to_ics.py` — builds `docs/xpn.ics` from xpn.org (`--regions "Philadelphia Area"` to filter; `--start 19:30 --hours 3` to change the placeholder slot; `--all-day` for the old behaviour; `--no-scrape` to skip ticket pages).
- `xpn_times.py` — follows each XPN show's ticket link with requests + BeautifulSoup and reads the show time from schema.org data or "Show/Doors" text; results cached in `docs/xpn_times.json`. Ticketmaster, AXS, Tixr and Etix block automated requests, so for those shows it falls back to `venue_sites.py`. Needs `pip install requests beautifulsoup4`.
- `venue_sites.py` — indexes the venues' own public listings (JSON-LD on Ardmore / MilkBoy / Underground Arts / 118 North / Live Nation venue sites; Rockhouse "Doors | Show" cards on R5 and Johnny Brenda's; AEG's public events JSON for Union Transfer and Franklin Music Hall) plus everything in `docs/venues/events.json` from the venue scrapers below, and matches shows by ticket URL, then by date + artist name.
- `phila_to_ics.py` — builds `docs/phila.ics` from the city's department calendars (drops recurring series that already ended; falls back to the saved calendar list if the city API blocks the request).
- `flp_to_ics.py` — builds `docs/flp.ics` from `libwww.freelibrary.org/rss/eventsrss.cfm`. Each feed returns only the next 10 events, so it walks every branch (codes from the RSS menu) and, for busy branches, each category, and merges into `docs/flp_history.json`. Times come from the line every item ends with ("11/12/26, 10:00 A.M. - Andorra Library"); events are 1 hour long by default. Runs at most once per 20 h. Busy branches (Parkway Central) only reach a week or two ahead; cancellations aren't detected.
- `combined_to_ics.py` — builds `docs/combined.ics` from every source in `combined_sources.json`. Rebuilds on every morning run (5–10 AM Eastern) and otherwise at most once every 11 h; `--only id1,id2 --force` tests a few sources, `--list` prints them. Needs `pip install requests beautifulsoup4`.
- `combined_to_ics.py --sources queertech_sources.json --out docs/queertech.ics --state docs/queertech_state.json --name "Queer Tech Events" --rsvp-lines --days-ahead 400` — the same engine, building the Queer Tech Events feed.
- `calfind.py` — finds embedded calendar feeds on any site: `python3 calfind.py --deep URL`.

The feed scripts are plain Python 3; `xpn_times.py` and the venue scrapers need `pip install requests beautifulsoup4`.

## Combined feed (`combined_to_ics.py`)

One feed for every source that does not have a feed of its own above. `combined_sources.json` holds one entry per site: `id`, `name`, `method`, `url`, and optionally `venue` (used as the location when the site gives none), `params`, `page`, `tz`, `skip` (a pattern for titles to drop, such as "CLOSED"), `off`.

| `method` | Reads | Notes |
|---|---|---|
| `ics` | any public iCalendar feed (Google Calendar, Tockify, Luma `api.lu.ma/ics/get?entity=calendar&id=…`) | events pass through as published, so repeating events keep their rule; reminders are stripped |
| `tribe` | The Events Calendar REST API | `params: {"venue": "466"}` narrows a shared calendar to one venue |
| `squarespace` | a Squarespace events-list page, from its HTML | the tidier `?format=json` view is disallowed by the robots.txt every Squarespace site ships with, so it is not used; calendar-view pages therefore yield nothing |
| `spothopper` | `spothopperapp.com/api/spots/<id>/events` | restaurant and bar sites; `page` is the link events open |
| `jsonld` | schema.org `Event` data in the page | set `"tz": "utc_wall"` for a site whose data applies its UTC offset twice (Weavers Way) |
| `wix` | the Wix Events data block in the page | |
| `html` | follows the page's links to event pages and reads schema.org data there | event pages are cached for a week in `docs/combined_state.json` |
| `text` | a plain page: each small block with one written date and a heading or link | all-day unless the block states a time; switch a source to this only after checking its output by hand |
| `custom` | a site-specific reader, `combined_readers/<reader>.py` | each module's docstring says what it reads, what it was checked against and how it can break; each has a saved sample and a test |

Events are de-duplicated across sources by title + start time, nightly runs fold into one "(daily through …)" entry, "midnight to 11:59 PM" items become all-day, and a site that answers 403/406 is reported and skipped. Requests carry an honest user agent: several sites refuse a browser-like one outright.

To add a source: find the method with `python3 calfind.py --deep URL` and the table above, add an entry, run `python3 combined_to_ics.py --only <id> --force --out /tmp/t.ics --state /tmp/t.json`, and compare a few events with the site.

Site-specific readers so far: Barnes Foundation, Bob & Barbara's, Center City Events, Cherry Street Pier, Curtis Institute, Delaware River Waterfront, Eventbrite (one organizer page per recurring organizer; the general Philadelphia listing is switched off because Eventbrite refuses GitHub's runner on it), Evil Genius, Hive76, ICA, Mural Arts, Navy Yard, Independence National Historical Park, Parks on Tap, Philadelphia Museum of Art, The Rotunda, Schuylkill Banks, Science History Institute, SideQuest Theater (Crowdwork), The Rail Park.

Rules every reader follows: check robots.txt before relying on a path; a 403/406 or bot challenge means the source is left out (Tixr, Temple, Penn Libraries, GivePulse's API); MATO and Instagram are never requested.

Entries marked `"off": true` (72 of them) are events pages with no feed and no structured data; `needs` says what each is waiting for. They are skipped until someone writes a reader.

## Queer Tech Events feed (`queertech_sources.json`)

One feed of events from LGBTQ+ organizations that work on jobs and careers in tech, engineering, consulting, business and education. It is built by `combined_to_ics.py` from its own source list, with three differences from the combined feed:

- **Events anywhere, times in Eastern.** These are national groups, so an event keeps whatever city it is in (or "Online"). Each clock time is moved to Eastern from the zone the source states (Eventbrite and Meetup give one; Out & Equal prints "ET") or, where the site prints local time at the venue (Out in Tech, Build Out Alliance: `"tz": "venue"`), from the venue's address (`combined_readers/zones.py`). When the zone cannot be told, the event is all-day and the printed time is quoted in its notes. Nothing is guessed.
- **A sign-up line on every event** (`--rsvp-lines`): `RSVP: <link>` when the source gives a registration link (Eventbrite, Meetup, a "Register" button; for Build Out Alliance the link is read from each event's own page, `"rsvp_pages": true`), otherwise `RSVP: on the event page`.
- **400 days ahead**, so next year's conferences show up as soon as they are announced.

| Source | Read from | Notes |
|---|---|---|
| Out in Tech | outintech.com/events/ and each event page (`qt_outintech`) | only the events the page lists in its own HTML; the Accelevents widget on the same page is drawn by script and cannot be read |
| Out Professionals, StartOut (two organizer pages), Unicorns in Tech, Queer Design Club | Eventbrite organizer pages (`eventbrite`, `"anywhere": true`) | the next 12 events of each organizer |
| Independence Business Alliance | the event cards on thinkiba.com (`qt_thinkiba`) | the few next events; the members calendar answers 403 to scripts |
| TransWork | transwork.org/events and each event page (`qt_transwork`) | Philadelphia job-search and networking events |
| Out & Equal | outandequal.org/events/ (`qt_outandequal`) | many events are for partner companies only |
| Build Out Alliance | its Squarespace events list (`squarespace`) | architecture, engineering, construction |
| LGBT Tech, NGLCC | Wix Events data in the page (`wix`) | |
| QueerTech (Montréal, Toronto, Calgary, Edmonton, Vancouver) | each Meetup group's events page (`qt_meetup`) | Meetup's calendar files leave out the venue |
| Out Leadership | outleadership.com/events/ (`qt_outleadership`) | dates only: the site gives no time zone |
| Reaching Out MBA, Out for Undergrad, Lesbians Who Tech & Allies | conference pages with a heading, a date line and a place (`qt_dateline`) | all-day; only dates written with their year |

Looked at and left out: oSTEM, myGwork and Campus Pride (403 to scripts); Pride at Work Canada (its robots.txt turns away automated agents by name); the Consortium of Higher Education LGBT Resource Professionals (its calendar export answers 403); Point Foundation, Gaingels, Pride in STEM, Trans Can Work, TransTech Social, Maven Youth, Out to Innovate, Queer in AI, 500 Queer Scientists, LGBTQ Leaders in Higher Education and the LGBTQ in Technology Slack (no dated upcoming events on a page a script can read, as of November 2026). To add one later, add an entry to `queertech_sources.json` and test it with `--only <id> --force`.

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
