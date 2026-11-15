"""
Hive76 (member-run makerspace, Kensington) — classes and events reader.

Page a person sees: https://www.hive76.org/classes/  (WordPress). The list on it is drawn
in the browser by the "Event Feed for Eventbrite" plugin, which loads
    https://www.hive76.org/wp-json/event-feed-for-eventbrite/v1/feed/7402
(one request per run, about 50 KB). 7402 is the feed's id, written in the page's inline
`EventFeedForEventbrite... = {"feed": {"ID": 7402, ...}, "api": "https://www.hive76.org/wp-json/"}`;
the route is the one the plugin's list script calls (`api + "event-feed-for-eventbrite/v1/feed/" + ID`).
robots.txt disallows only /wp-admin/.

The answer is {"events": [...]}: Hive76's own Eventbrite events as the plugin caches them,
at most 8 (the limit set on the feed, the same 8 the page shows). Each has `post_title`,
`start`/`end` with `utc`, `local` and `timezone`, a `venue` with a full address, the
Eventbrite `url`, `status`, and a `vue` block holding the exact text the page prints
("November 15, 2026 @ 2:30 pm").

No built-in method fits: the page's HTML holds no events and no schema.org data, and
there is no iCalendar feed.

Checked on 2026-11-15 against the text the page prints (`vue.start`, `vue.end`, `vue.location`):
  Hive76 Open House   November 15, 2026 @ 2:30 pm to 5:00 pm
  Hive76 Open House   November 22, 2026 @ 2:30 pm to 5:00 pm
  Hive76 Open House   November 29, 2026 @ 2:30 pm to 5:00 pm
  all at 1821 East Hagert Street #100c, Philadelphia, PA 19125

Known failure modes:
  * Only the next 8 events are published, so the feed reaches about 8 weeks ahead while
    the weekly open house fills it; a class further out appears once it is among the next 8.
  * Start and end come from the `utc` instants (converted to Philadelphia time); if those
    are missing the `local` wall time is used. An event with neither is dropped.
  * Cancelled events (`status` "canceled"/"cancelled") are dropped.
  * If the feed is rebuilt in WordPress its id changes and this URL answers 404; the new
    id is in the page source as described above.
"""
import json

import combined_to_ics as C

PAGE = "https://www.hive76.org/classes/"


def _when(block):
    """Eventbrite date block -> naive Philadelphia datetime, or None."""
    if not isinstance(block, dict):
        return None
    got = C.parse_iso(block.get("utc")) or C.parse_iso(block.get("local"))
    return got[0] if got and not got[1] else None


def _place(it):
    if it.get("online_event"):
        return "Online"
    v = it.get("venue") or {}
    a = v.get("address") or {}
    line = a.get("localized_address_display") or ", ".join(
        x for x in (C.clean(a.get("address_1")), C.clean(a.get("address_2")), C.clean(a.get("city")),
                    " ".join(y for y in (C.clean(a.get("region")), C.clean(a.get("postal_code"))) if y)) if x)
    return C.address({"name": v.get("name"), "address": line})


def parse(body, src):
    data = json.loads(body)
    items = data.get("events") if isinstance(data, dict) else data
    out = []
    for it in items or []:
        if not isinstance(it, dict) or str(it.get("status") or "").lower() in ("canceled", "cancelled"):
            continue
        st = _when(it.get("start"))
        if not st:
            continue
        e = C.event(src, it.get("ID") or it.get("url") or f"{it.get('post_title')}|{st}", it.get("post_title"), st,
                    _when(it.get("end")), False, _place(it), it.get("url") or src.get("page") or PAGE,
                    it.get("post_content"))
        if e:
            out.append(e)
    return out


def read(src, ctx):
    return parse(C.get_text(src["url"]), src)
