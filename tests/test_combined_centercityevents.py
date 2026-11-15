"""CenterCity.Events reader against a trimmed real copy of its RSS feed (no network).

The fixture is six of the 25 items https://centercity.events/rss.xml held on 2026-11-15,
unedited: two repeating events dated at their first occurrence and four dated events."""
import datetime as dt
import importlib
import os
import unittest

import combined_to_ics as C

R = importlib.import_module("combined_readers.centercityevents")
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "combined_centercityevents.xml")
SRC = {"id": "centercityevents", "name": "CenterCity.Events", "method": "custom", "reader": "centercityevents",
       "url": "https://centercity.events/rss.xml", "page": "https://centercity.events/calendar"}
TODAY = dt.date(2026, 11, 15)
CTX = {"lo": TODAY - dt.timedelta(days=3), "hi": TODAY + dt.timedelta(days=120), "today": TODAY, "detail": {}}


def body():
    with open(FIX, encoding="utf-8") as f:
        return f.read()


class CenterCityEvents(unittest.TestCase):
    def setUp(self):
        self.events = R.parse(body(), SRC)
        self.by = {e["url"].rsplit("/", 1)[-1]: e for e in self.events}

    def test_every_dated_item_is_parsed(self):
        self.assertEqual(sorted(self.by), ["184", "187", "193", "6", "78", "87"])

    def test_pubdate_is_the_start_in_local_time(self):
        # the item text says "We meet at 5:15 PM ... before the live performances begin at 5:30 PM"
        e = self.by["193"]
        self.assertEqual(e["title"], "🎅🎄 Manayunk Christmas Tree Lighting Ceremony | Canal View Park")
        self.assertEqual(e["start"], dt.datetime(2026, 11, 19, 17, 15))
        self.assertIn("We **meet at 5:15 PM**, 15 minutes before the ceremony", body())
        self.assertFalse(e["all_day"])
        self.assertIsNone(e["end"])
        # "at 10:00 AM sharp"
        self.assertEqual(self.by["187"]["start"], dt.datetime(2026, 11, 26, 10, 0))
        # "Saturday, December 5 at 6:00 PM"
        self.assertEqual(self.by["184"]["start"], dt.datetime(2026, 12, 5, 18, 0))
        self.assertEqual(self.by["184"]["start"].strftime("%A"), "Saturday")
        # "January 31, 2027 | 11 AM – 4 PM"
        self.assertEqual(self.by["87"]["start"], dt.datetime(2027, 1, 31, 11, 0))

    def test_location_only_from_a_printed_street_address(self):
        self.assertEqual(self.by["193"]["loc"], "Canal View Park, 4418 Main Street, Philadelphia, PA 19127")
        self.assertEqual(self.by["187"]["loc"], "20th Street & John F. Kennedy Boulevard, Philadelphia, PA 19103")
        self.assertEqual(self.by["184"]["loc"], "")       # "at LOVE Park": no address printed, none invented
        self.assertEqual(self.by["87"]["loc"], "")

    def test_titles_links_and_plain_description(self):
        self.assertEqual(self.by["187"]["title"], "🦃 Oldest in The USA Thanksgiving Day Parade | Philadelphia")
        self.assertEqual(self.by["87"]["title"], "🧊 Founders Philly Freeze-Out 2027")
        self.assertEqual(self.by["193"]["url"], "https://centercity.events/events/193")
        self.assertNotIn("**", self.by["187"]["desc"])
        # the "join our WhatsApp community" notice that opens some descriptions is not the event's description
        self.assertTrue(self.by["193"]["desc"].startswith(
            "🎅🎄 Join CenterCity.Events for the Manayunk Christmas Tree Lighting Ceremony"))
        self.assertNotIn("whatsapp", self.by["193"]["desc"].lower())
        self.assertTrue(self.by["187"]["desc"].startswith("Join CenterCity.Events for the 6abc Dunkin' Thanksgiving Day Parade"))

    def test_read_drops_repeating_events_dated_at_their_first_occurrence(self):
        # "Free Weekly Pickleball Game" is dated 2025-08-09 and "2027 Mummers Parade" 2026-01-01
        self.assertEqual(self.by["6"]["start"], dt.datetime(2025, 8, 9, 10, 30))
        self.assertEqual(self.by["78"]["start"], dt.datetime(2026, 1, 1, 13, 0))
        keep, seen = C.get_text, []
        C.get_text = lambda url: seen.append(url) or body()
        try:
            got = R.read(SRC, CTX)
        finally:
            C.get_text = keep
        self.assertEqual(seen, ["https://centercity.events/rss.xml"])
        self.assertEqual(sorted(e["url"].rsplit("/", 1)[-1] for e in got), ["184", "187", "193", "87"])

    def test_items_without_a_readable_date_are_skipped(self):
        feed = ("<rss><channel>"
                "<item><title>RFC date</title><link>https://centercity.events/events/1</link>"
                "<pubDate>Thu, 19 Nov 2026 17:15:00 GMT</pubDate></item>"
                "<item><title>No date</title><link>https://centercity.events/events/2</link></item>"
                "<item><title><![CDATA[Dinner & Drinks]]></title><link>https://centercity.events/events/3</link>"
                "<description>Meet at **Some Bar, 1 Main St, Camden, NJ 08102**</description>"
                "<pubDate>2026-12-01T19:00:00</pubDate></item>"
                "</channel></rss>")
        (e,) = R.parse(feed, SRC)
        self.assertEqual((e["title"], e["start"], e["loc"]),
                         ("Dinner & Drinks", dt.datetime(2026, 12, 1, 19, 0), "Some Bar, 1 Main St, Camden, NJ 08102"))


if __name__ == "__main__":
    unittest.main()
