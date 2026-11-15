"""Curtis Institute of Music reader against a trimmed real sample of its events API (no network).

The fixture is 14 of the ~1,350 items the API returned on 2026-11-15: ten from the current
season and four older ones that show the odd cases (no date, "12:00 a.m.", markup and an
HTML entity in the title)."""
import datetime as dt
import importlib
import os
import unittest

import combined_to_ics as C

R = importlib.import_module("combined_readers.curtis")
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "combined_curtis.json")
SRC = {"id": "curtis", "name": "Curtis Institute of Music", "method": "custom", "reader": "curtis",
       "url": "https://www.curtis.edu/wp-json/curtis/v1/events",
       "page": "https://www.curtis.edu/curtis-performances/calendar/"}
TODAY = dt.date(2026, 11, 15)
CTX = {"lo": TODAY - dt.timedelta(days=3), "hi": TODAY + dt.timedelta(days=120), "today": TODAY, "detail": {}}


def body():
    with open(FIX, encoding="utf-8") as f:
        return f.read()


class Curtis(unittest.TestCase):
    def setUp(self):
        self.events = R.parse(body(), SRC)
        self.by = {e["url"].rstrip("/").rsplit("/", 1)[-1]: e for e in self.events}

    def test_times_are_the_wall_times_the_site_prints(self):
        # event page: "Date Nov 13, 2026 / Time 7:30 p.m. / Location Curtis Institute of Music, Field Concert Hall"
        e = self.by["student-recital-2026-11-13"]
        self.assertEqual(e["start"], dt.datetime(2026, 11, 13, 19, 30))
        self.assertFalse(e["all_day"])
        self.assertIsNone(e["end"])
        self.assertEqual(e["loc"], "Curtis Institute of Music, Field Concert Hall")
        self.assertEqual(e["url"], "https://www.curtis.edu/event/student-recital-2026-11-13/")
        # cards on the site: "Mon — Nov 16 @ 7:30 p.m." and (Nov 13) "5:00 p.m."
        self.assertEqual(self.by["student-recital-2026-11-16"]["start"], dt.datetime(2026, 11, 16, 19, 30))
        self.assertEqual(self.by["student-recital-2026-11-13-5pm"]["start"], dt.datetime(2026, 11, 13, 17, 0))
        self.assertEqual(self.by["susannah-nov-19-2627"]["start"], dt.datetime(2026, 11, 19, 19, 0))

    def test_titles(self):
        # a programme-only recital title gets the site's category label
        self.assertEqual(self.by["student-recital-2026-11-13"]["title"], "Student Recital: Bowen, Prokofiev, and more")
        self.assertEqual(self.by["student-recital-2026-11-16"]["title"], "Student Recital: Bach, Brahms, and Schubert")
        # titles that already say what they are stay as published
        self.assertEqual(self.by["student-recital-2026-12-01"]["title"], "Poiesis Quartet Residency Recital")
        self.assertEqual(self.by["curtis-at-all-hallows-2026-11-14"]["title"], "Curtis at All Hallows: Daniel Carroll, organ")
        self.assertEqual(self.by["susannah-nov-19-2627"]["title"], "Susannah")
        # markup and entities are cleaned
        self.assertEqual(self.by["john-dowell-a-public-intimate-space"]["title"], "John Dowell: A Public Intimate Space")
        self.assertEqual(self.by["graduation-recital-zubin-hathi-timpani-percussion-2019-01-21"]["title"],
                         "Graduation Recital: Zubin Hathi, Timpani & Percussion")

    def test_label_can_be_switched_off(self):
        plain = R.parse(body(), dict(SRC, params={"label": False}))
        self.assertIn("Bach, Brahms, and Schubert", [e["title"] for e in plain])

    def test_locations_and_description(self):
        self.assertEqual(self.by["susannah-nov-19-2627"]["loc"], "Mainstage Theater, Philadelphia Film Center")
        self.assertEqual(self.by["curtis-at-all-hallows-2026-11-14"]["loc"], "All Hallows Episcopal Church")
        self.assertEqual(self.by["project-cso-2026-12-04"]["loc"], "YouTube")
        self.assertEqual(self.by["student-recital-2026-11-13"]["desc"], "Student Recital, Free, Livestream")

    def test_touring_dates_are_left_out_unless_asked_for(self):
        self.assertNotIn("curtis-on-tour-in-tryon-nc", self.by)
        kept = R.parse(body(), dict(SRC, params={"skip": []}))
        tour = [e for e in kept if e["title"] == "Curtis on Tour in Tryon, NC"]
        self.assertEqual(len(tour), 1)
        self.assertEqual(tour[0]["loc"], "Tryon Fine Arts Center")

    def test_midnight_means_no_time_and_undated_items_are_dropped(self):
        e = self.by["opera-ondemand-2021-01-22"]          # "12:00 a.m." in the data
        self.assertTrue(e["all_day"])
        self.assertEqual(e["start"], dt.date(2021, 1, 22))
        self.assertNotIn("spring-gala-2023", self.by)     # date: null
        self.assertEqual(len(self.events), 12)            # 14 items - 1 on tour - 1 undated

    def test_read_keeps_only_the_window(self):
        keep = C.get_text
        seen = []
        C.get_text = lambda url: seen.append(url) or body()
        try:
            got = R.read(SRC, CTX)
        finally:
            C.get_text = keep
        self.assertEqual(seen, ["https://www.curtis.edu/wp-json/curtis/v1/events"])      # one request
        self.assertEqual(len(got), 9)
        self.assertEqual(min(C.day_of(e) for e in got), dt.date(2026, 11, 13))
        self.assertEqual(max(C.day_of(e) for e in got), dt.date(2027, 3, 14))


if __name__ == "__main__":
    unittest.main()
