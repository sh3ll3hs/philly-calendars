"""ICA Philadelphia reader against a trimmed real copy of its calendar page (no network).

The fixture is https://icaphila.org/calendar/ as served on 2026-11-15 with the header,
menus, footer and scripts cut away: the "On View" exhibitions, the three "Upcoming
Events" rows and the page's script template (which also contains an `event-date` block)."""
import datetime as dt
import importlib
import os
import unittest

import combined_to_ics as C

R = importlib.import_module("combined_readers.icaphila")
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "combined_icaphila.html")
VENUE = "Institute of Contemporary Art, 118 S. 36th Street, Philadelphia, PA 19104"
SRC = {"id": "icaphila", "name": "Institute of Contemporary Art", "method": "custom", "reader": "icaphila",
       "url": "https://icaphila.org/calendar/", "venue": VENUE}


def body():
    with open(FIX, encoding="utf-8") as f:
        return f.read()


class Ica(unittest.TestCase):
    def setUp(self):
        self.events = R.parse(body(), SRC)

    def test_only_the_three_event_rows_are_read(self):
        # five exhibitions "Through Feb 21, 2027" and the script template are not events
        self.assertEqual([e["title"] for e in self.events], [
            "Sachs Lecture in Contemporary Art History | Shivani Shedde: “Militant Assemblies: "
            "Architecture and the Art of Afro-Asian Negotiation",
            "2026-2027 Visiting Artist Lecture Series: Elle Pérez",
            "Performance | Wilmer Wilson IV: Skirl (III)",
        ])
        self.assertFalse(any("Through" in e["title"] or "{{" in e["title"] for e in self.events))

    def test_dates_and_times_as_printed(self):
        # "Wed, Dec 2, 2026, 6PM–8PM", "Thu, Dec 3, 2026, 6PM–8PM", "Sat, Dec 5, 2026, 11AM–6PM"
        self.assertEqual([(e["start"], e["end"]) for e in self.events], [
            (dt.datetime(2026, 12, 2, 18, 0), dt.datetime(2026, 12, 2, 20, 0)),
            (dt.datetime(2026, 12, 3, 18, 0), dt.datetime(2026, 12, 3, 20, 0)),
            (dt.datetime(2026, 12, 5, 11, 0), dt.datetime(2026, 12, 5, 18, 0)),
        ])
        self.assertFalse(any(e["all_day"] for e in self.events))

    def test_location_link_and_kind(self):
        e = self.events[1]
        self.assertEqual(e["loc"], VENUE)                 # the page prints no place; the entry's venue is used
        self.assertEqual(e["url"], "https://icaphila.org/events/programs/2026-27-visiting-artist-lecture-series-elle-perez/")
        self.assertEqual(e["desc"], "Artist Talk")
        self.assertEqual(self.events[2]["desc"], "")      # the performance row has no type
        self.assertEqual(self.events[2]["url"], "https://icaphila.org/events/performance-wilmer-wilson-iv-skirl-iii/")

    def test_when_reads_only_what_is_written(self):
        self.assertEqual(R.when("Wed, Dec 2, 2026, 6PM–8PM"),
                         (dt.datetime(2026, 12, 2, 18, 0), dt.datetime(2026, 12, 2, 20, 0), False))
        self.assertEqual(R.when("Thu, Jan 14, 2027, 6:30PM"), (dt.datetime(2027, 1, 14, 18, 30), None, False))
        self.assertEqual(R.when("Sat, Dec 5, 2026"), (dt.date(2026, 12, 5), None, True))          # no time: all-day
        self.assertEqual(R.when("Fri, Oct 16 – Sun, Oct 18, 2026, 11AM–6PM"),
                         (dt.date(2026, 10, 16), dt.date(2026, 10, 18), True))                    # a run: no time taken
        self.assertIsNone(R.when("Wed, Dec 2, 6PM–8PM"))                                          # no year: not guessed
        self.assertIsNone(R.when("Open today, 11AM–6PM."))
        self.assertIsNone(R.when("Feb 30, 2027, 6PM"))

    def test_a_filled_location_block_and_a_relative_link(self):
        row = ('<div class="event-date font-regular"><span class="upcoming">Thu, Jan 14, 2027, 6PM–7:30PM</span></div>'
               '<a href="/events/off-site-talk/" class="black-text title">Off-site Talk &amp; Tour</a>'
               '<ul class="clean-ul event_types"><li><a href="/calendar/lecture">Lecture</a></li>'
               '<li><a href="/calendar/members">Members</a></li></ul>'
               '<div class="font-small locations">Meyerson Hall, 210 S. 34th Street</div>')
        (e,) = R.parse(row + row, SRC)                     # the same row twice is one event
        self.assertEqual(e["title"], "Off-site Talk & Tour")
        self.assertEqual((e["start"], e["end"]), (dt.datetime(2027, 1, 14, 18, 0), dt.datetime(2027, 1, 14, 19, 30)))
        self.assertEqual(e["loc"], "Meyerson Hall, 210 S. 34th Street")
        self.assertEqual(e["url"], "https://icaphila.org/events/off-site-talk/")
        self.assertEqual(e["desc"], "Lecture, Members")

    def test_read_makes_one_request(self):
        keep, seen = C.get_text, []
        C.get_text = lambda url: seen.append(url) or body()
        try:
            got = R.read(SRC, {})
        finally:
            C.get_text = keep
        self.assertEqual(seen, ["https://icaphila.org/calendar/"])
        self.assertEqual(len(got), 3)


if __name__ == "__main__":
    unittest.main()
