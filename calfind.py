#!/usr/bin/env python3
"""
calfind.py — find subscribable calendar feeds embedded in a web page.

Usage:
    python3 calfind.py https://www.phillydsa.org/events
    python3 calfind.py URL1 URL2 ...          # several sites at once
    python3 calfind.py --deep URL             # also open each embedded iframe page once

It prints a ready-to-subscribe ICS URL for every feed it finds, plus any event
platforms (Action Network, Mobilize, Eventbrite, Meetup, Luma) that point to events
but don't expose a public feed. No third-party packages are needed.
"""
import html
import re
import sys
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (calfind; +calendar feed finder)"

# Google Calendar IDs look like an email address. Only count them when they sit in a
# Google Calendar link (embed src=, cid=, or /ical/), so contact emails in event text
# aren't mistaken for calendars.
_ID = (r"[A-Za-z0-9._%+-]+@(?:group\.calendar\.google\.com|gmail\.com|"
       r"import\.calendar\.google\.com|resource\.calendar\.google\.com)")
GCAL_ID = re.compile(
    r"calendar\.google\.com/calendar/(?:[^\s\"'<>]*?[?&](?:src|cid)=|ical/)(" + _ID + ")"
)
ICS = re.compile(r"""(?:https?|webcal)://[^\s"'<>()]+?\.ics(?:\?[^\s"'<>()]*)?""", re.I)
IFRAME_SRC = re.compile(r"""<iframe[^>]+src=["']([^"']+)["']""", re.I)
PLATFORMS = {
    "Action Network": re.compile(r"""https?://actionnetwork\.org/(?:groups|events|event_campaigns)/[^\s"'<>]+""", re.I),
    "Mobilize": re.compile(r"""https?://(?:www\.)?mobilize\.us/[^\s"'<>]+""", re.I),
    "Eventbrite": re.compile(r"""https?://(?:www\.)?eventbrite\.[a-z.]+/(?:o|e)/[^\s"'<>]+""", re.I),
    "Meetup": re.compile(r"""https?://(?:www\.)?meetup\.com/[^\s"'<>/]+""", re.I),
    "Luma": re.compile(r"""https?://lu\.ma/[^\s"'<>]+""", re.I),
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", "replace")


def unwrap(text):
    """Undo HTML entities and URL encoding (repeatedly) so hidden links show up."""
    out = [text]
    t = html.unescape(text)
    for _ in range(3):
        out.append(t)
        nt = urllib.parse.unquote(t)
        if nt == t:
            break
        t = nt
    return "\n".join(out)


def gcal_feed(cal_id):
    return ("https://calendar.google.com/calendar/ical/"
            + urllib.parse.quote(cal_id, safe="") + "/public/basic.ics")


def scan(page_url, text, feeds, platforms):
    blob = unwrap(text)
    for cid in GCAL_ID.findall(blob):
        feeds.setdefault(gcal_feed(cid), f"Google Calendar ({cid})")
    for link in ICS.findall(blob):
        link = re.sub(r"^webcal://", "https://", link, flags=re.I)
        if "calendar.google.com" in link:
            continue  # already handled via the calendar ID
        feeds.setdefault(link, "ICS feed")
    for name, rx in PLATFORMS.items():
        for link in rx.findall(blob):
            platforms.setdefault(link.rstrip(".,;"), name)
    return [urllib.parse.urljoin(page_url, html.unescape(s)) for s in IFRAME_SRC.findall(text)]


TEC_MARK = re.compile(r"tribe-events|the-events-calendar|tribe_events", re.I)


def probe_known_plugins(page_url, text, feeds):
    """Some calendar plugins publish a feed at a conventional URL that never appears
    in the page source. The Events Calendar (WordPress) answers at <page>?ical=1."""
    if TEC_MARK.search(text):
        base = page_url.split("?")[0].split("#")[0]
        root = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(base))
        for cand in (base + "?ical=1", root + "/events/?ical=1"):
            try:
                req = urllib.request.Request(cand, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=20) as r:
                    if "text/calendar" in (r.headers.get("Content-Type") or ""):
                        feeds.setdefault(cand, "The Events Calendar export")
                        break
            except Exception:
                pass


def check(feed):
    """Return the number of events in a feed, or None if it can't be read."""
    try:
        return fetch(feed).count("BEGIN:VEVENT")
    except Exception:
        return None


def main(argv):
    deep = "--deep" in argv
    urls = [a for a in argv if not a.startswith("--")]
    if not urls:
        print(__doc__)
        return 1
    for url in urls:
        print(f"\n=== {url}")
        feeds, platforms = {}, {}
        try:
            text = fetch(url)
            iframes = scan(url, text, feeds, platforms)
            probe_known_plugins(url, text, feeds)
        except Exception as e:
            print(f"  could not load page: {e}")
            continue
        if deep:
            for src in iframes:
                try:
                    scan(src, fetch(src), feeds, platforms)
                except Exception:
                    pass
        if feeds:
            print("Subscribable feeds:")
            for feed, label in feeds.items():
                n = check(feed)
                status = f"{n} events" if n is not None else "not reachable"
                print(f"  [{label}] {status}\n    {feed}")
        else:
            print("No calendar feed found."
                  + ("" if deep else " Try --deep, or the page may load events with JavaScript."))
        if platforms:
            print("Event platforms linked (no public feed):")
            for link, name in platforms.items():
                print(f"  [{name}] {link}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
