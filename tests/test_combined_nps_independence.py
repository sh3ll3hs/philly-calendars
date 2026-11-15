"""NPS Independence reader against a saved response of the park calendar's event service (no network)."""
import datetime as dt
import importlib
import json
import os
import unittest

R = importlib.import_module("combined_readers.nps_independence")

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "combined_nps_independence.json")
SRC = {"id": "nps_independence", "name": "Independence National Historical Park", "method": "custom",
       "reader": "nps_independence", "url": "https://www.nps.gov/inde/planyourvisit/calendar.htm",
       "parks": "inde,edal,thko,glde", "city": "Philadelphia, PA"}
DETAIL = "https://www.nps.gov/planyourvisit/event-details.htm?id="


class NpsIndependence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIX, encoding="utf-8") as f:
            cls.body = f.read()
        cls.events = R.parse(cls.body, SRC)
        cls.by = {(e["title"], e["start"]): e for e in cls.events}

    def test_one_entry_per_listed_day(self):
        # 14 + 27 + 1 days of the daily talk, plus three single events
        self.assertEqual(len(self.events), 45)
        talks = [e for e in self.events if e["title"] == "First Bank of the US Guided Ranger Talk"]
        self.assertEqual(len(talks), 42)
        self.assertEqual(min(e["start"] for e in talks), dt.datetime(2026, 11, 12, 12, 0))
        self.assertEqual(max(e["start"] for e in talks), dt.datetime(2026, 12, 24, 13, 0))
        self.assertNotIn(dt.date(2026, 11, 26), {e["start"].date() for e in talks})      # no talk on Thanksgiving
        self.assertEqual(len({e["key"] for e in self.events}), 45)

    def test_first_session_is_the_start_and_the_rest_are_named(self):
        # site: "Every day at 12:00 PM, 1:00 PM, 2:00 PM, and 3:00 PM ... Duration: 30 minutes"
        e = self.by[("First Bank of the US Guided Ranger Talk", dt.datetime(2026, 11, 15, 12, 0))]
        self.assertEqual(e["end"], dt.datetime(2026, 11, 15, 12, 30))
        self.assertFalse(e["all_day"])
        self.assertTrue(e["desc"].startswith("Also at 1:00 PM, 2:00 PM and 3:00 PM. Free."))
        self.assertEqual(e["loc"], "120 S 3rd Street, Independence National Historical Park, Philadelphia, PA")
        self.assertEqual(e["url"], DETAIL + "C4E864A3-9A04-F023-18E5B21766824F05")
        # from Nov 27 the same talk runs at 1, 2, 3 and 4 PM
        later = self.by[("First Bank of the US Guided Ranger Talk", dt.datetime(2026, 12, 1, 13, 0))]
        self.assertEqual(later["end"], dt.datetime(2026, 12, 1, 13, 30))
        self.assertTrue(later["desc"].startswith("Also at 2:00 PM, 3:00 PM and 4:00 PM."))
        eve = self.by[("First Bank of the US Guided Ranger Talk", dt.datetime(2026, 12, 24, 13, 0))]
        self.assertTrue(eve["desc"].startswith("Also at 2:00 PM."))

    def test_single_events(self):
        title = "21st Century Tribal Nations' Perspectives on the American Revolution"
        e = self.by[(title, dt.datetime(2026, 11, 19, 17, 30))]                             # "Nov 19, 2026 at 5:30 PM", 2 hours
        self.assertEqual(e["end"], dt.datetime(2026, 11, 19, 19, 30))
        self.assertEqual(e["loc"], "Science History Institute, Ullyot Meeting Hall, 315 Chestnut Street, Philadelphia, PA 19106")
        self.assertEqual(e["url"], DETAIL + "F0DC030B-DC82-FA66-E8AEA906F5B15758")
        e = self.by[("Benjamin Franklin: America's First Diplomat", dt.datetime(2026, 12, 2, 17, 30))]
        self.assertEqual(e["end"], dt.datetime(2026, 12, 2, 19, 30))
        self.assertEqual(e["loc"], "First Bank of the United States, 120 S 3rd Street, "
                                   "Independence National Historical Park, Philadelphia, PA")
        e = self.by[("Free Entrance to the Benjamin Franklin Museum", dt.datetime(2027, 1, 17, 9, 0))]
        self.assertEqual(e["end"], dt.datetime(2027, 1, 17, 17, 0))

    def test_no_time_is_never_invented(self):
        data = json.loads(self.body)
        row = dict(data["data"][1], id="X-ALLDAY", isAllDay=True, dates=["2026-12-05"])
        sunrise = dict(data["data"][1], id="X-SUNRISE", dates=["2026-12-06"],
                       times=[{"timeStart": "", "timeEnd": "", "sunriseStart": True, "sunsetEnd": False}])
        got = {e["key"]: e for e in R.parse({"data": [row, sunrise]}, SRC)}
        self.assertEqual(got["X-ALLDAY|2026-12-05"]["start"], dt.date(2026, 12, 5))
        self.assertTrue(got["X-ALLDAY|2026-12-05"]["all_day"])
        self.assertEqual(got["X-SUNRISE|2026-12-06"]["start"], dt.date(2026, 12, 6))
        self.assertTrue(got["X-SUNRISE|2026-12-06"]["all_day"])

    def test_cancelled_dates_are_skipped(self):
        data = json.loads(self.body)
        row = dict(data["data"][0], cancelledDateList="2026-11-13,2026-11-14")
        days = {e["start"].date() for e in R.parse({"data": [row]}, SRC)}
        self.assertEqual(len(days), 12)
        self.assertNotIn(dt.date(2026, 11, 13), days)
        row = dict(data["data"][0], cancelledDateList=["2026-11-20"])
        self.assertNotIn(dt.date(2026, 11, 20), {e["start"].date() for e in R.parse({"data": [row]}, SRC)})


if __name__ == "__main__":
    unittest.main()
