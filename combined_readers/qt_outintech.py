"""Out in Tech — chapter events, read from outintech.com/events/ and each event's page.

List page (and /events/page/2/ ... while the page links to a next one, 4 pages at
most): one `<div class="single__post">` per event with the date `<h6>11.17.2026</h6>`,
title `<h3>`, a one-line blurb `<p>`, the address `<span class="link--location">` and
the link to the event page. The list gives no clock time.

Event page (opened once, kept for a week in the state file, at most "detail_max" new
pages per run, default 30): `<h4>November 17, 2026 5:30 pm - 7:30 pm</h4>`, the
sign-up link `<a ...>Register</a>` (Eventbrite or events.outintech.com) and
`<small>Venue:</small><p>address</p>`.

The clock time is local to the venue, so it is moved to Eastern by the address's time
zone (combined_readers/zones.py). When the zone cannot be told from the address (a
virtual event, an address with no state or country), or the event page has not been
read yet, the event is all-day and the printed time is quoted in the description.

robots.txt (2026-11-17): /events/ and /event/ are not disallowed. The site's
/wp-json/tribe/ API answers but is empty (events are a custom post type).

Not read: only the "Upcoming" part of the list on outintech.com/events has titles in
<h3>; the "Past Events" part is ignored. Chapter events on the Accelevents portal
(https://www.accelevents.com/o/OutinTech / https://events.outintech.com) are also
scraped from the SSR organizer cards and merged/deduplicated with the WordPress list.


Checked 2026-11-17 against the site: Out in Tech Denver November Monthly Mixer
(Nov 17, 5:30-7:30 pm at 525 Santa Fe Dr., Denver; its Eventbrite page gives
17:30-07:00, the same instant as 7:30 PM Eastern).

Known failure modes: a renamed `single__post` / `link--location` class or a moved
`<h4>` returns nothing or all-day events; an event edited after its page was read
keeps the old time for up to a week.
"""
import datetime as dt
import html
import re
import urllib.parse

import combined_to_ics as C
from combined_readers import qt_common as Q
from combined_readers import zones

MAX_PAGES = 4
DATE_WORDS = re.compile(r"\b" + Q.MONTHS + r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s+20\d{2}", re.I)


def _plain(s):
    return C.clean(re.sub(r"<[^>]+>", " ", s or ""))


def parse_list(body, src):
    """List page -> [{day, title, blurb, loc, url}] in page order."""
    out = []
    for block in re.split(r'<div\b[^>]*class="[^"]*\bsingle__post\b[^"]*"[^>]*>', body)[1:]:
        end = re.search(r'class="link--more"[^>]*>.*?</a>', block, re.S)      # a card ends with "View Event Page"
        block = block[:end.end()] if end else block[:900]                     # (the last card runs on into the footer)
        d = re.search(r"<h6[^>]*>\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*</h6>", block)
        t = re.search(r"<h3[^>]*>(.*?)</h3>", block, re.S)
        a = re.search(r'<a\b[^>]*href="([^"]+)"', block)
        if not (d and t and a):
            continue
        try:
            day = dt.date(int(d.group(3)), int(d.group(1)), int(d.group(2)))
        except ValueError:
            continue
        loc = re.search(r'class="[^"]*\blink--location\b[^"]*"[^>]*>(.*?)</span>', block, re.S)
        blurb = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
        out.append({"day": day, "title": _plain(t.group(1)), "blurb": _plain(blurb.group(1)) if blurb else "",
                    "loc": _plain(loc.group(1)) if loc else "",
                    "url": urllib.parse.urljoin(src["url"], html.unescape(a.group(1)))})
    return out


def next_page(body, n):
    m = re.search(r'href="([^"]*/events/page/%d/?)"' % (n + 1), body)
    return html.unescape(m.group(1)) if m else None


def parse_detail(body):
    """Event page -> {"when": the <h4> line, "rsvp": sign-up link, "venue": address}."""
    when = ""
    for h in re.findall(r"<h4[^>]*>(.*?)</h4>", body, re.S):
        if DATE_WORDS.search(_plain(h)):
            when = _plain(h)
            break
    rsvp = ""
    for href, label in re.findall(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', body, re.S):
        if Q.RSVP_TEXT.search(_plain(label)) and href.startswith("http"):
            rsvp = html.unescape(href)
            break
    v = re.search(r"<small[^>]*>\s*Venue:?\s*</small>\s*<p[^>]*>(.*?)</p>", body, re.S | re.I)
    return {"when": when, "rsvp": rsvp, "venue": _plain(v.group(1)) if v else ""}


def build(item, info, src):
    """One list entry plus (maybe) its event page -> a feed event."""
    loc = Q.place((info or {}).get("venue") or item["loc"])
    start, end, all_day, note = item["day"], None, True, ""
    clock = C.clock_from_text(DATE_WORDS.sub(" ", (info or {}).get("when", "")))
    if clock:
        st = dt.datetime.combine(item["day"], clock[0])
        en = dt.datetime.combine(item["day"], clock[1]) if clock[1] else None
        if en and en <= st:
            en += dt.timedelta(days=1)
        zone = zones.zone_for(loc)
        if zone:
            start, end, all_day = zones.to_ny(st, zone), zones.to_ny(en, zone) if en else None, False
        else:
            note = zones.unplaced(item["day"], st, en)
    desc = "\n\n".join(x for x in (item["blurb"], note) if x)
    return C.event(src, item["url"], item["title"], start, end, all_day, loc, item["url"], desc,
                   rsvp=(info or {}).get("rsvp", ""))


ACCELEVENTS_URL = "https://www.accelevents.com/o/OutinTech"
ACCELEVENTS_DATE_RX = re.compile(
    r"([A-Za-z]{3},\s+[A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s+from\s+"
    r"(\d{1,2}:\d{2}\s*[AP]M)\s+to\s+(\d{1,2}:\d{2}\s*[AP]M)\s*"
    r"\(([A-Z]{2,4})\)"
)


def parse_accelevents(body, src):
    """Accelevents SSR portal HTML -> feed events."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(body, "html.parser")
    events, seen_urls = [], set()
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "/e/" not in href or any(x in href for x in ("sharer", "twitter.com", "mailto:")):
            continue
        event_url = href if href.startswith("http") else f"https://events.outintech.com{href}"
        event_url = event_url.replace("https://www.accelevents.com/e/", "https://events.outintech.com/e/")
        if event_url in seen_urls:
            continue
        card = link.find_parent("div", class_="org-desc") or link.find_parent(["div", "article", "li"]) or link
        card_text = " ".join(card.stripped_strings)
        match = ACCELEVENTS_DATE_RX.search(card_text)
        if not match:
            continue
        date_part, start_str, end_str, tz_abbr = match.groups()
        tz = Q.TZ_MAP.get(tz_abbr, Q.EASTERN)
        dt_start = (
            dt.datetime.strptime(f"{date_part} {start_str}", "%a, %b %d, %Y %I:%M %p")
            .replace(tzinfo=tz)
            .astimezone(Q.EASTERN)
            .replace(tzinfo=None)
        )
        dt_end = (
            dt.datetime.strptime(f"{date_part} {end_str}", "%a, %b %d, %Y %I:%M %p")
            .replace(tzinfo=tz)
            .astimezone(Q.EASTERN)
            .replace(tzinfo=None)
        )
        if dt_end <= dt_start:
            dt_end += dt.timedelta(days=1)
        lines = [line.strip() for line in card.stripped_strings if line.strip()]
        title = next(
            (l for l in lines if "Out in Tech" in l or "#" in l),
            link.get_text(strip=True) or "Out in Tech Event",
        )
        location = "See event page"
        for i, l in enumerate(lines):
            if l == title and i + 1 < len(lines):
                candidate = lines[i + 1]
                if not ACCELEVENTS_DATE_RX.search(candidate) and candidate not in ("Free", "MULTIPLE DATES"):
                    location = candidate
                break
        seen_urls.add(event_url)
        e = C.event(src, event_url, title, dt_start, dt_end, False, Q.place(location), event_url, "", rsvp=event_url)
        if e:
            events.append(e)
    return events


def scrape_out_in_tech_accelevents(src=None) -> list[dict]:
    src = src or {"id": "qt_outintech", "name": "Out in Tech", "url": ACCELEVENTS_URL}
    url = src.get("accelevents_url") or ACCELEVENTS_URL
    if Q.cf_requests is not None:
        C.http._wait(url)
        resp = Q.cf_requests.get(url, headers={"User-Agent": "curl/8.0", "Accept-Language": "en-US,en;q=0.9"}, timeout=20)
        resp.raise_for_status()
        text = resp.text
    else:
        r = C.http.get(url, headers={"User-Agent": "curl/8.0"})
        r.encoding = "utf-8"
        text = r.text
    if "/e/" not in text or "org-desc" not in text:
        r = C.http.get(url, headers={"User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)"})
        r.encoding = "utf-8"
        text = r.text
    return parse_accelevents(text, src)


def _city_key(title):
    m = re.match(r"^out in tech\s+([a-z .'-]+?)(?:\s*[:|\-–—]|\s+\d|\s*$)", title.lower())
    return m.group(1).strip() if m else C.norm_title(title)


def read(src, ctx):
    items, url = [], src["url"]
    for n in range(1, MAX_PAGES + 1):
        try:
            body = C.get_text(url)
        except C.http.BlockedError:
            raise
        except Exception:
            if n == 1:
                raise
            break
        items += parse_list(body, src)
        url = next_page(body, n)
        if not url:
            break
    budget, out, seen = [int(src.get("detail_max", 30))], [], set()
    for it in items:
        if it["url"] in seen or not (ctx["lo"] <= it["day"] <= ctx["hi"]):
            continue
        seen.add(it["url"])
        e = build(it, Q.cached(ctx, it["url"], budget, parse_detail), src)
        if e:
            out.append(e)
    try:
        accel = scrape_out_in_tech_accelevents(src)
    except Exception:
        accel = []
    seen_chapter_time = {(_city_key(e["title"]), e["start"]) for e in out}
    for e in accel:
        if not (ctx["lo"] <= C.day_of(e) <= ctx["hi"]):
            continue
        ck = (_city_key(e["title"]), e["start"])
        if ck in seen_chapter_time or e["url"] in seen:
            continue
        seen.add(e["url"])
        seen_chapter_time.add(ck)
        out.append(e)
    return out
