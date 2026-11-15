"""
Philadelphia Museum of Art (Main Building and Rodin Museum) — events reader.

Why a sitemap: https://www.philamuseum.org/events is drawn in the browser from a hosted
search index that needs the site's API key, which this reader does not use. The server
sends that page without events ("events": null), there is no feed, and no schema.org
data. What is public and allowed by robots.txt:

  1. https://www.philamuseum.org/sitemap-events.xml  (one request per run): every event
     page with the time it last changed,
         <loc>https://www.philamuseum.org/events/exhibition-tour-rodins-hands</loc>
         <lastmod>2026-11-04T15:04:30Z</lastmod>
  2. the event pages themselves (Next.js). Each carries its event record in the page
     data (`self.__next_f.push(...)`): title, place and every occurrence in UTC,
         {"_id":"...","_type":"event", ... "occurrences":[{"start":"2026-11-15T18:00:00.000Z",
          "end":"2026-11-15T19:00:00.000Z","status":"active"}, ...], "place":{...}, "title":"..."}
     which the page shows a visitor as "Sunday, November 15, 2026 / 1:00 pm - 2:00 pm".

Paging: at most 12 event pages per run, most recently changed first. A page is read again
only when its sitemap `lastmod` changes, or after 45 days. There were 194 event pages on
2026-11-15 (each about 350 KB), so a new installation needs about 17 runs (8 to 9 days at
two runs a day) to have seen them all; recently edited events, which are the upcoming
ones, come first. After that a run opens only the few pages edited since the last one.
ctx["detail"][url] holds, per page: "fetched" (last run that confirmed it, so the script
keeps it), "read", "lastmod", and one packed event plus "occ", the list of
[start, end] pairs for the next 180 days.

Checked on 2026-11-15 against what the event pages show a visitor ("When" / "Where"):
Exhibition Tour: Rodin's Hands (Sunday, November 15, 2026, 1:00 pm - 2:00 pm, Rodin
Museum, Main Gallery; 18:00Z in the data), Friday Night: Holiday Jazz & Artist Market
(Fri, Dec 11, 2026 5:00 pm to 8:30 pm, Main Building; 22:00Z) and Alter Ego: Family
Festival (Sunday, December 6, 2026, 10:00 am - 3:00 pm, Main Building; 15:00Z). A first
run read 12 pages and gave 193 occurrences in the next 120 days, most of them daily tours.

Known failure modes:
  * Coverage is partial until every page has been read once (see above), and an event
    whose page changed is up to one run behind when more than 12 pages changed at once.
  * It relies on the sitemap's `lastmod` moving when occurrences are edited; the 45-day
    re-read is the safety net if it does not.
  * Cancelled occurrences (`"status":"cancelled"`) and events titled "Cancelled: ..." are
    left out. Sold-out is not marked.
  * Daily tours have hundreds of occurrences; the feed folds a daily run into one entry.
  * The place is the page's "Where" (building, room). Street addresses are added for the
    two buildings only: the Main Building's is in every page footer; the Rodin Museum's
    (2151 Benjamin Franklin Parkway) is not on these pages and was added by hand.
  * If the site stops embedding the event record, pages yield nothing (no error).
"""
import datetime as dt
import html
import json
import re
import urllib.parse
from zoneinfo import ZoneInfo

import combined_to_ics as C

MAX_NEW_PAGES = 12
MAX_AGE_DAYS = 45         # re-read a page this old even when the sitemap says it did not change
KEEP_AHEAD_DAYS = 180     # occurrences kept in the cache (the feed looks 120 days ahead)
NY = ZoneInfo("America/New_York")
ADDRESS = {"main building": "Philadelphia Museum of Art{room}, 2600 Benjamin Franklin Parkway, Philadelphia, PA 19130",
           "rodin museum": "Rodin Museum{room}, 2151 Benjamin Franklin Parkway, Philadelphia, PA 19130"}
URL_RX = re.compile(r"<url>\s*<loc>\s*([^<\s]+)\s*</loc>(.*?)</url>", re.S)
CHUNK_RX = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)\s*</script>', re.S)
DOC_RX = re.compile(r'\{"_id":"[^"]*","_type":"event"')


def parse_sitemap(body):
    """sitemap-events.xml -> [(event page url, lastmod)], most recently changed first."""
    out = []
    for m in URL_RX.finditer(body):
        url = html.unescape(m.group(1))
        if not re.match(r"^https://www\.philamuseum\.org/events/[^/?#]+/?$", url):
            continue
        mod = re.search(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", m.group(2))
        out.append((url, mod.group(1) if mod else ""))
    return sorted(out, key=lambda p: p[1], reverse=True)


def event_record(body):
    """The page's own event record (a dict), or None."""
    parts = []
    for c in CHUNK_RX.findall(body):
        try:
            parts.append(json.loads('"' + c + '"'))
        except ValueError:
            continue
    data, dec = "".join(parts), json.JSONDecoder()
    for m in DOC_RX.finditer(data):
        try:
            doc, _ = dec.raw_decode(data, m.start())
        except ValueError:
            continue
        if isinstance(doc, dict) and isinstance(doc.get("occurrences"), list):
            return doc
    return None


def _place(doc):
    p = doc.get("place") if isinstance(doc.get("place"), dict) else {}
    if p.get("_type") == "sublocation":
        building, room = C.clean((p.get("location") or {}).get("title")), C.clean(p.get("title"))
    elif p:
        building, room = C.clean(p.get("title")), ""
    else:
        building, room = "", C.clean(doc.get("legacyRoom"))
    if room.lower() == building.lower():
        room = ""
    known = ADDRESS.get(building.lower())
    if known:
        inside = ", ".join(x for x in (building if building.lower() == "main building" else "", room) if x)
        return known.format(room=f" ({inside})" if inside else "")
    return ", ".join(x for x in (building, room) if x)


def _words(blocks):
    """Sanity 'portable text' -> plain text."""
    if not isinstance(blocks, list):
        return ""
    paras = []
    for b in blocks:
        kids = b.get("children") if isinstance(b, dict) else None
        if isinstance(kids, list):
            paras.append("".join(str(k.get("text") or "") for k in kids if isinstance(k, dict)))
    return "\n\n".join(x.strip() for x in paras if x.strip())


def _link(url, start, end):
    """The site's own link to one occurrence: ?start=<UTC>&end=<UTC>."""
    def z(d):
        return d.replace(tzinfo=NY).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    q = {"start": z(start)}
    if end:
        q["end"] = z(end)
    return url + "?" + urllib.parse.urlencode(q, safe=":")


def parse(body, src, url=None):
    """One event page -> an event per active occurrence (past ones included)."""
    doc = event_record(body)
    if not doc or not doc.get("title") or re.match(r"\s*cancel+ed\b", str(doc["title"]), re.I):
        return []
    if not url:
        m = re.search(r'<link[^>]*rel="canonical"[^>]*href="([^"]+)"', body)
        url = html.unescape(m.group(1)) if m else (src.get("page") or src["url"])
    loc, notes = _place(doc), []
    tag = doc.get("tag") if isinstance(doc.get("tag"), dict) else {}
    if tag.get("title"):
        notes.append(C.clean(tag["title"]))
    notes.append(_words(doc.get("description")))
    desc = "\n\n".join(x for x in notes if x)
    out, seen = [], set()
    for o in doc["occurrences"]:
        if not isinstance(o, dict) or re.search(r"cancel|postpon", str(o.get("status") or ""), re.I):
            continue
        st = C.parse_iso(o.get("start"))
        if not st or st[1] or st[0] in seen:
            continue
        seen.add(st[0])
        en = C.parse_iso(o.get("end")) if o.get("end") else None
        end = en[0] if en and not en[1] and en[0] > st[0] else None
        e = C.event(src, f"{url}|{o.get('start')}", doc["title"], st[0], end, False, loc, _link(url, st[0], end), desc)
        if e:
            out.append(e)
    return out


def _store(events, lastmod, today):
    first = events[0] if events else None
    return {"fetched": today.isoformat(), "read": today.isoformat(), "lastmod": lastmod,
            "events": [C.pack(first)] if first else [],
            "occ": [[e["start"].isoformat(), e["end"].isoformat() if e.get("end") else ""] for e in events]}


def _restore(src, url, c):
    if not c.get("events"):
        return []
    first, out = c["events"][0], []
    for start, end in c.get("occ") or []:
        st = dt.datetime.fromisoformat(start)
        en = dt.datetime.fromisoformat(end) if end else None
        e = C.event(src, f"{url}|{start}", first["title"], st, en, False, first.get("loc", ""), _link(url, st, en),
                    first.get("desc", ""))
        if e:
            out.append(e)
    return out


def read(src, ctx):
    cache, today, opened, out = ctx["detail"], ctx["today"], 0, []
    keep_to = today + dt.timedelta(days=KEEP_AHEAD_DAYS)
    for url, lastmod in parse_sitemap(C.get_text(src["url"])):
        c = cache.get(url)
        current = bool(c) and c.get("lastmod") == lastmod and "read" in c \
            and (today - dt.date.fromisoformat(c["read"])).days < MAX_AGE_DAYS
        if not current and opened < MAX_NEW_PAGES:
            opened += 1
            try:
                events = parse(C.get_text(url), src, url)
            except Exception as ex:
                if type(ex).__name__ == "BlockedError":       # a 403/406 stops the source; never worked around
                    raise
                events = None
            if events is not None:
                c = cache[url] = _store([e for e in events if ctx["lo"] <= e["start"].date() <= keep_to], lastmod, today)
        if c:                                                 # read now, confirmed by the sitemap, or waiting its turn
            c["fetched"] = today.isoformat()
            out += _restore(src, url, c)
    return out
