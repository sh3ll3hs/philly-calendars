"""Parser tests against saved pages (tests/fixtures/), so layout changes show up as
failures instead of silently empty feeds. No network.

    python3 -m unittest discover -s tests -v
"""
import datetime as dt
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
FIX = os.path.join(ROOT, "tests", "fixtures")
TODAY = dt.date(2026, 11, 8)  # the day the fixtures were saved

from common.normalize import expand_dates, normalize_time  # noqa: E402
from scrapers import dawson, livenation_tm, mann, parx, queen, sellersville, south  # noqa: E402


def fx(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def check_shape(tc, recs):
    keys = {"venue", "title", "subtitle", "date", "show_time", "doors_time", "set_times",
            "url", "ticket_url", "price", "source", "needs_manual"}
    for r in recs:
        tc.assertTrue(keys <= set(r), r)
        tc.assertRegex(r["date"], r"^\d{4}-\d{2}-\d{2}$")
        if r["show_time"]:
            tc.assertRegex(r["show_time"], r"^\d{2}:\d{2}$")
        tc.assertEqual(r["needs_manual"], r["show_time"] is None)


class Normalize(unittest.TestCase):
    def test_times(self):
        cases = {"8:00PM": ["20:00"], "8:00 PM": ["20:00"], "6:30pm": ["18:30"], "7PM": ["19:00"],
                 "5pm": ["17:00"], "7:30PM & 9:30PM": ["19:30", "21:30"],
                 "6:30PM and 9:00PM": ["18:30", "21:00"], "7 p.m.": ["19:00"], "no time": []}
        for s, want in cases.items():
            self.assertEqual(normalize_time(s), want, s)

    def test_dates(self):
        d = lambda s: [x.isoformat() for x in expand_dates(s, TODAY)]
        self.assertEqual(d("FRI, SAT & SUN NOV 13, 14 & 15"), ["2026-11-13", "2026-11-14", "2026-11-15"])
        self.assertEqual(d("FRI-SUN MAY 16-18"), ["2027-05-16", "2027-05-17", "2027-05-18"])
        self.assertEqual(d("December 4, 5 & 6"), ["2026-12-04", "2026-12-05", "2026-12-06"])
        self.assertEqual(d("Jan 3"), ["2027-01-03"])  # rolls into next year


class South(unittest.TestCase):
    def test_listing(self):
        recs = south.parse(fx("south_listing.html"), TODAY)
        check_shape(self, recs)
        pher = next(r for r in recs if r["title"] == "PHER")
        self.assertEqual((pher["date"], pher["set_times"]), ("2026-11-08", ["18:00", "20:30"]))
        arp = [r for r in recs if r["title"].startswith("ARPEGGIO")]
        self.assertEqual(len(arp), 3)                       # Fri/Sat/Sun expanded
        self.assertTrue(all(r["needs_manual"] for r in arp))  # "showtimes vary" -> no guess

    def test_detail_day_times(self):
        by_day = south.parse_day_times(fx("south_detail_vary.html"))
        self.assertEqual(by_day[4], ["19:00", "21:30"])  # Friday
        self.assertEqual(by_day[6], ["18:00", "20:30"])  # Sunday


class Mann(unittest.TestCase):
    def test_list(self):
        urls = mann.parse_list(fx("mann_list.html"))
        self.assertIn("https://highmarkmann.org/events/2027-04-24/fontaines-dc", urls)

    def test_detail(self):
        recs = mann.parse_detail(fx("mann_detail.html"), "https://highmarkmann.org/events/2027-04-24/fontaines-dc")
        check_shape(self, recs)
        r = recs[0]
        self.assertEqual((r["date"], r["show_time"], r["doors_time"]), ("2027-04-24", "19:00", "18:00"))
        self.assertEqual(r["room"], "Skyline Stage")
        self.assertIn("ticketmaster.com", r["ticket_url"])


class Sellersville(unittest.TestCase):
    def test_cards(self):
        recs = sellersville.parse(fx("sellersville_p1.html"), TODAY)
        check_shape(self, recs)
        self.assertGreaterEqual(len(recs), 5)
        r = next(r for r in recs if "70's Show" in r["title"])
        self.assertEqual((r["date"], r["show_time"], r["doors_time"]), ("2026-11-08", "14:00", "13:30"))
        self.assertIn("etix.com", r["ticket_url"])


class Parx(unittest.TestCase):
    def test_json(self):
        recs = parx.parse(json.loads(fx("parx_days_p1.json")))
        check_shape(self, recs)
        self.assertTrue(recs)
        self.assertFalse(any("Drawing" in r["title"] for r in recs))  # promotions filtered out
        self.assertTrue(any(r.get("room") == "Xcite Center" for r in recs))


class Dawson(unittest.TestCase):
    def test_table(self):
        recs = dawson.parse(fx("dawson.html"), TODAY)
        check_shape(self, recs)
        self.assertEqual(recs[0]["title"], "Seth Aaron & John Gilbride")
        self.assertEqual(recs[0]["date"], "2026-11-13")
        self.assertIsNone(recs[0]["show_time"])  # never invented
        five = [r for r in recs if r["show_time"] == "17:00"]
        self.assertTrue(five and "Slowey" in five[0]["title"] and "5pm" not in five[0]["title"])

    def test_layout_change_raises(self):
        with self.assertRaises(RuntimeError):
            dawson.parse("<html><body>redesigned</body></html>", TODAY)


class Queen(unittest.TestCase):
    def test_sitemap(self):
        self.assertGreater(len(queen.parse_sitemap(fx("queen_sitemap.xml"))), 10)

    def test_detail(self):
        recs = queen.parse_detail(fx("queen_detail.html"), "https://thequeenwilmington.com/events/sonic-command/", TODAY)
        check_shape(self, recs)
        r = recs[0]
        self.assertEqual((r["date"], r["show_time"], r["doors_time"]), ("2026-12-05", "20:00", "19:00"))
        self.assertEqual(r["room"], "The Crown")


class TicketmasterDiscovery(unittest.TestCase):
    def test_parse(self):
        recs = livenation_tm.parse(json.loads(fx("tm_events.json")), "The Met Philadelphia")
        check_shape(self, recs)
        self.assertEqual((recs[0]["show_time"], recs[0]["doors_time"]), ("20:00", "19:00"))
        self.assertEqual(recs[0]["subtitle"], "Emma Ogier")
        self.assertIsNone(recs[1]["show_time"])  # TBA stays unknown


if __name__ == "__main__":
    unittest.main()
