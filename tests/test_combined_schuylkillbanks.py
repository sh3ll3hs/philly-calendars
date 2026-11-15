"""Schuylkill Banks reader against saved copies of the listing and two event pages (no network)."""
import datetime as dt
import importlib
import os
import unittest

R = importlib.import_module("combined_readers.schuylkillbanks")

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SRC = {"id": "schuylkillbanks", "name": "Schuylkill Banks", "method": "custom", "reader": "schuylkillbanks",
       "url": "https://www.schuylkillbanks.org/events/upcoming-events"}
RIBBON = "https://www.schuylkillbanks.org/events/schuylkill-crossing-ribbon-cutting-ceremony"
PHOTOS = ("https://www.schuylkillbanks.org/events/community-events/"
          "walking-schuylkill-john-brady-photography-fairmount-water-works")


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


class SchuylkillBanks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.listing = fixture("combined_schuylkillbanks.html")
        cls.ev = {e["title"]: e for e in R.parse(cls.listing, SRC)}

    def test_listing_titles_dates_and_times(self):
        self.assertEqual(len(self.ev), 11)
        ribbon = self.ev["Schuylkill Crossing Ribbon Cutting Ceremony"]
        self.assertEqual(ribbon["start"], dt.datetime(2026, 11, 13, 14, 0))      # "2:00PM- 4:00PM", Fri 13 Nov
        self.assertEqual(ribbon["end"], dt.datetime(2026, 11, 13, 16, 0))
        self.assertFalse(ribbon["all_day"])
        self.assertEqual(ribbon["url"], RIBBON)
        holidays = self.ev["Handmade Holidays at Bartram's Garden"]
        self.assertEqual(holidays["start"], dt.datetime(2026, 12, 5, 12, 0))     # "12:00PM- 3:00PM", Sat 5 Dec
        self.assertEqual(holidays["end"], dt.datetime(2026, 12, 5, 15, 0))
        walk = self.ev["ENIAC Endless Loop Walk by FreeWalkers"]
        self.assertEqual(walk["start"], dt.datetime(2026, 12, 12, 9, 0))
        self.assertEqual(walk["end"], dt.datetime(2026, 12, 12, 16, 0))
        self.assertEqual(walk["desc"], "Community Events")                       # the series line

    def test_start_only_and_two_day_events(self):
        ride = self.ev["Bicycle Club of Phila Ride to the Schuylkill Crossing Ribbon Cutting"]
        self.assertEqual(ride["start"], dt.datetime(2026, 11, 13, 13, 0))        # "1:00PM", no end stated
        self.assertIsNone(ride["end"])
        siege = self.ev["Siege Weekend at Fort Mifflin"]                          # "Through November 15"
        self.assertEqual(siege["start"], dt.datetime(2026, 11, 14, 10, 0))
        self.assertEqual(siege["end"], dt.datetime(2026, 11, 15, 16, 0))

    def test_year_comes_from_the_month_heading(self):
        photos = self.ev["WALKING THE SCHUYLKILL: John Brady Photography at Fairmount Water Works"]
        self.assertEqual(photos["start"], dt.datetime(2026, 9, 19, 10, 0))       # under "September 2026"
        self.assertIsNone(photos["end"])                                          # "10:00AM- 10:00AM" is no length

    def test_event_page_gives_location_and_description(self):
        info = R.parse_detail(fixture("combined_schuylkillbanks_detail.html"))
        self.assertEqual(info["loc"], "Grays Ferry Crescent Esplanade")
        self.assertTrue(info["desc"].startswith("Join Schuylkill River Development Corporation"))
        self.assertIsNone(info["end"])                                            # ends the same day
        ev = {e["title"]: e for e in R.parse(self.listing, SRC, {RIBBON: info})}
        ribbon = ev["Schuylkill Crossing Ribbon Cutting Ceremony"]
        self.assertEqual(ribbon["loc"], "Grays Ferry Crescent Esplanade")
        self.assertEqual(ribbon["start"], dt.datetime(2026, 11, 13, 14, 0))      # time still from the listing text
        self.assertEqual(ev["Handmade Holidays at Bartram's Garden"]["loc"], "")  # no page read, no location invented

    def test_event_page_gives_address_and_closing_day_of_a_long_run(self):
        info = R.parse_detail(fixture("combined_schuylkillbanks_detail2.html"))
        self.assertEqual(info["loc"], "Fairmount Water Works, 640 Waterworks Dr, Philadelphia, PA 19130")
        self.assertEqual(info["end"], dt.date(2027, 1, 8))                        # "to Friday, January 8 at 10:00am"
        ev = {e["title"]: e for e in R.parse(self.listing, SRC, {PHOTOS: info})}
        photos = ev["WALKING THE SCHUYLKILL: John Brady Photography at Fairmount Water Works"]
        self.assertEqual(photos["start"], dt.datetime(2026, 9, 19, 10, 0))
        self.assertEqual(photos["end"], dt.datetime(2027, 1, 8, 10, 0))
        self.assertEqual(photos["loc"], "Fairmount Water Works, 640 Waterworks Dr, Philadelphia, PA 19130")

    def test_read_caches_event_pages_and_opens_only_events_in_the_window(self):
        C = R.C
        pages = {SRC["url"]: self.listing, RIBBON: fixture("combined_schuylkillbanks_detail.html")}
        asked = []

        def fake(url):
            asked.append(url)
            if url not in pages:
                raise OSError("not saved")
            return pages[url]

        today = dt.date(2026, 11, 15)
        ctx = {"lo": today - dt.timedelta(days=3), "hi": today + dt.timedelta(days=120), "today": today, "detail": {}}
        real, C.get_text = C.get_text, fake
        try:
            ev = {e["title"]: e for e in R.read(SRC, ctx)}
            first = len(asked)
            R.read(SRC, ctx)
        finally:
            C.get_text = real
        self.assertEqual(ev["Schuylkill Crossing Ribbon Cutting Ceremony"]["loc"], "Grays Ferry Crescent Esplanade")
        self.assertNotIn(PHOTOS, asked)                   # opened Sep 19: outside the window, page not requested
        self.assertEqual(first, 11)                       # the listing + the 10 events inside the window
        self.assertIn(RIBBON, ctx["detail"])
        self.assertEqual(asked[first:].count(RIBBON), 0)  # second run reads the cached page


if __name__ == "__main__":
    unittest.main()
