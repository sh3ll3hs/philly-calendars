"""Bob & Barbara's reader against a saved, trimmed copy of /events (no network)."""
import datetime as dt
import importlib
import os
import unittest

R = importlib.import_module("combined_readers.bobandbarbaras")

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "combined_bobandbarbaras.html")
SRC = {"id": "bobandbarbaras", "name": "Bob & Barbara's Lounge", "method": "custom", "reader": "bobandbarbaras",
       "url": "https://www.bobandbarbaras.com/events",
       "venue": "Bob & Barbara's Lounge, 1509 South St, Philadelphia, PA 19146"}
TODAY = dt.date(2026, 11, 15)             # the day the page was saved (a Sunday)


def D(*a):
    return dt.datetime(*a)


class BobAndBarbaras(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIX, encoding="utf-8") as f:
            cls.body = f.read()
        cls.ev = R.parse(cls.body, SRC, TODAY)

    def when(self, title):
        return sorted(((e["start"], e["end"]) for e in self.ev if e["title"] == title), key=lambda p: str(p[0]))

    def test_written_dates_with_the_sections_hours(self):
        # "Monday: shakasounds ... from 8 - 11 pm", then "November 16" and "December 21"
        self.assertEqual(self.when("ShakaSounds")[0], (D(2026, 11, 16, 20, 0), D(2026, 11, 16, 23, 0)))
        self.assertIn((D(2026, 12, 21, 20, 0), D(2026, 12, 21, 23, 0)), self.when("ShakaSounds"))
        # "Mikey Mester and Friends ... EVERY 3rd WEDNESDAY of the month from 9 pm - 12 am", "November 18", "December 16"
        self.assertEqual(self.when("Mikey Mester and Friends"),
                         [(D(2026, 11, 18, 21, 0), D(2026, 11, 19, 0, 0)), (D(2026, 12, 16, 21, 0), D(2026, 12, 17, 0, 0))])
        # "dual identity ... 9 pm - 12 am NO COVER!", "November 4", "December 2"
        self.assertEqual(self.when("Dual Identity"),
                         [(D(2026, 11, 4, 21, 0), D(2026, 11, 5, 0, 0)), (D(2026, 12, 2, 21, 0), D(2026, 12, 3, 0, 0))])
        mikey = [e for e in self.ev if e["title"] == "Mikey Mester and Friends"][0]
        self.assertFalse(mikey["all_day"])
        self.assertEqual(mikey["loc"], "Bob & Barbara's Lounge, 1509 South St, Philadelphia, PA 19146")
        self.assertEqual(mikey["url"], "https://www.bobandbarbaras.com/events")

    def test_written_dates_without_a_time_are_all_day(self):
        # neither section states an hour, so none is given
        jj = [e for e in self.ev if e["title"] == "Jason Jeffries and The Tall Trees"]
        self.assertEqual([(e["start"], e["all_day"]) for e in jj], [(dt.date(2026, 11, 3), True), (dt.date(2026, 12, 1), True)])
        eq = [e for e in self.ev if e["title"] == "June’s EQ"]
        self.assertEqual([(e["start"], e["all_day"]) for e in eq], [(dt.date(2026, 11, 24), True), (dt.date(2026, 12, 29), True)])

    def test_drag_show_times_tickets_and_closed_night(self):
        # "Two shows, 7:30 pm and 9:30 pm"; under each date the page links "7:30" and "9:30"
        shows = [e for e in self.ev if e["title"] == "Miss Lisa Lisa’s Drag Show"]
        self.assertEqual(sorted(e["start"] for e in shows), [
            D(2026, 11, 5, 19, 30), D(2026, 11, 5, 21, 30), D(2026, 11, 12, 19, 30), D(2026, 11, 12, 21, 30),
            D(2026, 11, 19, 19, 30), D(2026, 11, 19, 21, 30), D(2026, 12, 3, 19, 30), D(2026, 12, 3, 21, 30)])
        days = {e["start"].date() if isinstance(e["start"], dt.datetime) else e["start"] for e in self.ev}
        self.assertNotIn(dt.date(2026, 11, 26), days)                # "November 26 CLOSED - Thanksgiving"
        late = [e for e in shows if e["start"] == D(2026, 11, 19, 21, 30)][0]
        self.assertEqual(late["url"], "https://www.eventbrite.com/e/2004328559677?aff=oddtdtcreator")
        self.assertIsNone(late["end"])                               # the page gives no end for a show

    def test_standing_nights_for_six_weeks(self):
        # "Friday: The Crowd pleasers ... EVERY FRIDAY NIGHT / 9 pm - 1 am"
        fridays = self.when("The Crowd Pleasers")
        self.assertEqual([s for s, _ in fridays], [D(2026, 11, 20, 21, 0), D(2026, 11, 27, 21, 0), D(2026, 12, 4, 21, 0),
                                                   D(2026, 12, 11, 21, 0), D(2026, 12, 18, 21, 0), D(2026, 12, 25, 21, 0)])
        self.assertEqual(fridays[0][1], D(2026, 11, 21, 1, 0))
        # "Saturday: tHe 3 Notes ... EVERY SATURDAY NIGHT / 9 pm - 1 am"
        self.assertEqual(self.when("The 3 Notes")[0], (D(2026, 11, 21, 21, 0), D(2026, 11, 22, 1, 0)))
        # "Sunday: karaoke ... EVERY SUNDAY / 9 pm - 2 am" (the page was saved on a Sunday)
        self.assertEqual(self.when("Karaoke")[0], (D(2026, 11, 15, 21, 0), D(2026, 11, 16, 2, 0)))
        self.assertEqual(len(self.when("Karaoke")), 7)
        note = [e for e in self.ev if e["title"] == "The Crowd Pleasers"][0]["desc"]
        self.assertIn("standing night", note)
        self.assertIn("NO COVER!", note)
        last = max(e["start"] for e in self.ev if isinstance(e["start"], dt.datetime))
        self.assertEqual(last, D(2026, 12, 27, 21, 0))               # six weeks from Nov 15, the last Sunday

    def test_wednesday_jam_gives_way_to_the_named_host(self):
        # "Every WEDNESDAY ... jam session ... 9 pm - 12 am"; Nov 18, Dec 2, 9, 16 are listed by name
        self.assertEqual([s for s, _ in self.when("Wednesday Jam Session")], [D(2026, 11, 25, 21, 0), D(2026, 12, 23, 21, 0)])
        self.assertEqual(self.when("Judd Nielsen Organ Trio"),
                         [(D(2026, 11, 11, 21, 0), D(2026, 11, 12, 0, 0)), (D(2026, 12, 9, 21, 0), D(2026, 12, 10, 0, 0))])

    def test_monthly_night_stated_in_passing(self):
        # "You can also hear him every 1st Saturday of the Month from 5 - 9 pm"
        self.assertIn((D(2026, 12, 5, 17, 0), D(2026, 12, 5, 21, 0)), self.when("ShakaSounds"))
        self.assertEqual(len(self.when("ShakaSounds")), 3)

    def test_totals_and_weeks_setting(self):
        self.assertEqual(len(self.ev), 42)
        # one week ahead: the 20 dated entries plus Fri Nov 20, Sat Nov 21 and Sun Nov 15 and 22
        self.assertEqual(len(R.parse(self.body, dict(SRC, weeks=1), TODAY)), 24)

    def test_bare_time_without_am_pm_gives_no_time(self):
        body = self.body.replace("Two shows, 7:30 pm and 9:30 pm.", "Two shows.")
        shows = [e for e in R.parse(body, SRC, TODAY) if e["title"] == "Miss Lisa Lisa’s Drag Show"]
        self.assertEqual([(e["start"], e["all_day"]) for e in shows],
                         [(dt.date(2026, 11, 5), True), (dt.date(2026, 11, 12), True), (dt.date(2026, 11, 19), True),
                          (dt.date(2026, 12, 3), True)])

    def test_stale_date_is_dropped_not_moved_to_next_year(self):
        body = self.body.replace(">December 21<", ">March 16<")
        days = [s for s, _ in self.when_in(R.parse(body, SRC, TODAY), "ShakaSounds")]
        self.assertEqual(days, [D(2026, 11, 16, 20, 0), D(2026, 12, 5, 17, 0)])

    @staticmethod
    def when_in(events, title):
        return sorted(((e["start"], e["end"]) for e in events if e["title"] == title), key=lambda p: str(p[0]))


if __name__ == "__main__":
    unittest.main()
