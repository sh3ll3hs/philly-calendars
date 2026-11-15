"""Parks on Tap reader against a saved, trimmed copy of /locations (no network)."""
import datetime as dt
import importlib
import os
import re
import unittest
from zoneinfo import ZoneInfo

R = importlib.import_module("combined_readers.parksontap")

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "combined_parksontap.html")
SRC = {"id": "parksontap", "name": "Parks on Tap", "method": "custom", "reader": "parksontap",
       "url": "https://www.parksontap.com/locations"}
COLUMBUS = "https://www.parksontap.com/locations/2024/9/25/columbus-square-park-sa7f3-mhcnf-p8g8b"


def D(*a):
    return dt.datetime(*a)


class ParksOnTap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIX, encoding="utf-8") as f:
            cls.body = f.read()
        cls.ev = R.parse(cls.body, SRC)

    def days(self, park):
        return [(e["start"], e["end"]) for e in self.ev if e["title"] == "Parks on Tap: " + park]

    def test_one_event_per_open_day_with_that_days_hours(self):
        # page: "Wed, Sep 30, 2026 4:00 PM - Sun, Oct 4, 2026 10:00 PM",
        # HOURS: WEDNESDAY - FRIDAY | 4 - 10PM, SATURDAY- SUNDAY | 12 - 10PM
        self.assertEqual(self.days("Stephen Girard Park"), [
            (D(2026, 9, 30, 16, 0), D(2026, 9, 30, 22, 0)),
            (D(2026, 10, 1, 16, 0), D(2026, 10, 1, 22, 0)),
            (D(2026, 10, 2, 16, 0), D(2026, 10, 2, 22, 0)),
            (D(2026, 10, 3, 12, 0), D(2026, 10, 3, 22, 0)),
            (D(2026, 10, 4, 12, 0), D(2026, 10, 4, 22, 0))])
        girard = [e for e in self.ev if e["title"] == "Parks on Tap: Stephen Girard Park"][0]
        self.assertFalse(girard["all_day"])
        self.assertEqual(girard["loc"], "Stephen Girard Park, Philadelphia, PA")
        self.assertEqual(girard["url"], "https://www.parksontap.com/locations/stephengirardpark-2r97h")
        self.assertIn("WEDNESDAY - FRIDAY | 4 - 10PM", girard["desc"])
        self.assertEqual(len(self.ev), 27)                       # 5 stops: 6 + 5 + 5 + 6 + 5 days

    def test_short_weekday_names(self):
        # "WED - FRI | 4 - 10PM / SAT - SUN | 12 - 10PM", Aug 12 to Aug 16
        self.assertEqual(self.days("Belmont Plateau")[0], (D(2026, 8, 12, 16, 0), D(2026, 8, 12, 22, 0)))
        self.assertEqual(self.days("Belmont Plateau")[-1], (D(2026, 8, 16, 12, 0), D(2026, 8, 16, 22, 0)))

    def test_holiday_monday_line(self):
        # Sep 2 to Sep 7, with "LABOR DAY, MONDAY 12 - 10PM"
        self.assertEqual(self.days("Penn Treaty")[-1], (D(2026, 9, 7, 12, 0), D(2026, 9, 7, 22, 0)))
        self.assertEqual(len(self.days("Penn Treaty")), 6)

    def test_last_day_without_stated_hours_is_all_day(self):
        # Oct 7 to Mon Oct 12 10:00 PM; the HOURS lines name Wednesday to Sunday only
        stops = [e for e in self.ev if e["title"] == "Parks on Tap: Columbus Square Park"]
        self.assertEqual([e["start"] for e in stops[:5]],
                         [D(2026, 10, 7, 16, 0), D(2026, 10, 8, 16, 0), D(2026, 10, 9, 16, 0),
                          D(2026, 10, 10, 12, 0), D(2026, 10, 11, 12, 0)])
        self.assertEqual((stops[5]["start"], stops[5]["end"], stops[5]["all_day"]), (dt.date(2026, 10, 12), None, True))
        self.assertTrue(all(e["url"] == COLUMBUS for e in stops))

    def test_odd_published_end_time_does_not_drop_sunday(self):
        # Cliveden Park is published as ending "Sun, Sep 27, 2026 4:00 AM"
        self.assertEqual(self.days("Cliveden Park")[-1], (D(2026, 9, 27, 12, 0), D(2026, 9, 27, 22, 0)))
        self.assertEqual(len(self.days("Cliveden Park")), 5)

    def test_shown_times_are_eastern(self):
        # the page's own "Google Calendar" link carries the same instants in UTC
        m = re.search(r"text=Columbus%20Square%20Park[^\"]*dates=(\d{8}T\d{6})Z/(\d{8}T\d{6})Z", self.body)
        ny = [dt.datetime.strptime(x, "%Y%m%dT%H%M%S").replace(tzinfo=dt.timezone.utc)
              .astimezone(ZoneInfo("America/New_York")).replace(tzinfo=None) for x in m.groups()]
        self.assertEqual(ny, [D(2026, 10, 7, 16, 0), D(2026, 10, 12, 22, 0)])     # "4:00 PM" and "10:00 PM" on the page

    def test_opening_hours(self):
        hours = R.opening_hours("<p><strong>HOURS:</strong></p><p>WED - FRI |<br>4 - 10PM<br>SAT - MON |<br>12 - 10PM</p>"
                                "<p><strong>ABOUT:</strong></p><p>Open since 5 - 9PM never mattered here.</p>")
        self.assertEqual(sorted(hours), [0, 2, 3, 4, 5, 6])
        self.assertEqual(hours[2], (dt.time(16, 0), dt.time(22, 0)))
        self.assertEqual(hours[0], (dt.time(12, 0), dt.time(22, 0)))
        self.assertEqual(R.opening_hours("<p>ABOUT: a park</p>"), {})

    def test_without_hours_the_stop_is_one_entry_as_published(self):
        body = re.sub(r"<strong>HOURS:</strong>", "<strong>NOTES:</strong>", self.body)
        ev = [e for e in R.parse(body, SRC) if e["title"] == "Parks on Tap: Stephen Girard Park"]
        self.assertEqual([(e["start"], e["end"]) for e in ev], [(D(2026, 9, 30, 16, 0), D(2026, 10, 4, 22, 0))])

    def test_read_keeps_the_window(self):
        real = R.C.get_text
        R.C.get_text = lambda url: self.body
        try:
            today = dt.date(2026, 10, 3)
            got = R.read(SRC, {"lo": today - dt.timedelta(days=3), "hi": today + dt.timedelta(days=120),
                               "today": today, "detail": {}})
            none = R.read(SRC, {"lo": dt.date(2026, 11, 12), "hi": dt.date(2027, 3, 15),
                                "today": dt.date(2026, 11, 15), "detail": {}})
        finally:
            R.C.get_text = real
        self.assertEqual(len(got), 5 + 6)                        # Stephen Girard Park (from Sep 30) and Columbus Square Park
        self.assertEqual(none, [])                               # off season: nothing upcoming


if __name__ == "__main__":
    unittest.main()
