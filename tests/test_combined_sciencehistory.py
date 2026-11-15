"""Science History Institute reader against a trimmed copy of the events listing (no network)."""
import datetime as dt
import importlib
import os
import unittest

R = importlib.import_module("combined_readers.sciencehistory")

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "combined_sciencehistory.html")
VENUE = "Science History Institute, 315 Chestnut St, Philadelphia, PA 19106"
SRC = {"id": "sciencehistory", "name": "Science History Institute", "method": "custom", "reader": "sciencehistory",
       "url": "https://www.sciencehistory.org/visit/events/", "venue": VENUE}
BASE = "https://www.sciencehistory.org/visit/events/"
TODAY = dt.date(2026, 11, 15)          # the day the page was saved


class ScienceHistory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIX, encoding="utf-8") as f:
            cls.body = f.read()
        cls.events = R.parse(cls.body, SRC, TODAY)
        cls.by = {e["url"]: e for e in cls.events}

    def test_every_card_is_read_in_page_order(self):
        self.assertEqual(len(self.events), 10)
        self.assertEqual([e["title"] for e in self.events][:3],
                         ["Othmer Library Tour", "The Electrical Grid in Flux", "Forensics Highlights Tour"])
        self.assertEqual(self.events, sorted(self.events, key=lambda e: e["start"]))

    def test_titles_dates_times_location(self):
        e = self.by[BASE + "othmer-library-tour-20261118/"]           # "Nov 18 Wed", "12pm-12:45pm"
        self.assertEqual(e["title"], "Othmer Library Tour")
        self.assertEqual(e["start"], dt.datetime(2026, 11, 18, 12, 0))
        self.assertEqual(e["end"], dt.datetime(2026, 11, 18, 12, 45))
        self.assertFalse(e["all_day"])
        self.assertEqual(e["loc"], VENUE)
        self.assertIn("Step into the Othmer Library of Chemical History!", e["desc"])
        self.assertTrue(e["desc"].endswith("Free · Library Programs & Activities · Tours"))
        e = self.by[BASE + "first-friday-start-talking-science-2026/"]    # "Dec 04 Fri", "5pm-7pm"
        self.assertEqual(e["title"], "First Friday: Start Talking Science")
        self.assertEqual((e["start"], e["end"]), (dt.datetime(2026, 12, 4, 17, 0), dt.datetime(2026, 12, 4, 19, 0)))
        e = self.by[BASE + "othmer-library-tour-20261204/"]           # "4:15pm-5pm"
        self.assertEqual((e["start"], e["end"]), (dt.datetime(2026, 12, 4, 16, 15), dt.datetime(2026, 12, 4, 17, 0)))

    def test_start_time_without_an_end(self):
        e = self.by[BASE + "forensics-highlights-tour-20261121/"]     # "11:30am"
        self.assertEqual(e["start"], dt.datetime(2026, 11, 21, 11, 30))
        self.assertIsNone(e["end"])
        e = self.by[BASE + "women-in-chemistry-tour-202612/"]         # "2pm"
        self.assertEqual(e["start"], dt.datetime(2026, 12, 12, 14, 0))
        self.assertIsNone(e["end"])

    def test_online_and_hybrid_labels_set_the_location(self):
        e = self.by[BASE + "the-electrical-grid-in-flux/"]            # "Nov 19 Thu", "1pm-2pm", label Online
        self.assertEqual((e["start"], e["end"]), (dt.datetime(2026, 11, 19, 13, 0), dt.datetime(2026, 11, 19, 14, 0)))
        self.assertEqual(e["loc"], "Online")
        e = self.by[BASE + "pain-and-its-killers-what-a-new-class-of-non-opioid-pain-medicine-could-mean-for-society/"]
        self.assertEqual((e["start"], e["end"]), (dt.datetime(2026, 12, 16, 18, 0), dt.datetime(2026, 12, 16, 20, 0)))
        self.assertEqual(e["loc"], VENUE + " (also online)")

    def test_year_comes_from_the_weekday(self):
        e = self.by[BASE + "stories-of-science-wondrous-wool-20270102/"]   # "Jan 02 Sat" -> 2027
        self.assertEqual((e["start"], e["end"]), (dt.datetime(2027, 1, 2, 10, 0), dt.datetime(2027, 1, 2, 17, 0)))
        # the same page read a year later would not find a Wednesday on Nov 18 2027 or 2028
        self.assertEqual(R.parse(self.body, SRC, dt.date(2027, 6, 1))[0]["start"], dt.datetime(2026, 11, 18, 12, 0))

    def test_multi_day_card(self):
        e = self.by[BASE + "oral-history-training-institute-202701/"]     # "Jan 04 Mon" - "Jan 07 Thu", "10am-1pm"
        self.assertEqual(e["start"], dt.datetime(2027, 1, 4, 10, 0))
        self.assertEqual(e["end"], dt.datetime(2027, 1, 7, 13, 0))
        self.assertEqual(e["loc"], "Online")

    def test_card_without_a_time_is_all_day(self):
        body = self.body.replace("12pm-12:45pm", "", 1)
        e = R.parse(body, SRC, TODAY)[0]
        self.assertEqual(e["start"], dt.date(2026, 11, 18))
        self.assertTrue(e["all_day"])

    def test_next_page_link(self):
        self.assertEqual(R.next_page(self.body, BASE), BASE + "page/2/")
        self.assertEqual(R.next_page("<html><body></body></html>", BASE), "")


if __name__ == "__main__":
    unittest.main()
