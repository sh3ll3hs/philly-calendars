"""Navy Yard reader against trimmed copies of its two events-archive pages (no network)."""
import datetime as dt
import importlib
import os
import unittest

R = importlib.import_module("combined_readers.navyyard")

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SRC = {"id": "navyyard", "name": "Navy Yard", "method": "custom", "reader": "navyyard",
       "url": "https://navyyard.org/events/"}
TODAY = dt.date(2026, 11, 15)
PAGE2 = "https://navyyard.org/events/page/2/"


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def row(month, day):
    return {"month": month, "day": day}


class NavyYard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page1, cls.page2 = fixture("combined_navyyard.html"), fixture("combined_navyyard_page2.html")
        cls.first = R.parse(cls.page1, SRC, TODAY)

    def pick(self, events, title, day):
        (e,) = [e for e in events if e["title"] == title and R.C.day_of(e) == day]
        return e

    def test_titles_dates_times_and_places(self):
        self.assertEqual(len(self.first), 12)
        run = self.pick(self.first, "Navy Yard Running Club", dt.date(2026, 11, 17))
        self.assertEqual(run["start"], dt.datetime(2026, 11, 17, 17, 45))        # "Nov 17", "5:45 pm"
        self.assertIsNone(run["end"])                                             # no end on the card, none invented
        self.assertFalse(run["all_day"])
        self.assertEqual(run["loc"], "Meet at Vincera Institute, 12th & Constitution Avenue")
        self.assertEqual(run["url"], "https://navyyard.org/events/navy-yard-running-club-24/")
        self.assertTrue(run["desc"].startswith("The Navy Yard Running Club meets every Tuesday at 5:45"))
        flyers = self.pick(self.first, "Navy Yard Night @ the Flyers", dt.date(2026, 11, 17))
        self.assertEqual(flyers["start"], dt.datetime(2026, 11, 17, 19, 0))      # featured block: "11/17/2026 7:00 pm"
        self.assertEqual(flyers["loc"], "Xfinity Mobile Arena")
        pilates = self.pick(self.first, "Alchemy X Fitness – Mat Pilates", dt.date(2026, 11, 18))
        self.assertEqual((pilates["start"], pilates["end"]),                      # "5:30 pm — 6:30 pm"
                         (dt.datetime(2026, 11, 18, 17, 30), dt.datetime(2026, 11, 18, 18, 30)))
        self.assertEqual(pilates["loc"], "Alchemy X (Inside of Vincera Institute)")
        wobble = self.pick(self.first, "Greater Philadelphia YMCA Gobble Wobble Thanksgiving Day 5k", dt.date(2026, 11, 26))
        self.assertEqual(wobble["start"], dt.datetime(2026, 11, 26, 8, 30))
        self.assertEqual(wobble["loc"], "Marine Parade Grounds")

    def test_weekly_cards_stay_separate_events(self):
        runs = [e for e in self.first if e["title"] == "Navy Yard Running Club"]
        self.assertEqual([R.C.day_of(e) for e in runs],
                         [dt.date(2026, 11, 17), dt.date(2026, 11, 24), dt.date(2026, 12, 1), dt.date(2026, 12, 8)])
        self.assertEqual(len({e["key"] for e in runs}), 4)

    def test_event_already_under_way_is_dated_this_year(self):
        drive = self.pick(self.first, "Camp Out for Hunger Drive (10/14-11/18)", dt.date(2026, 10, 14))
        self.assertEqual(drive["start"], dt.datetime(2026, 10, 14, 12, 0))

    def test_year_rolls_over_across_pages(self):
        both = R.build(R.cards(self.page1) + R.cards(self.page2), SRC, TODAY)
        self.assertEqual(len(both), 22)
        sprint = self.pick(both, "Sandy Sprint 5K", dt.date(2027, 4, 24))         # after "Dec 30": next year
        self.assertEqual(sprint["start"], dt.datetime(2027, 4, 24, 7, 0))
        quizzo = self.pick(both, "Holiday Quizzo Night", dt.date(2026, 12, 17))
        self.assertEqual((quizzo["start"], quizzo["end"]),
                         (dt.datetime(2026, 12, 17, 16, 30), dt.datetime(2026, 12, 17, 18, 30)))
        self.assertEqual(quizzo["loc"], "Gatehouse, 4503 S. Broad Street")

    def test_year_rules(self):
        years = lambda rows, today: [d.year for d in R.assign_years(rows, today)]
        self.assertEqual(years([row(12, 29), row(1, 5), row(1, 12)], dt.date(2026, 12, 20)), [2026, 2027, 2027])
        self.assertEqual(years([row(1, 5), row(1, 12)], dt.date(2026, 12, 20)), [2027, 2027])       # nothing left this year
        self.assertEqual(years([row(1, 5), row(2, 2)], dt.date(2027, 1, 3)), [2027, 2027])
        self.assertEqual(years([row(6, 1), row(11, 17), row(11, 24)], TODAY), [2026, 2026, 2026])   # long-running first card
        self.assertEqual(years([row(11, 17), row(11, 12), row(11, 24)], TODAY), [2026, 2026, 2026]) # slightly out of order

    def test_card_without_a_time_is_all_day(self):
        card = ('<article class="col-12 card-event" id="post-1"><div class="card-event__date mb-0"><p class="mb-0">Dec</p>'
                '<p class="mb-0">05</p></div><p class="card-event__title mb-1">Holiday Market</p>'
                '<p class="card-event__location mb-0">Central Green</p>'
                '<a href="https://navyyard.org/events/holiday-market/" class="card-event__link"><span>Read More</span></a></article>')
        (e,) = R.parse(card, SRC, TODAY)
        self.assertTrue(e["all_day"])
        self.assertEqual(e["start"], dt.date(2026, 12, 5))
        self.assertEqual(e["loc"], "Central Green")

    def test_read_follows_the_next_link_and_stops(self):
        C, asked = R.C, []
        pages = {SRC["url"]: self.page1, PAGE2: self.page2}
        real = C.get_text
        C.get_text = lambda url: asked.append(url) or pages[url]
        try:
            ev = R.read(SRC, {"lo": TODAY - dt.timedelta(days=3), "hi": TODAY + dt.timedelta(days=120), "today": TODAY,
                              "detail": {}})
        finally:
            C.get_text = real
        self.assertEqual(asked, [SRC["url"], PAGE2])       # page 2 has no rel="next"
        self.assertEqual(len(ev), 22)


if __name__ == "__main__":
    unittest.main()
