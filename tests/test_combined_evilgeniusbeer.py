"""Evil Genius Beer reader against a trimmed copy of its calendar page (no network)."""
import datetime as dt
import importlib
import os
import unittest

R = importlib.import_module("combined_readers.evilgeniusbeer")

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "combined_evilgeniusbeer.html")
SRC = {"id": "evilgeniusbeer", "name": "Evil Genius Beer Company", "method": "custom", "reader": "evilgeniusbeer",
       "url": "https://evilgeniusbeer.com/calendar/",
       "lab_venue": "Evil Genius Beer Company, 1727 N Front St, Philadelphia, PA 19122"}
TODAY = dt.date(2026, 11, 15)
LAB = "Evil Genius Beer Company, 1727 N Front St, Philadelphia, PA 19122"


def item(section, weekday, date, name, time):
    return (f'<h2 class="eg-events__cat-name">{section}</h2><div class="eg-events__event-item">'
            f'<span class="eg-events__event-item-weekday">{weekday}</span><span class="eg-events__event-item-date">{date}</span>'
            f'<h3 class="eg-events__event-item-name">{name}</h3><span class="eg-events__event-item-time">{time}</span></div>')


class EvilGenius(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIX, encoding="utf-8") as f:
            cls.body = f.read()
        cls.all = R.parse(cls.body, SRC, TODAY)
        cls.ev = {e["title"]: e for e in cls.all}

    def test_titles_dates_times_and_place(self):
        self.assertEqual(len(self.all), 12)
        brunch = self.ev["May The Brunch Be Ever In Your Favor"]
        self.assertEqual(brunch["start"], dt.datetime(2026, 11, 15, 11, 0))      # "Sunday 11/15", "11:00 AM - 2:00 PM"
        self.assertEqual(brunch["end"], dt.datetime(2026, 11, 15, 14, 0))
        self.assertFalse(brunch["all_day"])
        self.assertEqual(brunch["loc"], LAB)                                      # listed under "Events At The Lab"
        self.assertEqual(brunch["url"], "https://evilgeniusbeer.com/calendar/")
        self.assertTrue(brunch["desc"].startswith("Hunger Games Drag Brunch!"))
        karaoke = self.ev["Live Band Karaoke"]
        self.assertEqual((karaoke["start"], karaoke["end"]),                      # "Friday 11/20", "8:00 PM - 11:00 PM"
                         (dt.datetime(2026, 11, 20, 20, 0), dt.datetime(2026, 11, 20, 23, 0)))
        talk = self.ev["Skip the Small Talk"]
        self.assertEqual((talk["start"], talk["end"]),
                         (dt.datetime(2026, 11, 17, 19, 0), dt.datetime(2026, 11, 17, 21, 0)))
        party = self.ev["Steelers Vs. Eagles Watch Party"]
        self.assertEqual((party["start"], party["end"]),
                         (dt.datetime(2026, 11, 22, 16, 0), dt.datetime(2026, 11, 22, 19, 30)))

    def test_year_comes_from_the_weekday(self):
        self.assertEqual(self.ev["Drag Me to 2027: A NYE Drag Brunch"]["start"], dt.datetime(2026, 12, 31, 11, 0))   # Thursday 12/31
        self.assertEqual(self.ev["PowerPop Girls Drag Brunch"]["start"], dt.datetime(2027, 1, 10, 11, 0))            # Sunday 1/10
        self.assertEqual(self.ev["Backwoods Barbie Brunch"]["start"], dt.datetime(2027, 1, 31, 11, 0))               # Sunday 1/31
        self.assertEqual(R.day_for("Sunday", 11, 15, dt.date(2027, 1, 2)), dt.date(2026, 11, 15))   # still 2026 after New Year
        self.assertEqual(R.day_for("", 12, 5, TODAY), dt.date(2026, 12, 5))                         # no weekday: next such date
        self.assertEqual(R.day_for("", 2, 5, TODAY), dt.date(2027, 2, 5))

    def test_backwards_time_range_is_not_guessed(self):
        spice = self.ev["Spice Up Your Drag Brunch!"]                             # the page prints "11:00 PM - 2:00 PM"
        self.assertTrue(spice["all_day"])
        self.assertEqual(spice["start"], dt.date(2026, 11, 22))
        self.assertTrue(spice["desc"].startswith("Time as printed on the site: 11:00 PM - 2:00 PM"))

    def test_range_past_midnight_ends_next_day(self):
        (e,) = R.parse(item("Events At The Lab", "Saturday", "12/ 5", "Late Show", "9:00 PM - 1:00 AM"), SRC, TODAY)
        self.assertEqual((e["start"], e["end"]), (dt.datetime(2026, 12, 5, 21, 0), dt.datetime(2026, 12, 6, 1, 0)))

    def test_other_sections_get_no_brewery_address(self):
        (e,) = R.parse(item("Samplings", "Friday", "11/ 20", "Tasting at a Bottle Shop", "5:00 PM - 7:00 PM"), SRC, TODAY)
        self.assertEqual(e["loc"], "")
        self.assertEqual(e["desc"], "Samplings")
        self.assertEqual(e["start"], dt.datetime(2026, 11, 20, 17, 0))
        with_venue = dict(SRC, venue="should not be used")                        # even if the entry had a fallback venue
        (e,) = R.parse(item("Festivals", "Saturday", "12/ 5", "Beer Fest", ""), with_venue, TODAY)
        self.assertEqual(e["loc"], "")
        self.assertTrue(e["all_day"])                                             # no time printed

    def test_read_makes_one_request(self):
        C, asked = R.C, []
        real = C.get_text
        C.get_text = lambda url: asked.append(url) or self.body
        try:
            ev = R.read(SRC, {"lo": TODAY - dt.timedelta(days=3), "hi": TODAY + dt.timedelta(days=120), "today": TODAY,
                              "detail": {}})
        finally:
            C.get_text = real
        self.assertEqual(asked, ["https://evilgeniusbeer.com/calendar/"])
        self.assertEqual(len(ev), 12)


if __name__ == "__main__":
    unittest.main()
