"""Cherry Street Pier reader against trimmed copies of the events listing and five event pages (no network)."""
import datetime as dt
import importlib
import os
import unittest

import combined_to_ics as C

R = importlib.import_module("combined_readers.cherrystreetpier")

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
VENUE = "Cherry Street Pier, 121 N Christopher Columbus Blvd, Philadelphia, PA 19106"
SRC = {"id": "cherrystreetpier", "name": "Cherry Street Pier", "method": "custom", "reader": "cherrystreetpier",
       "url": "https://www.cherrystreetpier.com/events/", "venue": VENUE}
BASE = "https://www.cherrystreetpier.com/event/"
DRAW = BASE + "2026/11/drink-n-draw-cosplay/"
SUMMIT = BASE + "2026/11/kinkeeping-summit-and-holiday-market/"
FRIDAY = BASE + "2021/11/first-friday-at-cherry-street-pier/"
MARKET = BASE + "2026/03/artist-and-artisans-market/"
EXHIBIT = BASE + "2026/10/opening-reception-dunu-artists/"
PAGES = {DRAW: "day", SUMMIT: "summit", FRIDAY: "firstfriday", MARKET: "market", EXHIBIT: "exhibit"}
TODAY = dt.date(2026, 11, 15)          # the day the pages were saved


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def detail(url, title=""):
    return R.parse_detail(fixture(f"combined_cherrystreetpier_{PAGES[url]}.html"), SRC, url, title, TODAY)


class CherryStreetPier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.listing = fixture("combined_cherrystreetpier.html")

    def test_listing_cards(self):
        cards = R.cards(self.listing, SRC)
        self.assertEqual(len(cards), 8)
        self.assertEqual(cards[0], (MARKET, "Artist and Artisans Market 2026", "April 3–December 4"))
        self.assertEqual(cards[6], (DRAW, "Drink N’ Draw Featuring a Live Cosplay Model", "Sunday, November 15"))
        self.assertEqual(cards[7], (SUMMIT, "DiasporaDNA Kinkeeping Summit & Holiday Market", "Saturday, November 21"))

    def test_listing_alone_gives_all_day_entries_and_never_a_time(self):
        ev = {e["url"]: e for e in R.parse(self.listing, SRC, TODAY)}
        self.assertEqual(len(ev), 8)
        self.assertEqual(ev[SUMMIT]["title"], "DiasporaDNA Kinkeeping Summit & Holiday Market")
        self.assertEqual(ev[SUMMIT]["start"], dt.date(2026, 11, 21))
        self.assertTrue(all(e["all_day"] for e in ev.values()))
        self.assertEqual((ev[EXHIBIT]["start"], ev[EXHIBIT]["end"]), (dt.date(2026, 11, 6), dt.date(2026, 12, 28)))
        self.assertEqual(ev[SUMMIT]["loc"], VENUE)

    def test_single_day_pages_title_date_time_location(self):
        (e,) = detail(DRAW)                         # "Sunday / November 15 / 2026", "Time: 1pm to 3pm", "Location: Amphitheater"
        self.assertEqual(e["title"], "Drink N’ Draw Featuring a Live Cosplay Model")
        self.assertEqual(e["start"], dt.datetime(2026, 11, 15, 13, 0))
        self.assertEqual(e["end"], dt.datetime(2026, 11, 15, 15, 0))
        self.assertFalse(e["all_day"])
        self.assertEqual(e["loc"], "Amphitheater, " + VENUE)
        self.assertEqual(e["url"], DRAW)
        (e,) = detail(SUMMIT, "DiasporaDNA Kinkeeping Summit & Holiday Market")     # "Time: 11am to 3pm"
        self.assertEqual((e["start"], e["end"]), (dt.datetime(2026, 11, 21, 11, 0), dt.datetime(2026, 11, 21, 15, 0)))
        self.assertEqual(e["loc"], VENUE)                                           # "Location: Cherry Street Pier"
        self.assertTrue(e["desc"].startswith("Join DiasporaDNA Story Center"))

    def test_the_google_calendar_link_is_not_the_source_of_times(self):
        # the page's link says 16:00Z-24:00Z (11 am-7 pm) for an event the page gives as 1pm to 3pm
        self.assertIn("1pm to 3pm", fixture("combined_cherrystreetpier_day.html"))
        self.assertNotEqual(detail(DRAW)[0]["start"].hour, 11)

    def test_run_with_written_out_dates(self):
        ev = detail(FRIDAY, "First Friday presented by Fulton Bank")       # "May 1-December 4 2026", "Time: 4 pm to 9 pm"
        days = [e["start"] for e in ev]
        # "First Friday dates: March 6, April 3, May 1, ... and December 4." kept inside the run
        self.assertEqual(days, [dt.datetime(2026, m, d, 16, 0) for m, d in
                                ((5, 1), (6, 5), (7, 3), (8, 7), (9, 4), (10, 2), (11, 6), (12, 4))])
        self.assertTrue(all(e["end"] == e["start"].replace(hour=21) for e in ev))
        self.assertEqual(len({e["key"] for e in ev}), 8)
        ev = detail(MARKET, "Artist and Artisans Market 2026")             # "Time: Select Fridays from 4 pm to 9 pm" + "Schedule:"
        self.assertEqual(len(ev), 9)
        self.assertEqual(ev[-1]["start"], dt.datetime(2026, 12, 4, 16, 0))
        self.assertEqual(ev[-1]["end"], dt.datetime(2026, 12, 4, 21, 0))
        self.assertEqual(ev[-1]["loc"], "The Market, " + VENUE)
        self.assertTrue(all(e["start"].weekday() == 4 for e in ev))

    def test_run_without_listed_dates_is_one_all_day_entry(self):
        (e,) = detail(EXHIBIT)                      # "November 6-December 28 2026", "Time: Pier Operating Hours"
        self.assertEqual(e["title"], "Termite TV Resident Artists: Joy Waldinger and Lee Bird Exhibition")
        self.assertEqual((e["start"], e["end"]), (dt.date(2026, 11, 6), dt.date(2026, 12, 28)))
        self.assertTrue(e["all_day"])

    def test_hours_and_dates_helpers(self):
        self.assertEqual(R.hours("Time: 11am to 3pm"), ((dt.time(11, 0), dt.time(15, 0)), set(), True))
        self.assertEqual(R.hours("Time: Select Fridays from 4 pm to 9 pm"), ((dt.time(16, 0), dt.time(21, 0)), {4}, False))
        for vague in ("Time: Times Vary", "Time: Pier Operating Hours", "", "Time: 11am to 3pm and 5pm to 8pm"):
            self.assertIsNone(R.hours(vague)[0])
        self.assertEqual(R.span("November 6–26 2026", TODAY), (dt.date(2026, 11, 6), dt.date(2026, 11, 26)))
        self.assertEqual(R.span("Sunday, November 15", TODAY), (dt.date(2026, 11, 15), None))
        self.assertEqual(R.span("December 15–January 5", TODAY), (dt.date(2026, 12, 15), dt.date(2027, 1, 5)))
        text = "We are closed: November 26, December 24, December 25. Join us."
        self.assertEqual(R.listed_dates(text, dt.date(2026, 11, 1), dt.date(2026, 12, 31)), [])

    def test_read_uses_event_pages_and_caches_them(self):
        pages = {SRC["url"]: self.listing}
        pages.update({u: fixture(f"combined_cherrystreetpier_{n}.html") for u, n in PAGES.items()})
        asked = []

        def fake(url):
            asked.append(url)
            if url not in pages:
                raise RuntimeError("404")
            return pages[url]

        real, C.get_text = C.get_text, fake
        try:
            ctx = {"lo": TODAY - dt.timedelta(days=3), "hi": TODAY + dt.timedelta(days=120), "today": TODAY, "detail": {}}
            first = R.read(SRC, ctx)
            n = len(asked)
            second = R.read(SRC, ctx)
        finally:
            C.get_text = real
        self.assertEqual(n, 9)                                   # the listing + eight event pages
        self.assertEqual(len(asked) - n, 4)                      # listing + the three pages that failed; five came from the cache
        by = {(e["url"], C.day_of(e)): e for e in first}
        self.assertEqual(by[(DRAW, dt.date(2026, 11, 15))]["start"], dt.datetime(2026, 11, 15, 13, 0))
        self.assertEqual(by[(FRIDAY, dt.date(2026, 12, 4))]["start"], dt.datetime(2026, 12, 4, 16, 0))
        self.assertEqual(by[(MARKET, dt.date(2026, 12, 4))]["loc"], "The Market, " + VENUE)
        # pages that could not be read fall back to the card: date only, all day
        gallery = by[(BASE + "2026/11/in-diasporadna-exhibit/", dt.date(2026, 11, 6))]
        self.assertTrue(gallery["all_day"])
        self.assertEqual([(e["key"], e["start"]) for e in first], [(e["key"], e["start"]) for e in second])


if __name__ == "__main__":
    unittest.main()
