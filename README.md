# Philly calendar feeds

Auto-updating iCal (`.ics`) subscriptions for Philadelphia event calendars that don't publish their own.
A GitHub Actions workflow rebuilds the feeds every 6 hours and publishes them via GitHub Pages.

| Calendar | Subscribe URL | Source |
|---|---|---|
| Philly DSA | `https://calendar.google.com/calendar/ical/baed11tvm1nnnb3am8ihpafq7c%40group.calendar.google.com/public/basic.ics` | native Google Calendar (no conversion needed) |
| Philly Gay Calendar | `https://sh3ll3hs.github.io/philly-calendars/feed.ics` | `pgc_to_ics.py` — site's agenda endpoint, 8-day rolling window + history |
| CreativePHL (OACCE arts) | `https://sh3ll3hs.github.io/philly-calendars/creativephl.ics` | `creativephl_to_ics.py` — calendar page's embedded event data, 6 months ahead |
| WKDU Philly Haps (concerts) | `https://sh3ll3hs.github.io/philly-calendars/wkdu.ics` | `wkdu_to_ics.py` — scrapes the listings table, venue addresses cached |
| WXPN concert calendar | `https://sh3ll3hs.github.io/philly-calendars/xpn.ics` | `xpn_to_ics.py` — site's Events Calendar REST API, all regions, all-day events |
| Grid Magazine events | `https://gridphilly.com/events/?ical=1` | native export (no conversion needed) |

Checked and not worth converting: Northeast Times community calendar (prose, last updated Jan 2025),
Sound Advice newsletter (last issue June 2025), Visit Philly (editorial, stale dates),
Filmadelphia (bot-blocked ticketing), DIY PHL (site gone).

## Scripts

- `pgc_to_ics.py` — builds `docs/feed.ics` from phillygaycalendar.com (corrects the site's 4-hour timezone bug by checking event pages).
- `creativephl_to_ics.py` — builds `docs/creativephl.ics` from creativephl.org (`--days-ahead` to widen the window).
- `wkdu_to_ics.py` — builds `docs/wkdu.ics` from wkdu.org/phillyhaps/all (shows default to 3 hours long).
- `xpn_to_ics.py` — builds `docs/xpn.ics` from xpn.org (`--regions "Philadelphia Area"` to filter).
- `calfind.py` — finds embedded calendar feeds on any site: `python3 calfind.py --deep URL`.

All plain Python 3, no dependencies.
