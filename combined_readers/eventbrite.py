"""Eventbrite: in-person events in Philadelphia, read from the data Eventbrite renders
into its own public pages. No API, no token.

Two kinds of page are understood (the reader picks by what the page holds):

  * a destination search listing, e.g.
        https://www.eventbrite.com/d/pa--philadelphia/free--events/
    The HTML carries `window.__SERVER_DATA__ = {...}`; the 20 events of the page
    are in search_data.events.results. Further pages are `?page=2`, `?page=3`...
    The entry's "pages" (default 1, never more than 5) says how many to read, so
    a run makes at most 5 requests. An entry may instead give "urls": a list of
    up to 5 listing URLs.
  * an organizer page, e.g. https://www.eventbrite.com/o/<name>-<id> (or /o/<id>).
    The HTML carries Next.js `__NEXT_DATA__`; the organizer's upcoming events are
    in props.pageProps.upcomingEvents (one request). That is the first screen
    only: the next 12 events, soonest first (hasMoreUpcoming says when there are
    more; the page's "Show more" call is not used).

On both kinds of page a repeating series is one record, dated at its next
occurrence; the later dates of the series are not listed and show up run by run.

Both give, per event: name, start_date + start_time and end_date + end_time as
wall-clock values in the event's own `timezone`, is_online_event, is_cancelled,
and primary_venue with a full address. The wall time is converted from the event's
time zone to America/New_York (the same thing for nearly every Philadelphia event).

What is kept: events with a venue in Philadelphia, PA. Dropped: online events,
cancelled or postponed events (see called_off), events elsewhere (the
Philadelphia search also returns Camden, Cherry Hill and other nearby towns),
and events whose organizer hid the start date (nothing on the site to check a
time against). The end is left out when the organizer hid it or when it equals
the start (organizer pages repeat the start time as the end time; the feed then
uses its default length).

Search listings are a ranked sample, not a complete list: an event can be on page
3 today and page 9 tomorrow. So that events do not flicker in and out of the
calendar, each event read from a listing is remembered in ctx["detail"] (keyed by
its event URL) and is still returned for KEEP_DAYS days after it was last seen, as
long as it has not started. The cost: an event cancelled or moved after it fell
off the listing stays for up to KEEP_DAYS days. An organizer page lists its
events in date order (one that is missing is over or withdrawn), so nothing is
remembered for those. An entry can set "keep_days" (0 turns it off).

robots.txt (checked 2026-11-15, `User-agent: *`): /d/, /o/ and /e/ are not
disallowed and neither is `?page=N`. /api/v3/destination/events/ IS disallowed
and is not used. Links are the plain event URL, without tracking parameters.

Checked against (2026-11-15): pages 1-5 of the free Philadelphia listing and the
organizer pages of People's Cinema Club, Riot Nerd and HoneyTree EvilEye; times
compared with four event pages (/e/...), whose schema.org startDate carries the
UTC offset and whose visible text gives the clock time ("6:30 PM - 9 PM").

Known failure modes: Eventbrite renames or removes `__SERVER_DATA__` /
`__NEXT_DATA__` (parse raises ValueError: the source shows as an error, other
sources are unaffected); an organizer page whose own event lookup failed
(upcomingEventsFailed, raised as an error rather than read as "no events"); a
403/406 (reported as blocked, never worked around).
"""
import datetime as dt
import json
import re
from zoneinfo import ZoneInfo

import combined_to_ics as C

MAX_PAGES = 5      # requests per run, at most
KEEP_DAYS = 7      # how long a listing event is remembered after it was last seen


def records(body):
    """The event records embedded in a search listing page or an organizer page."""
    i = body.find("window.__SERVER_DATA__")
    if i >= 0:
        data = json.JSONDecoder().raw_decode(body, body.index("{", i))[0]
        return ((data.get("search_data") or {}).get("events") or {}).get("results") or []
    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', body, re.S)
    if m:
        props = (json.loads(m.group(1)).get("props") or {}).get("pageProps") or {}
        if props.get("upcomingEventsFailed"):
            raise ValueError("Eventbrite could not load this organizer's events (upcomingEventsFailed)")
        if "upcomingEvents" in props:
            first = [props["featuredEvent"]] if isinstance(props.get("featuredEvent"), dict) else []
            return first + (props.get("upcomingEvents") or [])
    raise ValueError("no Eventbrite event data in the page (__SERVER_DATA__ / __NEXT_DATA__ not found)")


def in_philadelphia(rec):
    """True when the event's venue is in Philadelphia, PA."""
    # Eventbrite's own place hierarchy for the venue (search listings only), then the written address
    names = {(p.get("type"), p.get("name")) for p in rec.get("locations") or [] if isinstance(p, dict)}
    if ("region", "Pennsylvania") in names and {("locality", "Philadelphia"), ("county", "Philadelphia")} & names:
        return True
    a = (rec.get("primary_venue") or {}).get("address") or {}
    return C.clean(a.get("city")).lower().startswith("philadelphia") and \
        C.clean(a.get("region")).lower() in ("pa", "pennsylvania")


def called_off(rec):
    """Cancelled or postponed. Search records carry is_cancelled; an organizer page leaves
    that false and marks the event in event_sales_status (message_code "event_cancelled",
    message "Cancelled"), which is what its "Cancelled" badge is drawn from."""
    if rec.get("is_cancelled"):
        return True
    s = rec.get("event_sales_status") or {}
    return bool(re.search(r"cancel|postpon", f"{s.get('message_code')} {s.get('message')}", re.I))


def when(day, clock, zone):
    """(date 'YYYY-MM-DD', clock 'HH:MM[:SS]', IANA zone) -> (New York wall time, False),
    or (date, True) when there is no clock time. None if the date is unreadable."""
    try:
        d = dt.date.fromisoformat(str(day or "")[:10])
    except ValueError:
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})", str(clock or ""))
    if not m:
        return d, True
    try:
        tz = ZoneInfo(str(zone))
    except Exception:
        tz = C.NY
    return C.local(dt.datetime.combine(d, dt.time(int(m.group(1)), int(m.group(2))), tzinfo=tz)), False


def place(venue):
    """Venue name plus Eventbrite's one-line address (street, city, state, ZIP)."""
    a = venue.get("address") or {}
    full = C.clean(a.get("localized_address_display")) or ", ".join(
        x for x in (C.clean(a.get("address_1")), C.clean(a.get("city")),
                    " ".join(y for y in (C.clean(a.get("region")), C.clean(a.get("postal_code"))) if y)) if x)
    name = C.clean(venue.get("name"))
    # a venue without a name of its own is entered as its street ("2233 N 7th St"): one copy is enough
    if not name or (full and C.address({"name": name, "address": C.clean(a.get("address_1"))}) == name):
        return full or name
    return f"{name}, {full}" if full else name


def parse(body, src):
    out, seen = [], set()
    for r in records(body):
        if not isinstance(r, dict) or r.get("is_online_event") or called_off(r) or r.get("hide_start_date"):
            continue
        venue = r.get("primary_venue") or {}
        if not venue or not in_philadelphia(r):
            continue
        st = when(r.get("start_date"), r.get("start_time"), r.get("timezone"))
        if not st:
            continue
        start, all_day = st
        end = None
        if r.get("end_date") and not r.get("hide_end_date"):
            en = when(r.get("end_date"), None if all_day else r.get("end_time"), r.get("timezone"))
            if en and en[1] == all_day and en[0] > start:
                end = en[0]
        url = str(r.get("url") or "").split("?")[0].split("#")[0]
        key = r.get("id") or r.get("eventbrite_event_id") or url
        if not url or key in seen:
            continue
        seen.add(key)
        e = C.event(src, key, r.get("name"), start, end, all_day, place(venue), url, r.get("summary"))
        if e:
            out.append(e)
    return out


def page_urls(src):
    if src.get("urls"):
        return list(src["urls"])[:MAX_PAGES]
    base = src["url"]
    try:
        n = max(1, min(int(src.get("pages", 1)), MAX_PAGES))
    except (TypeError, ValueError):
        n = 1
    return [base] + [f"{base}{'&' if '?' in base else '?'}page={i}" for i in range(2, n + 1)]


def read(src, ctx):
    found = {}
    for n, u in enumerate(page_urls(src)):
        try:
            got = parse(C.get_text(u), src)
        except C.http.BlockedError:
            raise
        except Exception:
            if n == 0:
                raise
            break                       # a later page failed: keep what the earlier ones gave
        for e in got:
            found.setdefault(e["url"], e)
    out = list(found.values())

    keep = src.get("keep_days", KEEP_DAYS if "/d/" in src["url"] else 0)
    cache, today = ctx.get("detail"), ctx["today"]
    if not keep or not isinstance(cache, dict):
        return out
    for u, c in list(cache.items()):    # listing events seen on an earlier run
        evs = c.get("events") or []
        if u in found or len(evs) != 1 or evs[0].get("src") != src["id"]:
            continue
        try:
            age = (today - dt.date.fromisoformat(c["fetched"])).days
            e = C.unpack(evs[0])
        except (KeyError, TypeError, ValueError):
            continue
        if age < int(keep) and C.day_of(e) >= today:
            out.append(e)
    for u, e in found.items():
        cache[u] = {"fetched": today.isoformat(), "events": [C.pack(e)]}
    return out
