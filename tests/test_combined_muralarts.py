"""Mural Arts reader against saved copies of the listing and two event pages (no network)."""
import datetime as dt
import importlib
import os
import unittest

R = importlib.import_module("combined_readers.muralarts")

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SRC = {"id": "muralarts", "name": "Mural Arts Philadelphia", "method": "custom", "reader": "muralarts",
       "url": "https://muralarts.org/events/"}
PAINT = "https://muralarts.org/events/community-paint-day-philadelphia-stars-negro-league-baseball-mural/"
KNIT = "https://muralarts.org/events/tacony-labs-third-annual-knit-a-thon/"


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


class MuralArts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.listing = fixture("combined_muralarts.html")                  # /events/ on 2026-11-15
        cls.paint_page = fixture("combined_muralarts_event.html")         # one evening, with times
        cls.knit_page = fixture("combined_muralarts_event_days.html")     # two days, no time shown
        cls.ev = {e["title"]: e for e in R.parse(cls.listing, SRC)}

    def test_listing_titles_dates_and_start_times(self):
        self.assertEqual(len(self.ev), 11)
        paint = self.ev["Philadelphia Stars Community Paint Day"]         # "11/17/2026", "6:00 pm"
        self.assertEqual(paint["start"], dt.datetime(2026, 11, 17, 18, 0))
        self.assertIsNone(paint["end"])                                    # the listing has no end time
        self.assertFalse(paint["all_day"])
        self.assertEqual(paint["url"], PAINT)
        self.assertEqual(paint["key"], "27629")
        self.assertEqual(paint["loc"], "")                                 # and no place
        sale = self.ev["Defender Association Art Sale"]                    # "12/10/2026", "4:00 pm"
        self.assertEqual(sale["start"], dt.datetime(2026, 12, 10, 16, 0))
        just_us = self.ev["Restorative Justice Month at City Hall: Just Us Exhibition & Reception"]
        self.assertEqual(just_us["start"], dt.datetime(2026, 11, 19, 10, 0))
        dedication = self.ev["“Then and Now and All Around” Dedication"]
        self.assertEqual(dedication["start"], dt.datetime(2026, 11, 20, 10, 0))

    def test_listing_without_a_time_is_all_day(self):
        tilt = self.ev["Eco-Social Realism Open House at TILT"]            # "time": ""
        self.assertEqual((tilt["start"], tilt["end"], tilt["all_day"]), (dt.date(2026, 11, 14), None, True))
        knit = self.ev["Tacony Lab’s Third Annual KNIT-A-THON"]            # 11/14 to 11/15: a range is never timed
        self.assertEqual((knit["start"], knit["end"], knit["all_day"]),
                         (dt.date(2026, 11, 14), dt.date(2026, 11, 15), True))

    def test_event_page_gives_end_time_and_place(self):
        info = R.parse_detail(self.paint_page)       # page shows "November 17, 2026 / 6:00 PM - 8:00 PM"
        self.assertEqual(info["start"], dt.datetime(2026, 11, 17, 18, 0))
        self.assertEqual(info["end"], dt.datetime(2026, 11, 17, 20, 0))
        self.assertFalse(info["all_day"])
        self.assertEqual(info["loc"], "1101 N 38th St, Philadelphia, PA 19104")
        self.assertTrue(info["desc"].startswith("Cost: Free\n\nCome help paint the new Philadelphia Stars"))
        self.assertIn("6:00 PM - 8:00 PM", self.paint_page)                # the visible text agrees with the link
        e = {x["title"]: x for x in R.parse(self.listing, SRC, {PAINT: info})}["Philadelphia Stars Community Paint Day"]
        self.assertEqual((e["start"], e["end"]), (dt.datetime(2026, 11, 17, 18, 0), dt.datetime(2026, 11, 17, 20, 0)))
        self.assertEqual(e["loc"], "1101 N 38th St, Philadelphia, PA 19104")

    def test_event_page_without_a_time_is_all_day(self):
        info = R.parse_detail(self.knit_page)        # page shows "November 14 - 15, 2026"; link 20261114/20261116
        self.assertEqual((info["start"], info["end"], info["all_day"]),
                         (dt.date(2026, 11, 14), dt.date(2026, 11, 15), True))
        self.assertEqual(info["loc"], "Tacony LAB Community Arts Center, 6918 Torresdale Avenue, Philadelphia, PA, USA")
        e = {x["title"]: x for x in R.parse(self.listing, SRC, {KNIT: info})}["Tacony Lab’s Third Annual KNIT-A-THON"]
        self.assertTrue(e["all_day"])
        self.assertEqual(e["loc"], info["loc"])

    def test_stale_event_page_is_not_trusted_for_times(self):
        # a cached page from before a reschedule: other day -> listing date and time win
        old = dict(R.parse_detail(self.paint_page), start=dt.datetime(2026, 11, 10, 18, 0), end=dt.datetime(2026, 11, 10, 20, 0))
        e = {x["title"]: x for x in R.parse(self.listing, SRC, {PAINT: old})}["Philadelphia Stars Community Paint Day"]
        self.assertEqual((e["start"], e["end"]), (dt.datetime(2026, 11, 17, 18, 0), None))

    def test_city_is_added_only_when_asked_and_missing(self):
        self.assertEqual(R._with_city("1441 Sansom Street", "Philadelphia, PA"), "1441 Sansom Street, Philadelphia, PA")
        self.assertEqual(R._with_city("2024 Reed Street 19146", "Philadelphia, PA"), "2024 Reed Street 19146, Philadelphia, PA")
        for full in ("1101 N 38th St, Philadelphia, PA 19104", "Philadelphia City Hall, 1400 John F. Kennedy Blvd",
                     "520 Market St, Camden, NJ 08102", "Online", ""):
            self.assertEqual(R._with_city(full, "Philadelphia, PA"), full)
        self.assertEqual(R._with_city("1441 Sansom Street", None), "1441 Sansom Street")
        info = dict(R.parse_detail(self.paint_page), loc="1441 Sansom Street")
        src = dict(SRC, city="Philadelphia, PA")
        e = {x["title"]: x for x in R.parse(self.listing, src, {PAINT: info})}["Philadelphia Stars Community Paint Day"]
        self.assertEqual(e["loc"], "1441 Sansom Street, Philadelphia, PA")

    def test_utc_and_other_zone_links(self):
        page = self.paint_page.replace("20261117T180000%2F20261117T200000", "20261117T230000Z%2F20261118T010000Z")
        info = R.parse_detail(page)
        self.assertEqual((info["start"], info["end"]), (dt.datetime(2026, 11, 17, 18, 0), dt.datetime(2026, 11, 17, 20, 0)))
        page = self.paint_page.replace("ctz=America%2FNew_York", "ctz=America%2FChicago")
        self.assertEqual(R.parse_detail(page)["start"], dt.datetime(2026, 11, 17, 19, 0))

    def test_read_opens_each_event_page_once_and_caches(self):
        pages = {SRC["url"]: self.listing, PAINT: self.paint_page, KNIT: self.knit_page}
        asked, real_get, real_sleep = [], R.C.get_text, R.time.sleep
        R.C.get_text = lambda url: (asked.append(url), pages.get(url, "<html></html>"))[1]
        R.time.sleep = lambda s: None
        try:
            today = dt.date(2026, 11, 15)
            ctx = {"lo": today - dt.timedelta(days=3), "hi": today + dt.timedelta(days=120), "today": today, "detail": {}}
            first = R.read(SRC, ctx)
            n_first = len(asked)
            second = R.read(SRC, ctx)
        finally:
            R.C.get_text, R.time.sleep = real_get, real_sleep
        # 11 listed; 2 ended before the window (Nov 5 and 6); listing + 9 event pages, then listing only
        self.assertEqual(n_first, 1 + 9)
        self.assertEqual(len(asked), n_first + 1)
        self.assertEqual(len(first), 11)
        by = {e["title"]: e for e in second}
        self.assertEqual(by["Philadelphia Stars Community Paint Day"]["end"], dt.datetime(2026, 11, 17, 20, 0))
        self.assertEqual(by["Philadelphia Stars Community Paint Day"]["loc"], "1101 N 38th St, Philadelphia, PA 19104")
        # a page with no calendar link leaves the listing's own date and time
        self.assertEqual(by["Defender Association Art Sale"]["start"], dt.datetime(2026, 12, 10, 16, 0))
        self.assertIn(PAINT, ctx["detail"])
        self.assertEqual(ctx["detail"][PAINT]["fetched"], "2026-11-15")


if __name__ == "__main__":
    unittest.main()
