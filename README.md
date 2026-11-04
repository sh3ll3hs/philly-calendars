# Philly calendar feeds

Auto-updating iCal (`.ics`) subscriptions for Philadelphia event calendars that don't publish their own.
A GitHub Actions workflow rebuilds the feeds every 6 hours and publishes them via GitHub Pages.

| Calendar | Subscribe URL | Source |
|---|---|---|
| Philly DSA | `https://calendar.google.com/calendar/ical/baed11tvm1nnnb3am8ihpafq7c%40group.calendar.google.com/public/basic.ics` | native Google Calendar (no conversion needed) |
| Philly Gay Calendar | `https://sh3ll3hs.github.io/philly-calendars/feed.ics` | `pgc_to_ics.py` — site's agenda endpoint, 8-day rolling window + history |
| CreativePHL (OACCE arts) | `https://sh3ll3hs.github.io/philly-calendars/creativephl.ics` | `creativephl_to_ics.py` — calendar page's embedded event data, 6 months ahead |

## Scripts

- `pgc_to_ics.py` — builds `docs/feed.ics` from phillygaycalendar.com (corrects the site's 4-hour timezone bug by checking event pages).
- `creativephl_to_ics.py` — builds `docs/creativephl.ics` from creativephl.org (`--days-ahead` to widen the window).
- `calfind.py` — finds embedded calendar feeds on any site: `python3 calfind.py --deep URL`.

All plain Python 3, no dependencies.
