"""A Meetup group's events, read from the group's public events page
(https://www.meetup.com/<group>/events/), one request.

The page carries Next.js `__NEXT_DATA__`; props.pageProps.__APOLLO_STATE__ holds one
"Event:<id>" record per event (title, eventUrl, description, dateTime and endTime
with their UTC offset, eventType PHYSICAL / ONLINE / HYBRID, status ACTIVE / PAST /
CANCELLED) and the "Venue:<id>" record each one points to (name, address, city,
state). Times are converted to Eastern from the offset the page gives.

Why not the group's calendar file (/events/ical/): it leaves out the venue.

Kept: events whose status is not CANCELLED (past ones are dropped by the feed's date
window). An online event's place is "Online". The Meetup page is both the event page
and where to sign up.

robots.txt (2026-11-17): /<group>/events/ is allowed (only its /atom/, /rss/ and
/xml/ variants are disallowed).

Checked 2026-11-17 on meetup.com/queertech-toronto: QT Qonference 2026, Nov 18 8:00 AM
to Nov 19 5:00 PM Eastern, Evergreen Brick Works, 550 Bayview Ave, Toronto.

Known failure modes: Meetup renames `__NEXT_DATA__` or the record types (parse raises
ValueError, shown as an error for this source only); the page shows the group's next
few events, so a group with many scheduled shows the later ones as they come up.
"""
import json
import re

import combined_to_ics as C


def parse(body, src):
    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', body, re.S)
    if not m:
        raise ValueError("no __NEXT_DATA__ in the Meetup page")
    state = ((json.loads(m.group(1)).get("props") or {}).get("pageProps") or {}).get("__APOLLO_STATE__")
    if not isinstance(state, dict):
        raise ValueError("no __APOLLO_STATE__ in the Meetup page data")
    out = []
    for key, r in state.items():
        if not key.startswith("Event:") or not isinstance(r, dict) or str(r.get("status")).upper() == "CANCELLED":
            continue
        st = C.parse_iso(r.get("dateTime"))
        if not st:
            continue
        en = C.parse_iso(r.get("endTime"))
        ref = (r.get("venue") or {}).get("__ref") if isinstance(r.get("venue"), dict) else None
        v = state.get(ref) if ref else None
        if str(r.get("eventType")).upper() == "ONLINE" or r.get("isOnline"):
            loc = "Online"
        elif isinstance(v, dict):
            loc = ", ".join(x for x in (C.clean(v.get("name")), C.clean(v.get("address"))) if x)
            for extra in (C.clean(v.get("city")), C.clean(v.get("state"))):
                if extra and extra.lower() not in loc.lower():
                    loc += f", {extra}"
        else:
            loc = ""
        desc = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", str(r.get("description") or ""))     # markdown links -> their text
        desc = re.sub(r"[*#_]{1,3}", "", desc)
        url = str(r.get("eventUrl") or src["url"])
        e = C.event(src, r.get("id") or url, r.get("title"), st[0], en[0] if en and not st[1] and not en[1] else None,
                    st[1], loc, url, desc, rsvp=url)
        if e:
            out.append(e)
    return out


def read(src, ctx):
    return parse(C.get_text(src["url"]), src)
