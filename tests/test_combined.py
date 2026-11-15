"""Reader tests for combined_to_ics.py against small saved samples (no network)."""
import datetime as dt
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import combined_to_ics as C  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
TODAY = dt.date(2026, 11, 15)
CTX = {"lo": TODAY - dt.timedelta(days=3), "hi": TODAY + dt.timedelta(days=120), "today": TODAY, "detail": {}}


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8", newline="") as f:
        return f.read()


class Readers(unittest.TestCase):
    def setUp(self):
        self._text, self._json = C.get_text, C.get_json

    def tearDown(self):
        C.get_text, C.get_json = self._text, self._json

    def serve(self, name):
        body = fixture(name)
        C.get_text = lambda url: body
        C.get_json = lambda url: json.loads(body)

    def test_squarespace_converts_epoch_to_local_time(self):
        self.serve("combined_squarespace.json")
        src = {"id": "jet", "name": "Jet Wine Bar", "url": "https://www.jetwinebar.com/events"}
        ev = C.read_squarespace(src, CTX)
        self.assertEqual(len(ev), 1)                      # the undated item is dropped
        e = ev[0]
        self.assertEqual(e["title"], "Wine Class: Bubbles & Bites")
        self.assertEqual(e["start"], dt.datetime(2026, 11, 20, 19, 0))   # 1795219200000 ms = Nov 21 00:00 UTC = 7 PM Eastern
        self.assertEqual(e["end"], dt.datetime(2026, 11, 20, 21, 0))
        self.assertEqual(e["loc"], "Jet Wine Bar, 1525 South Street, Philadelphia, PA, 19146")
        self.assertEqual(e["url"], "https://www.jetwinebar.com/events/wine-class")

    def test_jsonld_times_dates_and_addresses(self):
        self.serve("combined_jsonld.html")
        src = {"id": "hoj", "name": "The Heart of Jazz", "url": "https://example.org/venue/time/"}
        ev = {e["title"]: e for e in C.read_jsonld(src, CTX)}
        self.assertEqual(set(ev), {"Jam Session – Midtown Jazz", "Holiday Market", "UTC stamped show"})
        jam = ev["Jam Session – Midtown Jazz"]
        self.assertEqual(jam["start"], dt.datetime(2026, 11, 21, 20, 0))
        self.assertEqual(jam["loc"], "Time Restaurant, 1315 Sansom St, Philadelphia, PA 19107")
        self.assertEqual(jam["url"], "https://example.org/event/jam-session/")
        self.assertEqual(jam["desc"], "Open jam, all welcome.")
        market = ev["Holiday Market"]
        self.assertTrue(market["all_day"])                # a date with no time stays a date
        self.assertEqual(market["start"], dt.date(2026, 12, 5))
        self.assertEqual(ev["UTC stamped show"]["start"], dt.datetime(2026, 11, 21, 19, 30))   # 00:30Z = 7:30 PM the day before

    def test_wix_skips_unscheduled_and_converts_utc(self):
        self.serve("combined_wix.html")
        src = {"id": "attic", "name": "Attic Brewing", "url": "https://www.atticbrewing.com/events"}
        ev = C.read_wix(src, CTX)
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["start"], dt.datetime(2026, 11, 15, 13, 0))
        self.assertEqual(ev[0]["end"], dt.datetime(2026, 11, 15, 17, 0))
        self.assertEqual(ev[0]["loc"], "Attic Brewing Company, 137 Berkley St, Philadelphia, PA 19144")
        self.assertEqual(ev[0]["url"], "https://www.atticbrewing.com/event-details/pearls-pale-ale-release")

    def test_spothopper_never_invents_a_time(self):
        self.serve("combined_spothopper.json")
        src = {"id": "bar", "name": "Some Bar", "url": "https://www.spothopperapp.com/api/spots/1/events",
               "page": "https://somebar.com/events", "venue": "Some Bar"}
        ev = {e["title"]: e for e in C.read_spothopper(src, CTX)}
        self.assertEqual(set(ev), {"Sunday Football Specials", "Holiday Party"})      # hidden template dropped
        self.assertEqual(ev["Sunday Football Specials"]["start"], dt.datetime(2026, 11, 22, 13, 0))
        self.assertEqual(ev["Sunday Football Specials"]["end"], dt.datetime(2026, 11, 22, 20, 0))
        self.assertTrue(ev["Holiday Party"]["all_day"])                                # no start time given
        self.assertEqual(ev["Holiday Party"]["loc"], "Some Bar")
        self.assertEqual(ev["Holiday Party"]["url"], "https://somebar.com/events")

    def test_ics_keeps_rules_and_drops_alarms(self):
        self.serve("combined.ics")
        src = {"id": "bok", "name": "Bok", "url": "https://example.org/feed.ics", "venue": "Bok"}
        ev = {e["title"]: e for e in C.read_ics(src, CTX)}
        self.assertEqual(set(ev), {"Movie Club, free screening", "Weekly Open Studio"})   # cancelled + long-past dropped
        movie = ev["Movie Club, free screening"]
        self.assertEqual(movie["start"], dt.datetime(2026, 11, 19, 19, 0))               # for de-duplication only
        self.assertFalse(any("VALARM" in l or "reminder" in l for l in movie["raw"]))
        self.assertTrue(any(l.startswith("RRULE:") for l in ev["Weekly Open Studio"]["raw"]))
        out = C.build_ics(C.tidy(list(ev.values()), CTX["lo"], CTX["hi"]))
        self.assertIn("RRULE:FREQ=WEEKLY;BYDAY=TU", out)
        self.assertIn("LOCATION:Bok", out)                                              # empty location filled from the source
        self.assertEqual(out.count("BEGIN:VEVENT"), 2)
        self.assertNotIn("BEGIN:VALARM", out)

    def test_text_reader_uses_only_stated_times(self):
        src = {"id": "gallery", "name": "A Gallery", "url": "https://gallery.example/events"}
        ev = {e["title"]: e for e in C.text_events(src, fixture("combined_text.html"), src["url"], TODAY, CTX["hi"])}
        self.assertEqual(set(ev), {"Collage Night", "Holiday Artist Sale"})              # nav, footer and 2025 ignored
        self.assertEqual(ev["Collage Night"]["start"], dt.datetime(2026, 11, 19, 18, 30))
        self.assertEqual(ev["Collage Night"]["end"], dt.datetime(2026, 11, 19, 20, 30))
        self.assertEqual(ev["Collage Night"]["url"], "https://gallery.example/events/collage-night")
        self.assertTrue(ev["Holiday Artist Sale"]["all_day"])
        self.assertEqual(ev["Holiday Artist Sale"]["start"], dt.date(2026, 12, 5))


class Merge(unittest.TestCase):
    def ev(self, src, title, start, **kw):
        return {"src": src, "key": f"{title}{start}", "title": title, "start": start, "end": None,
                "all_day": not isinstance(start, dt.datetime), "loc": kw.get("loc", ""), "url": "https://x.example/e",
                "desc": "", "source": src}

    def test_same_event_from_two_sources_is_written_once(self):
        a = self.ev("venue", "Trivia Night!", dt.datetime(2026, 11, 20, 19, 0))
        b = self.ev("district", "trivia night", dt.datetime(2026, 11, 20, 19, 0), loc="Some Bar, 1 Main St")
        out = C.tidy([a, b], CTX["lo"], CTX["hi"])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["loc"], "Some Bar, 1 Main St")        # the fuller location is kept

    def test_nightly_run_becomes_one_entry(self):
        run = [self.ev("museum", "Light Show", dt.datetime(2026, 11, 20, 18, 0) + dt.timedelta(days=i)) for i in range(12)]
        out = C.tidy(run, CTX["lo"], CTX["hi"])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["title"], "Light Show (daily through Dec 1)")

    def test_output_is_valid_looking_icalendar(self):
        e = self.ev("venue", "A, B; C", dt.datetime(2026, 11, 20, 19, 0), loc="Hall, 1 Main St, Philadelphia, PA 19100")
        e["desc"] = "Line one\nLine two " + "x" * 200
        out = C.build_ics([e])
        self.assertTrue(out.startswith("BEGIN:VCALENDAR\r\n") and out.endswith("END:VCALENDAR\r\n"))
        self.assertIn("DTSTART;TZID=America/New_York:20261120T190000", out)
        self.assertIn("DTEND;TZID=America/New_York:20261120T210000", out)          # 2 h default when no end given
        self.assertIn("SUMMARY:A\\, B\\; C", out)
        self.assertTrue(all(len(l.encode()) <= 75 for l in out.split("\r\n")))    # folded lines


if __name__ == "__main__":
    unittest.main()
