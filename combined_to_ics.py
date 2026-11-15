#!/usr/bin/env python3
"""
combined_to_ics.py — one .ics feed merged from many Philadelphia event sources.

The sources (museums, parks, venues, galleries, bars, neighborhood groups) are listed in
combined_sources.json. Each entry names a site and how its events can be read:

    ics          any public iCalendar feed (Google Calendar, Tockify, Luma)
    tribe        The Events Calendar REST API (/wp-json/tribe/events/v1/events)
    squarespace  a Squarespace events-list page (its HTML; robots.txt rules out ?format=json)
    spothopper   SpotHopper's public events JSON (restaurant and bar sites)
    jsonld       schema.org Event data embedded in the page
    wix          the Wix Events data embedded in the page
    html         a plain HTML events page: the script follows the page's links to
                 individual event pages and reads schema.org Event data there
    custom       a site with its own reader module in combined_readers/
    text         a plain HTML events page with no structured data anywhere: each
                 small block holding one written date and a heading or link is
                 read as an event (checked by hand before a source is set to this)

Usage:
    python3 combined_to_ics.py --out docs/combined.ics --state docs/combined_state.json
    python3 combined_to_ics.py --only jetwinebar,tmoms --force   # test a few sources
    python3 combined_to_ics.py --list                            # show the source list

Rules it follows (same as the other feeds here):
  * Never invents a time. A source that gives only a date becomes an all-day event;
    an html source with no structured data on its event pages produces nothing.
  * Polite: one listing request per source per run, 1.5 s between requests to a
    domain (common/http.py), event pages cached in the state file for a week, and
    the whole run happens at most once every --min-hours (default 11), except that
    the morning run (5-10 AM Eastern) always rebuilds.
  * A site that answers 403/406 is reported and skipped, never worked around.
  * One broken source never stops the others; its events return when it answers again.

Needs `pip install requests`. Shares its iCalendar helpers with pgc_to_ics.py and
tribe_to_ics.py (keep the files together).
"""
import argparse
import collections
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

from common import http
from common import normalize
from pgc_to_ics import VTIMEZONE, TZID, esc, fold, collapse_span, clock_from_text
import tribe_to_ics as tribe

NY = ZoneInfo(TZID)
UA = "Mozilla/5.0 (combined_to_ics; personal calendar subscription; +https://github.com/sh3ll3hs/philly-calendars)"
DEFAULT_HOURS = 2
MAX_DESC = 350
DETAIL_PER_SOURCE = 12     # event pages opened per html source per run
DETAIL_TTL_DAYS = 7
DAILY_MIN = 10
HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- small helpers
def get_text(url):
    return http.get(url, headers={"User-Agent": UA}).text


def get_json(url):
    return http.get(url, headers={"User-Agent": UA, "Accept": "application/json"}).json()


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(str(s or ""))).strip(" ,")


def text(s):
    s = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", str(s or ""), flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    s = re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t\xa0]+", " ", s)).strip()
    return s if len(s) <= MAX_DESC else s[:MAX_DESC].rsplit(" ", 1)[0] + "…"


def local(d):
    """Aware datetime -> naive America/New_York wall time."""
    return d.astimezone(NY).replace(tzinfo=None) if d.tzinfo else d


def parse_iso(s, utc_wall=False):
    """ISO-8601 from structured data -> (datetime or date, all_day). None if unreadable.
    utc_wall: for a site whose data applies its UTC offset twice (the true local
    time is the instant's UTC clock reading), keep the UTC wall time."""
    s = str(s or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        return dt.date(*map(int, m.groups())), True
    s2 = re.sub(r"Z$", "+00:00", s)
    s2 = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", s2)          # +0500 -> +05:00
    s2 = re.sub(r"\.\d+", "", s2)
    try:
        d = dt.datetime.fromisoformat(s2)
    except ValueError:
        return None
    if utc_wall and d.tzinfo:
        return d.astimezone(dt.timezone.utc).replace(tzinfo=None), False
    return local(d), False


def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def address(loc):
    """schema.org Place / PostalAddress (or a plain string) -> one line."""
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if isinstance(loc, str):
        return clean(loc)
    if not isinstance(loc, dict):
        return ""
    name = clean(loc.get("name"))
    a = loc.get("address")
    if isinstance(a, dict):
        tail = " ".join(x for x in (clean(a.get("addressRegion")), clean(a.get("postalCode"))) if x)
        a = ", ".join(x for x in (clean(a.get("streetAddress")), clean(a.get("addressLocality")), tail) if x)
    a = clean(a)
    parts, seen = [], []
    for piece in [p.strip() for chunk in (name, a) for p in chunk.split(",")]:
        key = tribe._norm(piece)
        if key and not any(key == s or key in s for s in seen):
            seen.append(key)
            parts.append(piece)
    return ", ".join(parts)


def event(src, key, title, start, end=None, all_day=False, loc="", url="", desc=""):
    title = clean(title)
    if not title or start is None:
        return None
    if isinstance(start, dt.datetime) and isinstance(end, dt.datetime) and start.hour <= 1 and start.minute == 0 \
            and end - start >= dt.timedelta(hours=20) and (end.hour, end.minute) in ((23, 59), (0, 0), (1, 0)):
        # "midnight to 11:59 PM" is how sites enter an all-day item (closures, exhibitions)
        start, end, all_day = start.date(), (end - dt.timedelta(minutes=2)).date(), True
    parts = []
    for piece in clean(loc).split(", "):          # "..., Philadelphia, PA, 19103, Philadelphia" -> drop the repeat
        if piece and piece.lower() not in [x.lower() for x in parts]:
            parts.append(piece)
    return {"src": src["id"], "key": str(key), "title": title, "start": start, "end": end, "all_day": all_day,
            "loc": ", ".join(parts) or src.get("venue", ""), "url": tribe.good_url(url) or src.get("page") or src["url"],
            "desc": text(desc), "source": src["name"]}


# ---------------------------------------------------------------- readers
def jsonld_events(src, page, page_url):
    out = []
    for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, re.S | re.I):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
        except ValueError:
            try:
                data = json.loads(html.unescape(raw))
            except ValueError:
                continue
        for o in walk(data):
            t = o.get("@type", "")
            types = t if isinstance(t, list) else [t]
            if not any(isinstance(x, str) and x.endswith("Event") for x in types) or not o.get("startDate"):
                continue
            wall = src.get("tz") == "utc_wall"
            st = parse_iso(o.get("startDate"), wall)
            if not st:
                continue
            en = parse_iso(o.get("endDate"), wall) if o.get("endDate") else None
            url = o.get("url") if isinstance(o.get("url"), str) else ""
            url = urllib.parse.urljoin(page_url, url) if url else page_url
            e = event(src, f"{url}|{o.get('startDate')}", o.get("name"), st[0], en[0] if en else None, st[1],
                      address(o.get("location")), url, o.get("description"))
            if e:
                out.append(e)
    return out


def read_jsonld(src, ctx):
    return jsonld_events(src, get_text(src["url"]), src["url"])


def read_tribe(src, ctx):
    base = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(src["url"]))
    events, page = [], 1
    while page <= 6:
        q = {"per_page": 50, "page": page, "start_date": ctx["lo"].isoformat(), "end_date": ctx["hi"].isoformat()}
        q.update(src.get("params") or {})
        try:
            d = get_json(f"{base}/wp-json/tribe/events/v1/events?{urllib.parse.urlencode(q)}")
        except Exception:
            if page > 1:
                break
            raise
        events += d.get("events", [])
        if page >= int(d.get("total_pages") or 1):
            break
        page += 1
    out = []
    for e in events:
        st, en = tribe.parse(e["start_date"]), tribe.parse(e["end_date"])
        all_day = bool(e.get("all_day"))
        out.append(event(src, e["id"], e.get("title"), st.date() if all_day else st, en.date() if all_day else en, all_day,
                         tribe.location(e.get("venue")), tribe.good_url(e.get("website")) or e.get("url"), e.get("description")))
    return [e for e in out if e]


def read_squarespace(src, ctx):
    """A Squarespace events-list page, read from its HTML. (The tidier `?format=json`
    view is ruled out by the robots.txt every Squarespace site ships with.)"""
    from combined_readers import squarespace_list
    return squarespace_list.parse(get_text(src["url"]), src)


def read_spothopper(src, ctx):
    d = get_json(src["url"])
    out = []
    for it in (d.get("events") if isinstance(d, dict) else d) or []:
        if str(it.get("show_on_website")) == "False" or str(it.get("is_template")) == "True":
            continue
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(it.get("event_date") or ""))
        if not m:
            continue
        day = dt.date(*map(int, m.groups()))
        t = re.match(r"^(\d{1,2}):(\d{2})$", str(it.get("start_time") or ""))
        if t and str(it.get("all_day")) != "True":
            st = dt.datetime.combine(day, dt.time(int(t.group(1)), int(t.group(2))))
            mins = str(it.get("duration_minutes") or "")
            en = st + dt.timedelta(minutes=int(mins)) if mins.isdigit() and int(mins) > 0 else None
            e = event(src, it.get("id"), it.get("name"), st, en, False, "", src.get("page") or "", it.get("text"))
        else:
            e = event(src, it.get("id"), it.get("name"), day, None, True, "", src.get("page") or "", it.get("text"))
        if e:
            out.append(e)
    return out


def read_wix(src, ctx):
    page = get_text(src["url"])
    m = re.search(r'<script[^>]+id="wix-warmup-data"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        return []
    root = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(src["url"]))
    out, seen = [], set()
    for o in walk(json.loads(m.group(1))):
        sch = o.get("scheduling")
        if not isinstance(sch, dict) or not isinstance(o.get("title"), str) or o.get("id") in seen:
            continue
        cfg = sch.get("config") or {}
        if cfg.get("scheduleTbd") or not cfg.get("startDate"):
            continue
        seen.add(o.get("id"))
        st, en = parse_iso(cfg["startDate"]), parse_iso(cfg.get("endDate")) if cfg.get("endDate") else None
        if not st:
            continue
        L = o.get("location") or {}
        loc = address({"name": L.get("name"), "address": re.sub(r",\s*USA$", "", str(L.get("address") or ""))})
        url = f"{root}/event-details/{o['slug']}" if o.get("slug") else src["url"]
        e = event(src, o.get("id"), o["title"], st[0], en[0] if en else None, False, loc, url, o.get("description"))
        if e:
            out.append(e)
    return out


DETAIL_RX = re.compile(r"/(events?|shows?|calendar|classes|class|workshops?|programs?|exhibitions?|performances?|"
                       r"happenings|whats-on|screenings?|concerts?|e|event-details)/[^/?#]+", re.I)
SKIP_RX = re.compile(r"/(category|tag|page|feed|list|month|week|day|today|photo|map|venue|organizer|series)/|"
                     r"\.(ics|jpg|jpeg|png|pdf|xml)$|[?&](ical|outlook-ical|format)=", re.I)


def detail_links(page, page_url):
    host = urllib.parse.urlsplit(page_url).netloc.removeprefix("www.")
    base_path = urllib.parse.urlsplit(page_url).path.rstrip("/")
    out = []
    for href in re.findall(r"""<a\b[^>]*?href=["']([^"'#]+)["']""", page, re.I):
        u = urllib.parse.urljoin(page_url, html.unescape(href)).split("#")[0]
        p = urllib.parse.urlsplit(u)
        if p.scheme not in ("http", "https") or p.netloc.removeprefix("www.") != host:
            continue
        path = p.path.rstrip("/")
        if path == base_path or SKIP_RX.search(u):
            continue
        under = base_path and path.startswith(base_path + "/") and path.count("/") <= base_path.count("/") + 4
        if (under or DETAIL_RX.search(path)) and u not in out:
            out.append(u)
    return out


def read_html(src, ctx):
    page = get_text(src["url"])
    found = jsonld_events(src, page, src["url"])
    if found:
        return found
    cache, today, opened, out = ctx["detail"], ctx["today"].isoformat(), 0, []
    for u in detail_links(page, src["url"])[:40]:
        c = cache.get(u)
        if c and (dt.date.fromisoformat(today) - dt.date.fromisoformat(c["fetched"])).days < DETAIL_TTL_DAYS:
            evs = c["events"]
        elif opened < DETAIL_PER_SOURCE:
            opened += 1
            try:
                evs = [pack(e) for e in jsonld_events(src, get_text(u), u)][:6]
            except http.BlockedError:
                raise
            except Exception:
                continue
            cache[u] = {"fetched": today, "events": evs}
        else:
            continue
        out += [unpack(e) for e in evs]
    return out


MONTH_RX = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
DATE_RX = re.compile(r"\b" + MONTH_RX + r"\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s+(20\d{2}))?", re.I)
NUMDATE_RX = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2}|\d{2})\b")
STOP_TITLES = re.compile(r"^(read more|learn more|more info(rmation)?|details?|event details|view event|buy tickets?|tickets?|"
                         r"get tickets|rsvp|register( now| here)?|sign up|book now|see more|view all|click here|info|"
                         r"add to calendar|google calendar|ics|share|upcoming events?|events?|calendar|members?|featured event|free)$", re.I)


def _dates_in(txt, today):
    out = []
    for m in DATE_RX.finditer(txt):
        mon, day = normalize.month_num(m.group(1)), int(m.group(2))
        try:
            d = dt.date(int(m.group(3)), mon, day) if m.group(3) else normalize.infer_year(mon, day, today)
        except (ValueError, TypeError):
            continue
        if d:
            out.append((m.start(), d))
    for m in NUMDATE_RX.finditer(txt):
        try:
            y = int(m.group(3))
            out.append((m.start(), dt.date(y if y > 100 else 2000 + y, int(m.group(1)), int(m.group(2)))))
        except ValueError:
            continue
    return sorted(out)


def text_events(src, page, page_url, today, hi):
    """Last resort for a plain HTML page: an event is a small block of the page
    that holds one written date and a heading or link to use as the title. A time
    is used only if the block states one; otherwise the event is all-day."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(page, "html.parser")
    for t in soup(["script", "style", "noscript", "nav", "footer", "header", "form", "svg", "select", "iframe"]):
        t.decompose()
    out, seen = [], set()
    for node in soup.find_all(string=DATE_RX):
        el = node.parent
        block = None
        for _ in range(6):
            if el is None or el.name in ("body", "html", "[document]"):
                break
            txt = " ".join(el.get_text(" ", strip=True).split())
            if len(txt) > 700:
                break
            distinct = {d for _, d in _dates_in(txt, today)}
            if len(distinct) > 2:
                break
            if el.find(["h1", "h2", "h3", "h4", "h5", "h6", "a", "strong", "b"]) and len(txt) > len(str(node).strip()) + 3:
                block = el
                if el.find(["h1", "h2", "h3", "h4", "h5", "h6", "a"]):
                    break
            el = el.parent
        if block is None:
            continue
        txt = " ".join(block.get_text(" ", strip=True).split())
        dates = _dates_in(txt, today)
        if not dates:
            continue
        day = dates[0][1]
        end_day = dates[-1][1] if dates[-1][1] > day else None
        if not (today <= (end_day or day) and day <= hi):
            continue
        title, link = "", ""
        for tag in block.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "a", "strong", "b"]):
            cand = " ".join(tag.get_text(" ", strip=True).split())
            bare = DATE_RX.sub("", cand)
            bare = re.sub(r"\b(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)[a-z]*\.?,?|\d{1,2}(:\d{2})?\s*[ap]\.?m\.?|[@|,:;\-–—•·]", " ", bare, flags=re.I)
            bare = " ".join(bare.split())
            if len(re.sub(r"[^A-Za-z]", "", bare)) < 3 or STOP_TITLES.match(bare) or len(bare) > 140:
                continue
            title = bare
            a = tag if tag.name == "a" else tag.find("a") or tag.find_parent("a")
            link = a.get("href", "") if a else ""
            break
        if not title:
            continue
        if not link:
            a = block.find("a", href=True)
            link = a["href"] if a else ""
        url = urllib.parse.urljoin(page_url, link) if link and not link.startswith(("mailto:", "tel:", "javascript:")) else page_url
        clock = clock_from_text(DATE_RX.sub(" ", txt))
        key = (title.lower(), day)
        if key in seen:
            continue
        seen.add(key)
        note = "Read from the events page text; check the page for details."
        if clock:
            st = dt.datetime.combine(day, clock[0])
            en = dt.datetime.combine(day, clock[1]) if clock[1] else None
            if en and en <= st:
                en += dt.timedelta(days=1)
            e = event(src, f"{title}|{day}", title, st, en, False, "", url, note)
        else:
            e = event(src, f"{title}|{day}", title, day, end_day, True, "", url, note)
        if e:
            out.append(e)
        if len(out) >= 60:
            break
    return out


def read_text(src, ctx):
    page = get_text(src["url"])
    return jsonld_events(src, page, src["url"]) or text_events(src, page, src["url"], ctx["today"], ctx["hi"])


READERS = {"text": read_text, "tribe": read_tribe, "squarespace": read_squarespace, "spothopper": read_spothopper,
           "jsonld": read_jsonld, "wix": read_wix, "html": read_html}


# ---------------------------------------------------------------- ICS pass-through
def unfold(s):
    return re.sub(r"\r?\n[ \t]", "", s.replace("\r\n", "\n"))


def read_ics(src, ctx):
    """Keep each VEVENT as published (so repeating events keep their rule); add a
    source-specific UID, the source name, and a fallback location."""
    body = unfold(get_text(src["url"]))
    out = []
    for b in re.findall(r"^BEGIN:VEVENT\n(.*?)^END:VEVENT", body, re.S | re.M):
        if re.search(r"^STATUS:CANCELLED", b, re.M):
            continue
        b = re.sub(r"^BEGIN:VALARM\n.*?^END:VALARM\n", "", b, flags=re.S | re.M)   # reminders are the subscriber's choice
        m = re.search(r"^DTSTART[^:\n]*:(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})(Z)?)?", b, re.M)
        if not m:
            continue
        day = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        rrule = re.search(r"^RRULE:(.*)$", b, re.M)
        if rrule:
            until = re.search(r"UNTIL=(\d{4})(\d{2})(\d{2})", rrule.group(1))
            if day > ctx["hi"] or (until and dt.date(*map(int, until.groups())) < ctx["lo"]):
                continue
        elif not (ctx["lo"] <= day <= ctx["hi"]):
            continue
        if m.group(4):
            st = dt.datetime(day.year, day.month, day.day, int(m.group(4)), int(m.group(5)), int(m.group(6)))
            if m.group(7):
                st = local(st.replace(tzinfo=dt.timezone.utc))
        else:
            st = day
        uid = re.search(r"^UID:(.*)$", b, re.M)
        title = re.search(r"^SUMMARY[^:\n]*:(.*)$", b, re.M)
        lines = [l for l in b.strip("\n").split("\n")
                 if not l.startswith(("UID", "DTSTAMP", "SEQUENCE", "CREATED", "LAST-MODIFIED", "CATEGORIES", "ATTENDEE",
                                      "ORGANIZER", "X-", "BEGIN:VALARM", "END:VALARM", "TRIGGER", "ACTION", "STATUS",
                                      "TRANSP", "CLASS"))]
        lines = [l[:MAX_DESC + 12].rstrip("\\") + "…" if l.startswith("DESCRIPTION") and len(l) > MAX_DESC + 12 else l for l in lines]
        out.append({"src": src["id"], "key": uid.group(1) if uid else b[:80], "raw": lines,
                    "title": clean((title.group(1) if title else "").replace("\\,", ",").replace("\\;", ";")),
                    "start": st, "all_day": not m.group(4), "source": src["name"], "loc": src.get("venue", ""),
                    "rrule": bool(rrule)})
    return out


READERS["ics"] = read_ics


def read_custom(src, ctx):
    """A site that needs its own reader: combined_readers/<reader>.py with read(src, ctx)."""
    import importlib
    return importlib.import_module(f"combined_readers.{src['reader']}").read(src, ctx)


READERS["custom"] = read_custom


# ---------------------------------------------------------------- state (JSON-safe events)
def pack(e):
    d = dict(e)
    for k in ("start", "end"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    return d


def unpack(d):
    e = dict(d)
    for k in ("start", "end"):
        v = e.get(k)
        if isinstance(v, str):
            e[k] = dt.datetime.fromisoformat(v) if "T" in v else dt.date.fromisoformat(v)
    return e


def day_of(e):
    return e["start"].date() if isinstance(e["start"], dt.datetime) else e["start"]


# ---------------------------------------------------------------- merge + write
def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def tidy(events, lo, hi):
    """Window, de-duplicate across sources, and fold nightly runs into one entry."""
    keep, seen = [], {}
    for e in events:
        if not e.get("rrule") and not (lo <= day_of(e) <= hi):
            continue
        k = (norm_title(e["title"]), e["start"].isoformat())
        if k in seen:
            first = seen[k]
            if not first.get("loc") and e.get("loc"):
                first["loc"] = e["loc"]
            continue
        seen[k] = e
        keep.append(e)
    by = collections.defaultdict(list)
    for e in keep:
        if "raw" not in e:
            by[(e["src"], norm_title(e["title"]))].append(e)
    drop = set()
    for series in by.values():
        if len(series) < DAILY_MIN:
            continue
        series.sort(key=lambda e: e["start"].isoformat())
        days = sorted({day_of(e) for e in series})
        gaps = sorted((b - a).days for a, b in zip(days, days[1:]))
        if gaps and gaps[len(gaps) // 2] <= 2:
            series[0]["title"] += f" (daily through {days[-1]:%b %-d})"
            drop.update(id(e) for e in series[1:])
    return sorted((e for e in keep if id(e) not in drop), key=lambda e: (day_of(e), e["start"].isoformat(), e["title"]))


def build_ics(events, calname="Philly combined events"):
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//combined_to_ics//Philly combined events//EN",
           "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{calname}", f"X-WR-TIMEZONE:{TZID}",
           "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]
    out += VTIMEZONE.split("\n")
    for e in events:
        uid = hashlib.sha1(f"{e['src']}-{e['key']}".encode()).hexdigest() + "@combined.philly-calendars"
        out += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{now}"]
        if "raw" in e:
            lines = list(e["raw"])
            if e.get("loc") and not any(l.startswith("LOCATION") and len(l) > 10 for l in lines):
                lines = [l for l in lines if not l.startswith("LOCATION")] + [f"LOCATION:{esc(e['loc'])}"]
            tag = f"Source: {esc(e['source'])}"
            if any(l.startswith("DESCRIPTION") for l in lines):
                lines = [l + "\\n\\n" + tag if l.startswith("DESCRIPTION") else l for l in lines]
            else:
                lines.append("DESCRIPTION:" + tag)
            out += lines + [f"CATEGORIES:{esc(e['source'])}", "END:VEVENT"]
            continue
        title, st, en = e["title"], e["start"], e.get("end")
        if e["all_day"]:
            s = day_of(e)
            last = (en.date() if isinstance(en, dt.datetime) else en) if en else s
            if last and last > s:
                title += f" (through {last:%b %-d})"
            out += [f"DTSTART;VALUE=DATE:{s:%Y%m%d}", f"DTEND;VALUE=DATE:{s + dt.timedelta(days=1):%Y%m%d}"]
        else:
            if not isinstance(en, dt.datetime) or en <= st:
                en = st + dt.timedelta(hours=DEFAULT_HOURS)
            st, en, through = collapse_span(st, en, default_hours=DEFAULT_HOURS)
            if through:
                title += f" (through {through:%b %-d})"
            out += [f"DTSTART;TZID={TZID}:{st:%Y%m%dT%H%M%S}", f"DTEND;TZID={TZID}:{en:%Y%m%dT%H%M%S}"]
        out.append(f"SUMMARY:{esc(title)}")
        if e.get("loc"):
            out.append(f"LOCATION:{esc(e['loc'])}")
        desc = "\n\n".join(x for x in (e.get("desc"), f"Source: {e['source']}\nEvent page: {e['url']}") if x)
        out += [f"DESCRIPTION:{esc(desc)}", f"URL:{e['url']}", f"CATEGORIES:{esc(e['source'])}", "END:VEVENT"]
    out.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in out) + "\r\n"


def should_skip(age_hours, local_hour, min_hours, morning=(5, 10)):
    """Skip a run that comes too soon after the last one, except that the first run
    of the morning (Eastern time) always rebuilds, so the feed is fresh every day
    however the earlier runs fell."""
    if morning[0] <= local_hour < morning[1] and age_hours >= 3:
        return False
    return age_hours < min_hours


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", default=os.path.join(HERE, "combined_sources.json"))
    ap.add_argument("--out", default="combined.ics")
    ap.add_argument("--state", default="combined_state.json")
    ap.add_argument("--past-days", type=int, default=3)
    ap.add_argument("--days-ahead", type=int, default=120)
    ap.add_argument("--min-hours", type=float, default=11,
                    help="skip the run if the last one was more recent (the morning run, 5-10 AM Eastern, always rebuilds)")
    ap.add_argument("--only", default="", help="comma-separated source ids")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)

    with open(a.sources) as f:
        sources = [s for s in json.load(f) if not s.get("off")]
    if a.list:
        for s in sources:
            print(f"{s['id']:<28} {s['method']:<12} {s['url']}")
        return 0
    only = {x for x in a.only.split(",") if x}
    state = {"last_run": "", "detail": {}, "sources": {}}
    if os.path.exists(a.state):
        with open(a.state) as f:
            state.update(json.load(f))
    now = dt.datetime.now(dt.timezone.utc)
    if state["last_run"] and not (a.force or only):
        age = (now - dt.datetime.fromisoformat(state["last_run"])).total_seconds() / 3600
        if should_skip(age, now.astimezone(NY).hour, a.min_hours) and os.path.exists(a.out):
            print(f"combined: last run {age:.1f} h ago (< {a.min_hours:g} h); skipping")
            return 0

    today = now.astimezone(NY).date()
    lo, hi = today - dt.timedelta(days=a.past_days), today + dt.timedelta(days=a.days_ahead)
    ctx = {"lo": lo, "hi": hi, "today": today, "detail": state["detail"]}
    events, report = [], collections.Counter()

    def run(s):
        try:
            got = [e for e in READERS[s["method"]](s, ctx) if e]
            if s.get("skip"):                 # e.g. "CLOSED" / "PRIVATE EVENT" housekeeping entries
                got = [e for e in got if not re.search(s["skip"], e["title"], re.I)]
            return s, [e for e in got if e.get("rrule") or lo <= day_of(e) <= hi], ""
        except Exception as ex:
            kind = "blocked" if isinstance(ex, http.BlockedError) else "error"
            return s, [], f"{kind}: {type(ex).__name__}: {str(ex)[:120]}"

    todo = [s for s in sources if not only or s["id"] in only]
    with ThreadPoolExecutor(max_workers=12) as pool:      # different sites in parallel; each site still gets 1.5 s gaps
        for s, got, err in pool.map(run, todo):
            state["sources"][s["id"]] = {"events": len(got), "checked": today.isoformat(), "error": err}
            report[err.split(":")[0] if err else ("ok" if got else "empty")] += 1
            events += got
            print(f"  {s['id']:<28} {s['method']:<12} {len(got):>4}  {err}")

    final = tidy(events, lo, hi)
    if not final:
        print("combined: no events from any source; keeping the existing feed", file=sys.stderr)
        return 1
    cutoff = (today - dt.timedelta(days=DETAIL_TTL_DAYS * 2)).isoformat()
    state["detail"] = {u: c for u, c in state["detail"].items() if c["fetched"] >= cutoff}
    if not only:
        state["last_run"] = now.isoformat()
    for path in (a.out, a.state):
        if os.path.dirname(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(a.out, "w", newline="") as f:
        f.write(build_ics(final))
    with open(a.state, "w") as f:
        json.dump(state, f, indent=0, sort_keys=True)
    print(f"combined: {len(sources)} sources ({dict(report)}); {len(events)} events read, "
          f"{len(final)} written to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
