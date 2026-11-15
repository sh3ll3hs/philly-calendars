"""The Rotunda reader against saved copies of two month pages (no network)."""
import datetime as dt
import importlib
import os
import unittest

R = importlib.import_module("combined_readers.therotunda")

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SRC = {"id": "therotunda", "name": "The Rotunda", "method": "custom", "reader": "therotunda",
       "url": "https://www.therotunda.org/events"}
HALL = "The Rotunda, 4014 Walnut St, Philadelphia, PA 19104"


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


class TheRotunda(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nov = fixture("combined_therotunda.html")            # /events on 2026-11-15
        cls.dec = fixture("combined_therotunda_next.html")       # /events?date=2026-12-15
        cls.ev = R.parse(cls.nov, SRC)
        cls.by_key = {e["key"]: e for e in cls.ev}

    def test_month_and_next_link(self):
        self.assertEqual(R.month_of(self.nov), (2026, 11))
        self.assertEqual(R.next_month_url(self.nov, SRC["url"]), "https://www.therotunda.org/events?date=2026-12-15")
        self.assertEqual(R.month_of(self.dec), (2026, 12))
        self.assertEqual(R.next_month_url(self.dec, SRC["url"]), "https://www.therotunda.org/events?date=2027-01-15")

    def test_titles_dates_times_location(self):
        self.assertEqual(len(self.ev), 29)
        party = self.by_key["eventData_3684"]                    # Sun Nov 15, "12:00 PM -  4:00 PM"
        self.assertEqual(party["title"], "FLATstrap Launch Party")
        self.assertEqual(party["start"], dt.datetime(2026, 11, 15, 12, 0))
        self.assertEqual(party["end"], dt.datetime(2026, 11, 15, 16, 0))
        self.assertFalse(party["all_day"])
        self.assertEqual(party["loc"], HALL)
        self.assertEqual(party["url"], "https://www.therotunda.org/event/flatstrap-launch-party")
        vogue = self.by_key["eventData_3654"]                    # Mon Nov 16, "6:00 PM -  8:30 PM"
        self.assertEqual(vogue["title"], "Comm University Vogue Commentating Class")
        self.assertEqual(vogue["start"], dt.datetime(2026, 11, 16, 18, 0))
        self.assertEqual(vogue["end"], dt.datetime(2026, 11, 16, 20, 30))
        # the site's own link states the same wall time
        self.assertTrue(vogue["url"].endswith("-2026-11-16-18-00-00-0500"))
        veldt = self.by_key["eventData_3687"]                    # Sat Nov 21, "7:00 PM - 11:00 PM"
        self.assertEqual(veldt["title"], "The Veldt w/ Noun and Sun Within")
        self.assertEqual((veldt["start"], veldt["end"]),
                         (dt.datetime(2026, 11, 21, 19, 0), dt.datetime(2026, 11, 21, 23, 0)))
        self.assertIn("The Veldt coming up from North Carolina", veldt["desc"])

    def test_two_events_on_one_day(self):
        day = sorted((e["start"], e["title"]) for e in self.ev if e["start"].date() == dt.date(2026, 11, 29))
        self.assertEqual(day, [
            (dt.datetime(2026, 11, 29, 11, 0),
             "Animal ACTivists of Philly Holiday Bizarre and Indoor Flea Market featuring KRAMPUS"),
            (dt.datetime(2026, 11, 29, 17, 0), "Vegan Potluck open to all")])

    def test_prefixes(self):
        self.assertFalse([e["title"] for e in self.ev if "in-person!" in e["title"].lower()])
        sold_out = self.by_key["eventData_3594"]
        self.assertEqual(sold_out["title"], "SOLD OUT!!!! Fire Museum Presents: Ak'chamel and Ecology: HomeStones")
        online = self.by_key["eventData_3708"]                   # "Online! The Game Show Game Show", Nov 21
        self.assertEqual(online["title"], "The Game Show Game Show (online)")
        self.assertEqual(online["loc"], "Online")
        self.assertEqual(online["start"], dt.datetime(2026, 11, 21, 15, 0))
        self.assertEqual(online["end"], dt.datetime(2026, 11, 21, 16, 0))

    def test_cells_of_other_months_are_skipped(self):
        # the November grid ends with December 1-5 and the December grid starts with November 29-30
        self.assertEqual({e["start"].month for e in self.ev}, {11})
        dec = R.parse(self.dec, SRC)
        self.assertEqual([(e["title"], e["start"], e["end"]) for e in dec], [
            ("Bowerbird pres. Water Can Assume Any Form Matthew Levy, tenor saxophone and electronics",
             dt.datetime(2026, 12, 4, 20, 0), dt.datetime(2026, 12, 4, 21, 30)),
            ("Trans Art Mart", dt.datetime(2026, 12, 5, 11, 0), dt.datetime(2026, 12, 5, 17, 0)),
            ("Trans Art Mart", dt.datetime(2026, 12, 6, 11, 0), dt.datetime(2026, 12, 6, 17, 0)),
            ("Philadelphia Science Fiction Society (PSFS) meeting and guest speaker Paul Halpern",
             dt.datetime(2026, 12, 11, 20, 0), dt.datetime(2026, 12, 11, 21, 0))])
        self.assertTrue(all(e["loc"] == HALL for e in dec))

    def _read(self, pages, **extra):
        asked, real = [], R.C.get_text
        R.C.get_text = lambda url: (asked.append(url), pages[url])[1]
        try:
            today = dt.date(2026, 11, 15)
            got = R.read(dict(SRC, **extra), {"lo": today - dt.timedelta(days=3), "hi": today + dt.timedelta(days=120),
                                              "today": today, "detail": {}})
        finally:
            R.C.get_text = real
        return asked, got

    def test_stops_after_an_empty_month(self):
        empty = ('<h2 id="currentMonth">January 2027</h2><a id="nextMonth" href="/events?date=2027-02-15">February 2027</a>'
                 '<table class="calendar"><tr><td><div class="header"><span class="day">1</span></div></td></tr></table>')
        pages = {"https://www.therotunda.org/events": self.nov,
                 "https://www.therotunda.org/events?date=2026-12-15": self.dec,
                 "https://www.therotunda.org/events?date=2027-01-15": empty}
        asked, got = self._read(pages)                           # February is never asked for
        self.assertEqual(asked, list(pages))
        self.assertEqual(len(got), 29 + 4)

    def test_month_cap(self):
        pages = {"https://www.therotunda.org/events": self.nov,
                 "https://www.therotunda.org/events?date=2026-12-15": self.dec}
        asked, got = self._read(pages, months=2)
        self.assertEqual(asked, list(pages))
        self.assertEqual(len(got), 29 + 4)


if __name__ == "__main__":
    unittest.main()
