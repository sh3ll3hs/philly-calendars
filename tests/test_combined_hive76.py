"""Hive76 reader against a trimmed real sample of the site's Eventbrite feed JSON (no network).

The fixture is the first three of the eight events the feed returned on 2026-11-15, with
the image, ticket and organizer-description blocks cut away."""
import datetime as dt
import importlib
import json
import os
import re
import unittest

import combined_to_ics as C

R = importlib.import_module("combined_readers.hive76")
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "combined_hive76.json")
SRC = {"id": "hive76", "name": "Hive76", "method": "custom", "reader": "hive76",
       "url": "https://www.hive76.org/wp-json/event-feed-for-eventbrite/v1/feed/7402",
       "page": "https://www.hive76.org/classes/"}


def body():
    with open(FIX, encoding="utf-8") as f:
        return f.read()


class Hive76(unittest.TestCase):
    def setUp(self):
        self.events = R.parse(body(), SRC)

    def test_titles_dates_and_times(self):
        self.assertEqual([e["title"] for e in self.events], ["Hive76 Open House"] * 3)
        self.assertEqual([e["start"] for e in self.events],
                         [dt.datetime(2026, 11, 15, 14, 30), dt.datetime(2026, 11, 22, 14, 30), dt.datetime(2026, 11, 29, 14, 30)])
        self.assertEqual(self.events[0]["end"], dt.datetime(2026, 11, 15, 17, 0))
        self.assertFalse(any(e["all_day"] for e in self.events))

    def test_times_equal_the_text_the_page_prints(self):
        # the plugin prints vue.start ("November 15, 2026 @ 2:30 pm") and vue.end ("5:00 pm")
        for raw, e in zip(json.loads(body())["events"], self.events):
            m = re.match(r"(\w+) (\d+), (\d{4}) @ (\d+):(\d+) (am|pm)", raw["vue"]["start"])
            shown = dt.datetime.strptime(" ".join(m.groups()), "%B %d %Y %I %M %p")
            self.assertEqual(e["start"], shown)
            self.assertEqual(e["end"].strftime("%-I:%M %p").lower(), raw["vue"]["end"])

    def test_location_and_link(self):
        e = self.events[0]
        self.assertEqual(e["loc"], "Hive76, 1821 East Hagert Street #100c, Philadelphia, PA 19125")
        self.assertEqual(e["url"], "https://www.eventbrite.com/e/hive76-open-house-tickets-1981528082837")
        self.assertTrue(e["desc"].startswith("Take a tour of Hive76's makerspace"))
        self.assertEqual(len({e["key"] for e in self.events}), 3)

    def test_cancelled_undated_and_online_items(self):
        base = json.loads(body())["events"][0]
        cancelled = dict(base, ID="1", status="canceled")
        undated = dict(base, ID="2", start={})
        online = dict(base, ID="3", online_event=True, post_title="Intro to KiCad")
        local_only = dict(base, ID="4", start={"local": "2026-12-01T19:00:00"}, end={}, post_title="Laser Class")
        got = R.parse(json.dumps({"events": [cancelled, undated, online, local_only]}), SRC)
        self.assertEqual([(e["title"], e["loc"]) for e in got],
                         [("Intro to KiCad", "Online"),
                          ("Laser Class", "Hive76, 1821 East Hagert Street #100c, Philadelphia, PA 19125")])
        self.assertEqual(got[1]["start"], dt.datetime(2026, 12, 1, 19, 0))
        self.assertIsNone(got[1]["end"])

    def test_read_makes_one_request(self):
        keep, seen = C.get_text, []
        C.get_text = lambda url: seen.append(url) or body()
        try:
            got = R.read(SRC, {})
        finally:
            C.get_text = keep
        self.assertEqual(seen, [SRC["url"]])
        self.assertEqual(len(got), 3)


if __name__ == "__main__":
    unittest.main()
