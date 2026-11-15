"""Delaware River Waterfront reader against saved copies of the RSS view and two event pages (no network)."""
import datetime as dt
import importlib
import os
import unittest

import combined_to_ics as C

R = importlib.import_module("combined_readers.drwc")

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SRC = {"id": "drwc", "name": "Delaware River Waterfront", "method": "custom", "reader": "drwc",
       "url": "https://www.delawareriverwaterfront.com/what-to-do"}
BASE = "https://www.delawareriverwaterfront.com/what-to-do/"
RINK = "Independence Blue Cross RiverRink Winterfest, 101 South Columbus Boulevard, Philadelphia, PA 19106"
TODAY = dt.date(2026, 11, 15)          # the day the feed was saved


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


class Drwc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.feed = fixture("combined_drwc.xml")
        cls.events = R.parse(cls.feed, SRC, TODAY)
        cls.by = {e["title"]: e for e in cls.events}

    def test_titles_dates_and_times(self):
        self.assertEqual(len(self.events), 4)
        tree = self.by["Holiday Tree Lighting Powered by PECO featuring Zinadelphia"]
        self.assertEqual(tree["start"], dt.datetime(2026, 11, 29, 17, 0))        # "Nov 29 5:00 pm - Nov 29 8:00 pm"
        self.assertEqual(tree["end"], dt.datetime(2026, 11, 29, 20, 0))
        self.assertFalse(tree["all_day"])
        self.assertEqual(tree["url"], BASE + "holiday-tree-lighting-powered-by-peco-2026")
        self.assertTrue(tree["desc"].startswith("Join us for the Annual Holiday Tree Lighting"))
        weekend = self.by["Opening Weekend: Independence Blue Cross RiverRink Winterfest"]
        self.assertEqual(weekend["start"], dt.datetime(2026, 11, 27, 11, 0))     # "Nov 27 11:00 am - Nov 29 11:00 pm"
        self.assertEqual(weekend["end"], dt.datetime(2026, 11, 29, 23, 0))

    def test_year_only_when_the_site_prints_one(self):
        party = self.by["(TICKETED EVENT) Valentine's Day Fire & Ice Party"]      # "Feb 13 '27 7:00 pm - Feb 13 '27 10:30 pm"
        self.assertEqual(party["start"], dt.datetime(2027, 2, 13, 19, 0))
        self.assertEqual(party["end"], dt.datetime(2027, 2, 13, 22, 30))
        # a date without a year belongs to the year the feed was built, whatever "today" is
        self.assertEqual(R.parse(self.feed, SRC, dt.date(2027, 3, 1))[0]["start"], dt.datetime(2026, 11, 27, 11, 0))

    def test_end_past_midnight_moves_to_the_next_day(self):
        nye = self.by["New Year’s Eve Fireworks on the Waterfront"]          # "Dec 31 6:00 pm - Dec 31 12:30 am"
        self.assertEqual(nye["start"], dt.datetime(2026, 12, 31, 18, 0))
        self.assertEqual(nye["end"], dt.datetime(2027, 1, 1, 0, 30))

    def test_heading_without_a_time_is_all_day(self):
        feed = self.feed.replace("5:00 pm", "").replace("8:00 pm", "")
        tree = {e["title"]: e for e in R.parse(feed, SRC, TODAY)}["Holiday Tree Lighting Powered by PECO featuring Zinadelphia"]
        self.assertEqual(tree["start"], dt.date(2026, 11, 29))
        self.assertTrue(tree["all_day"])
        self.assertIsNone(tree["end"])

    def test_event_page_gives_the_place_and_address(self):
        self.assertEqual(R.parse_detail(fixture("combined_drwc_detail.html"))["loc"], RINK)
        self.assertEqual(R.parse_detail(fixture("combined_drwc_detail_noplace.html"))["loc"], "")
        self.assertEqual(R.parse_detail("<html><body></body></html>")["loc"], "")

    def test_read_adds_locations_from_cached_event_pages(self):
        pages = {BASE.rstrip("/") + "?feed=rss": self.feed,
                 BASE + "holiday-tree-lighting-powered-by-peco-2026": fixture("combined_drwc_detail.html"),
                 BASE + "new-year-s-eve-fireworks-on-the-waterfront-2027": fixture("combined_drwc_detail_noplace.html")}
        asked = []

        def fake(url):
            asked.append(url)
            if url not in pages:
                raise RuntimeError("404")
            return pages[url]

        real, C.get_text = C.get_text, fake
        try:
            ctx = {"lo": TODAY - dt.timedelta(days=3), "hi": TODAY + dt.timedelta(days=120), "today": TODAY, "detail": {}}
            first = {e["title"]: e for e in R.read(SRC, ctx)}
            n = len(asked)
            second = {e["title"]: e for e in R.read(SRC, ctx)}
        finally:
            C.get_text = real
        self.assertEqual(n, 5)                                  # the feed + four event pages
        self.assertEqual(first["Holiday Tree Lighting Powered by PECO featuring Zinadelphia"]["loc"], RINK)
        self.assertEqual(first["New Year’s Eve Fireworks on the Waterfront"]["loc"], "")
        self.assertEqual(first["Holiday Tree Lighting Powered by PECO featuring Zinadelphia"]["start"],
                         dt.datetime(2026, 11, 29, 17, 0))
        # second run: the two pages that loaded come from the cache, the two that failed are retried
        self.assertEqual(len(asked) - n, 3)
        self.assertEqual(second["Holiday Tree Lighting Powered by PECO featuring Zinadelphia"]["loc"], RINK)


if __name__ == "__main__":
    unittest.main()
