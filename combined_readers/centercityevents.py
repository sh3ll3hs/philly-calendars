"""
CenterCity.Events (a Philadelphia meetup community: tree lightings, hikes, dinners,
weekly pickleball and tennis) — reader for the site's RSS feed.

Source: https://centercity.events/rss.xml  (one request per run, about 105 KB, 25 items).
It is the "RSS" link in the site's footer. The site itself is a JavaScript app: every
page answers the same empty shell without a browser, and its data comes from /api/...,
which robots.txt disallows ("Disallow: /api/", including the app's own
webcal://centercity.events/api/events calendar link). /rss.xml is not under /api/ and
robots.txt allows it, so this reader uses the RSS feed and nothing else.

Each item has <title>, <link> (https://centercity.events/events/<id>), a long
<description> and <pubDate>, and the pubDate is the event's start as Philadelphia wall
time with no offset ("2026-11-19T17:15:00"), not a publication date: items are dated up
to 2027, and the descriptions state the same times.

Checked on 2026-11-15 against the event text in the feed (the event pages cannot be read
without a browser):
  Manayunk Christmas Tree Lighting Ceremony | Canal View Park   pubDate 2026-11-19T17:15
      "We meet at 5:15 PM ... at Canal View Park, 4418 Main Street, Philadelphia, PA 19127"
  Oldest in The USA Thanksgiving Day Parade | Philadelphia      pubDate 2026-11-26T10:00
      "We meet at 20th Street & John F. Kennedy Boulevard ... at 10:00 AM sharp"
  Christmas Village Walk                                        pubDate 2026-12-05T18:00
      "Saturday, December 5 at 6:00 PM at LOVE Park"
  Founders Philly Freeze-Out 2027                               pubDate 2027-01-31T11:00
      "January 31, 2027 | 11 AM – 4 PM"

Known failure modes:
  * Repeating events are NOT covered. A weekly or yearly event appears once, dated at its
    first occurrence ("Free Weekly Pickleball Game", 2025-08-09; "2027 Mummers Parade",
    2026-01-01); its coming dates live only in the disallowed /api/ data. Such items fall
    outside the feed's window and are dropped, so the weekly pickleball and tennis games
    are missing from this source.
  * An event the organisers move by adding a new schedule may keep its old date here.
  * There is no location field. A place is taken only when the description prints a full
    street address in bold ending in a state and ZIP code ("**Canal View Park, 4418 Main
    Street, Philadelphia, PA 19127**"); otherwise the event has no location.
  * No end time is published; the feed's default length applies.
  * A pubDate in any other format (for example the RFC-822 dates RSS normally uses) is
    not read and the item is skipped.
"""
import datetime as dt
import html
import re

import combined_to_ics as C

ITEM_RX = re.compile(r"<item\b[^>]*>(.*?)</item>", re.S)
ADDRESS_RX = re.compile(r"\*\*([^*\n]{5,140}?,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?)\*\*")


def _field(item, tag):
    m = re.search(r"<%s\b[^>]*>(.*?)</%s>" % (tag, tag), item, re.S)
    if not m:
        return ""
    raw = m.group(1).strip()
    cdata = re.match(r"<!\[CDATA\[(.*?)\]\]>$", raw, re.S)
    return cdata.group(1) if cdata else html.unescape(raw)


BOILERPLATE_RX = re.compile(r"^\W*(J O I N our\b[^\n]*WhatsApp|https://chat\.whatsapp\.com/\S+\s*$|our hosts may be busy)", re.I)


def _plain(description):
    """The organisers write Markdown-style emphasis; show the words without the marks, and
    start after the "join our WhatsApp community" notice that opens some descriptions."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", description.replace("\u200b", "")) if p.strip()]
    while paras and BOILERPLATE_RX.match(paras[0]):
        paras.pop(0)
    s = re.sub(r"\*{1,3}([^*\n]+?)\*{1,3}", r"\1", "\n\n".join(paras))
    return s.replace("<", "\u2039")          # keep an angle bracket in the text from being read as markup


def parse(body, src):
    """Every dated item in the feed -> events (`read` applies the window)."""
    out = []
    for item in ITEM_RX.findall(body):
        title, link = _field(item, "title"), C.clean(_field(item, "link"))
        st = C.parse_iso(C.clean(_field(item, "pubDate")))
        if not title or not st:
            continue
        description = _field(item, "description")
        place = ADDRESS_RX.search(description)
        e = C.event(src, link or f"{title}|{st[0].isoformat()}", title, st[0], None, st[1],
                    place.group(1) if place else "", link, _plain(description))
        if e:
            out.append(e)
    return out


def _day(e):
    return e["start"].date() if isinstance(e["start"], dt.datetime) else e["start"]


def read(src, ctx):
    return [e for e in parse(C.get_text(src["url"]), src) if ctx["lo"] <= _day(e) <= ctx["hi"]]
