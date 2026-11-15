"""
The Rail Park (Friends of the Rail Park) — events reader.

Source: the Gatsby page data behind https://www.therailpark.org/news-and-events/ :
    https://www.therailpark.org/page-data/news-and-events/page-data.json
(one request per run; the site has no robots.txt). `result.data.allPrismicEvent.edges[].node`
holds every published event from the site's Prismic CMS: title, `start` / `end` as UTC
instants ("2026-10-29T21:30:00+0000"), `all_day`, `cost`, `tags`, `location` (venue +
address) and the repeat fields `recurring_event`, `frequency` (Daily / Weekly / Monthly /
Yearly), `interval`, `recurring_end`, `excluded_dates`. The events list on the page itself
is drawn by JavaScript from this same data, so the built-in `text` method finds nothing.

TIME ZONE: the instants are true UTC and the site's script shows them in the visitor's
own time zone, so 21:30Z is 5:30 PM in Philadelphia. The static HTML of an event page was
rendered on a UTC build server and reads "Thursday, October 29, 2026 @ 9:30 PM - 11:00 PM"
until the script runs; that is not the local time. This reader converts to America/New_York.

Checked on 2026-11-15: October Yappy Hour (Thu Oct 29, 21:30Z-23:00Z = 5:30-7:00 PM, The
Rail Park, 1300 Block of Noble Street), Tour the Rail Park! (Sat Nov 14, 15:00Z-17:00Z =
10:00 AM-noon, $20) and Love Your Park (Sat Nov 14, marked all day) against the event
pages (date, venue, cost) and the site's script (app-*.js, the function that maps
`allPrismicEvent`). The reference calendar had October Yappy Hour at 4:30 PM, one hour
before this; it ran one hour early on every site in this batch where an event could be compared.

Known failure modes:
  * Page data is a build-time snapshot; an event appears when the site is rebuilt.
  * The listing data has no description; the event's types and cost are used instead
    (the site prints "Free" when no cost is entered).
  * An event marked `all_day` is all-day here even when its instants carry clock times,
    because that is what the site shows.
  * Repeating events: no published event repeated when this was written, so that branch
    follows the site's script but has not been compared with a live example. Occurrences
    keep the first one's local clock time, step by `interval` days / weeks / months / years,
    stop at `recurring_end` (counted the way the site's month view does: the UTC date of the
    occurrence must not be after it) and skip `excluded_dates`. A repeating event with no
    `recurring_end` yields only its first date.
  * If the Gatsby template or the Prismic field names change, the reader returns nothing.
"""
import datetime as dt
import json
import urllib.parse

import combined_to_ics as C

MAX_OCCURRENCES = 400


def data_url(page_url):
    p = urllib.parse.urlsplit(page_url)
    return f"{p.scheme}://{p.netloc}/page-data/{p.path.strip('/')}/page-data.json"


def _location(rows):
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        addr = row.get("address")
        loc = C.address({"name": row.get("venue"), "address": addr.get("text") if isinstance(addr, dict) else addr})
        if loc:
            return loc
    return ""


def _add_months(d, months):
    """Same day of the month `months` later; None when that month has no such day."""
    y, m = divmod(d.year * 12 + d.month - 1 + months, 12)
    try:
        return d.replace(year=y, month=m + 1)
    except ValueError:
        return None


def _occurrences(first, freq, interval, shift, until, excluded):
    """Local start times of a repeating event. `shift` is UTC minus local for the first
    occurrence; the site compares UTC dates with `recurring_end` and `excluded_dates`."""
    try:
        step = max(1, int(interval or 1))
    except (TypeError, ValueError):
        step = 1
    out, k = [], 0
    while len(out) < MAX_OCCURRENCES and k < 4000:
        if freq == "Daily":
            d = first + dt.timedelta(days=step * k)
        elif freq == "Weekly":
            d = first + dt.timedelta(weeks=step * k)
        elif freq == "Monthly":
            d = _add_months(first, step * k)
        else:
            d = _add_months(first, 12 * step * k)
        k += 1
        if d is None:
            continue
        if (d + shift).date() > until:
            break
        if d.date().isoformat() in excluded or (d + shift).date().isoformat() in excluded:
            continue
        out.append(d)
    return out


def parse(body, src):
    """Page data (JSON text or the decoded object) -> events."""
    data = json.loads(body) if isinstance(body, (str, bytes)) else body
    try:
        edges = data["result"]["data"]["allPrismicEvent"]["edges"]
    except (KeyError, TypeError):
        return []
    root = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(src["url"]))
    out = []
    for edge in edges or []:
        node = (edge or {}).get("node") or {}
        d = node.get("data") or {}
        if node.get("lang") not in (None, "en-us") or not d.get("start"):
            continue
        st = C.parse_iso(d["start"])
        if not st or st[1]:
            continue
        start = st[0]
        en = C.parse_iso(d["end"]) if d.get("end") else None
        end = en[0] if en and not en[1] and en[0] > start else None
        url = urllib.parse.urljoin(root, node.get("url") or "") if node.get("url") else src["url"]
        types = ", ".join(t["event_type"] for t in d.get("tags") or [] if isinstance(t, dict) and t.get("event_type"))
        cost = C.clean(d.get("cost"))
        cost = "Free" if not cost else f"${cost}" if cost.replace(".", "", 1).isdigit() else cost
        desc = "\n".join(x for x in (types, cost) if x)
        loc = _location(d.get("location"))
        key = node.get("id") or url

        starts = [start]
        until = C.parse_iso(d.get("recurring_end")) if d.get("recurring_end") else None
        if d.get("recurring_event") and until:
            shift = C.parse_iso(d["start"], True)[0] - start
            last = until[0] if until[1] else until[0].date()
            excluded = {str(x.get("date")) for x in d.get("excluded_dates") or [] if isinstance(x, dict) and x.get("date")}
            starts = _occurrences(start, d.get("frequency"), d.get("interval"), shift, last, excluded)
        for s in starts:
            e_end = s + (end - start) if end else None
            k = key if len(starts) == 1 else f"{key}|{s.date()}"
            if d.get("all_day"):
                # an end at local midnight belongs to the day before
                last_day = (e_end - dt.timedelta(minutes=1)).date() if e_end else None
                e = C.event(src, k, d.get("title"), s.date(), last_day if last_day and last_day > s.date() else None,
                            True, loc, url, desc)
            else:
                e = C.event(src, k, d.get("title"), s, e_end, False, loc, url, desc)
            if e:
                out.append(e)
    return out


def read(src, ctx):
    return parse(C.get_json(data_url(src["url"])), src)
