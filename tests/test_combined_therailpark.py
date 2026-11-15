"""Rail Park reader against a trimmed copy of the site's Gatsby page data (no network)."""
import datetime as dt
import importlib
import json
import os
import unittest

R = importlib.import_module("combined_readers.therailpark")

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "combined_therailpark.json")
SRC = {"id": "therailpark", "name": "The Rail Park", "method": "custom", "reader": "therailpark",
       "url": "https://www.therailpark.org/news-and-events/"}


def made_up(**data):
    """Page data holding one invented event, for the repeat rules no published event uses yet."""
    base = {"title": "Weekly Walk", "start": "2026-10-22T21:30:00+0000", "end": "2026-10-22T23:00:00+0000",
            "all_day": False, "cost": None, "tags": [], "recurring_event": True, "frequency": "Weekly",
            "interval": None, "recurring_end": "2026-11-19", "excluded_dates": [{"date": None}], "location": []}
    base.update(data)
    node = {"id": "made-up", "url": "/event/weekly-walk/", "lang": "en-us", "type": "event", "data": base}
    return {"result": {"data": {"allPrismicEvent": {"edges": [{"node": node}]}}}}


class RailPark(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIX, encoding="utf-8") as f:
            cls.body = f.read()
        cls.ev = {e["title"]: e for e in R.parse(cls.body, SRC)}

    def test_data_url(self):
        self.assertEqual(R.data_url(SRC["url"]), "https://www.therailpark.org/page-data/news-and-events/page-data.json")

    def test_utc_instants_become_philadelphia_time(self):
        self.assertEqual(len(self.ev), 7)
        yappy = self.ev["October Yappy Hour"]
        self.assertEqual(yappy["start"], dt.datetime(2026, 10, 29, 17, 30))      # 21:30Z, daylight time
        self.assertEqual(yappy["end"], dt.datetime(2026, 10, 29, 19, 0))
        self.assertFalse(yappy["all_day"])
        self.assertEqual(yappy["loc"], "The Rail Park, 1300 Block of Noble Street")
        self.assertEqual(yappy["url"], "https://www.therailpark.org/event/yappy-hour-october-2026/")
        self.assertEqual(yappy["desc"], "Arts & Culture, On the Park\nFree")
        tour = self.ev["Tour the Rail Park!"]
        self.assertEqual(tour["start"], dt.datetime(2026, 11, 14, 10, 0))        # 15:00Z, standard time
        self.assertEqual(tour["end"], dt.datetime(2026, 11, 14, 12, 0))
        self.assertEqual(tour["desc"], "Tours\n$20")
        self.assertEqual(tour["loc"], "")                                         # none entered, none invented

    def test_all_day_flag_wins_over_clock_times(self):
        love = self.ev["Love Your Park"]
        self.assertTrue(love["all_day"])
        self.assertEqual(love["start"], dt.date(2026, 11, 14))
        self.assertIsNone(love["end"])
        self.assertEqual(love["loc"], "The Rail Park")
        survey = self.ev["Community Engagement Survey"]                           # 05:00Z Mar 8 to 03:59Z Mar 21
        self.assertEqual((survey["start"], survey["end"]), (dt.date(2024, 3, 8), dt.date(2024, 3, 20)))

    def test_repeat_fields_ignored_unless_flagged_and_bad_end_dropped(self):
        titles = [e["title"] for e in R.parse(self.body, SRC)]
        self.assertEqual(titles.count("Community Engagement Survey"), 1)          # "Weekly" set but recurring_event false
        party = self.ev["Block Party"]
        self.assertEqual(party["start"], dt.datetime(2022, 6, 11, 14, 0))
        self.assertIsNone(party["end"])                                           # the site's end is before its start

    def test_weekly_repeat_keeps_local_time_and_skips_excluded_dates(self):
        ev = R.parse(made_up(excluded_dates=[{"date": "2026-11-05"}]), SRC)
        self.assertEqual([e["start"] for e in ev],
                         [dt.datetime(2026, 10, 22, 17, 30), dt.datetime(2026, 10, 29, 17, 30),
                          dt.datetime(2026, 11, 12, 17, 30), dt.datetime(2026, 11, 19, 17, 30)])   # clocks change Nov 1
        self.assertEqual(ev[0]["end"], dt.datetime(2026, 10, 22, 19, 0))
        self.assertEqual(len({e["key"] for e in ev}), 4)

    def test_repeat_end_is_counted_in_utc_like_the_site(self):
        ev = R.parse(made_up(start="2026-12-04T00:00:00+0000", end="2026-12-04T02:00:00+0000",
                             recurring_end="2026-12-17"), SRC)
        self.assertEqual([e["start"] for e in ev],                                # 7 PM Thursdays; Dec 17 is Dec 18 in UTC
                         [dt.datetime(2026, 12, 3, 19, 0), dt.datetime(2026, 12, 10, 19, 0)])

    def test_monthly_repeat_skips_months_without_the_day_and_no_end_means_once(self):
        ev = R.parse(made_up(start="2026-12-31T17:00:00+0000", end="2026-12-31T18:00:00+0000", frequency="Monthly",
                             recurring_end="2027-03-31"), SRC)
        self.assertEqual([e["start"].date() for e in ev],
                         [dt.date(2026, 12, 31), dt.date(2027, 1, 31), dt.date(2027, 3, 31)])
        once = R.parse(made_up(recurring_end=None), SRC)
        self.assertEqual([e["start"] for e in once], [dt.datetime(2026, 10, 22, 17, 30)])

    def test_read_asks_for_the_page_data(self):
        C, asked = R.C, []
        real = C.get_json
        C.get_json = lambda url: asked.append(url) or json.loads(self.body)
        try:
            ev = R.read(SRC, {"lo": dt.date(2026, 11, 12), "hi": dt.date(2027, 3, 15), "today": dt.date(2026, 11, 15),
                              "detail": {}})
        finally:
            C.get_json = real
        self.assertEqual(asked, ["https://www.therailpark.org/page-data/news-and-events/page-data.json"])
        self.assertEqual(len(ev), 7)


if __name__ == "__main__":
    unittest.main()
