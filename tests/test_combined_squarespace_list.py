"""Glen Foerd reader against a trimmed copy of its Squarespace events-list page (no network)."""
import datetime as dt
import importlib
import os
import unittest

R = importlib.import_module("combined_readers.squarespace_list")

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "combined_glenfoerd.html")
SRC = {"id": "glenfoerd", "name": "Glen Foerd", "method": "custom", "reader": "glenfoerd",
       "url": "https://www.glenfoerd.org/events"}
PLACE = "Glen Foerd, 5001 Grant Avenue Philadelphia, PA, 19114"


class GlenFoerd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIX, encoding="utf-8") as f:
            cls.body = f.read()
        cls.all = R.parse(cls.body, SRC)
        cls.ev = {e["title"]: e for e in cls.all}

    def test_every_listed_event_once(self):
        self.assertEqual(len(self.all), 12)               # 9 upcoming + the 3 past ones kept in the sample
        self.assertEqual(len(self.ev), 12)
        self.assertNotIn("(map)", self.ev)                # what the generic text reader made of this page

    def test_titles_dates_times_and_place(self):
        concert = self.ev["Fall Concert by Settlement Music School"]
        self.assertEqual(concert["start"], dt.datetime(2026, 11, 20, 19, 0))     # "Friday, November 20, 2026 7:00 PM"
        self.assertEqual(concert["end"], dt.datetime(2026, 11, 20, 20, 0))       # "8:00 PM"
        self.assertFalse(concert["all_day"])
        self.assertEqual(concert["loc"], PLACE)
        self.assertEqual(concert["url"], "https://www.glenfoerd.org/events/2026/11/20/free-concert")
        self.assertTrue(concert["desc"].startswith("Enjoy this free string ensemble concert"))
        tour = self.ev["Monthly Guided Tour"]
        self.assertEqual(tour["start"], dt.datetime(2026, 12, 6, 11, 0))
        self.assertEqual(tour["end"], dt.datetime(2026, 12, 6, 12, 30))
        solstice = self.ev["Winter Solstice Celebration"]
        self.assertEqual(solstice["start"], dt.datetime(2026, 12, 20, 15, 0))
        self.assertEqual(solstice["end"], dt.datetime(2026, 12, 20, 18, 0))
        self.assertEqual(solstice["loc"], PLACE)
        party = self.ev["Lily P.A.D.S. Holiday Pajama Party"]
        self.assertEqual((party["start"], party["end"]),
                         (dt.datetime(2026, 12, 16, 17, 0), dt.datetime(2026, 12, 16, 18, 30)))

    def test_noon_and_entities(self):
        past = self.ev["Second SUNDAY Guided Tour"]       # "11:00 AM" to "12:00 PM"
        self.assertEqual((past["start"], past["end"]),
                         (dt.datetime(2026, 11, 15, 11, 0), dt.datetime(2026, 11, 15, 12, 0)))
        self.assertIn("Entertain & Gather: A Holiday Tablescape Workshop", self.ev)   # &amp; decoded

    def test_run_that_ends_on_a_later_day(self):
        play = self.ev["EgoPo Presents “The Ways of White Folks” by Langston Hughes"]
        self.assertEqual(play["start"], dt.datetime(2027, 2, 10, 19, 0))         # "Wed, Feb 10, 2027 7:00 PM"
        self.assertEqual(play["end"], dt.datetime(2027, 2, 28, 14, 0))           # "Sun, Feb 28, 2027 2:00 PM"

    def test_date_without_a_clock_time_is_all_day(self):
        block = ('<article class="eventlist-event eventlist-event--upcoming">'
                 '<h1 class="eventlist-title"><a href="/events/2026/12/31/open-house" class="eventlist-title-link">Open House</a></h1>'
                 '<time class="event-date" datetime="2026-12-31">Thursday, December 31, 2026</time></article>')
        (e,) = R.parse(block, SRC)
        self.assertTrue(e["all_day"])
        self.assertEqual(e["start"], dt.date(2026, 12, 31))
        self.assertEqual(e["loc"], "")

    def test_read_makes_one_request(self):
        C, asked = R.C, []
        real = C.get_text
        C.get_text = lambda url: asked.append(url) or self.body
        try:
            ev = R.read(SRC, {"lo": dt.date(2026, 11, 12), "hi": dt.date(2027, 3, 15), "today": dt.date(2026, 11, 15),
                              "detail": {}})
        finally:
            C.get_text = real
        self.assertEqual(asked, ["https://www.glenfoerd.org/events"])
        self.assertEqual(len(ev), 12)


if __name__ == "__main__":
    unittest.main()
