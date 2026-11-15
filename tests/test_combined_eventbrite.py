"""Eventbrite reader: search listing page and organizer page fixtures (real pages, trimmed)."""
import datetime as dt
import importlib
import json
import os
import unittest
from unittest import mock

R = importlib.import_module("combined_readers.eventbrite")
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SRC = {"id": "eventbrite", "name": "Eventbrite (free events in Philadelphia)", "method": "custom", "reader": "eventbrite",
       "url": "https://www.eventbrite.com/d/pa--philadelphia/free--events/", "pages": 5}
ORG = {"id": "eventbrite_peoplescinemaclub", "name": "People's Cinema Club", "method": "custom", "reader": "eventbrite",
       "url": "https://www.eventbrite.com/o/peoples-cinema-club-121566806278"}


def load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def without(body, title_start):
    """The listing fixture with one event record taken out (as if it fell off the listing)."""
    marker = "window.__SERVER_DATA__ = "
    i = body.index(marker) + len(marker)
    data, end = json.JSONDecoder().raw_decode(body, i)
    res = data["search_data"]["events"]["results"]
    data["search_data"]["events"]["results"] = [r for r in res if not r["name"].startswith(title_start)]
    assert len(data["search_data"]["events"]["results"]) == len(res) - 1
    return body[:i] + json.dumps(data) + body[end:]


class ListingPage(unittest.TestCase):
    def setUp(self):
        self.body = load("combined_eventbrite.html")
        self.events = {e["title"]: e for e in R.parse(self.body, SRC)}

    def test_only_philadelphia_events_are_kept(self):
        self.assertEqual(len(R.records(self.body)), 7)
        self.assertEqual(sorted(self.events), [
            "Advances in Microbiome Research: Host Communities to the Global Environment",
            "Nickel and Dimed, 25 Years Later",
            'SGDI "The Return" Popup shop',
            "Sankofa",
            "WXPN Philly Anthems LIVE",
        ])      # the Camden and Cherry Hill events of the same listing are dropped

    def test_start_end_and_location(self):
        e = self.events["Sankofa"]       # event page: "Tuesday, December 1 - 6:30 PM - 9 PM"
        self.assertEqual(e["start"], dt.datetime(2026, 12, 1, 18, 30))
        self.assertEqual(e["end"], dt.datetime(2026, 12, 1, 21, 0))
        self.assertFalse(e["all_day"])
        self.assertEqual(e["loc"], "Village of Industry & Art, 320 South Broad Street, Philadelphia, PA 19102")
        self.assertEqual(e["url"], "https://www.eventbrite.com/e/sankofa-tickets-2003796766068")
        self.assertEqual(e["key"], "2003796766068")
        e = self.events["Nickel and Dimed, 25 Years Later"]     # "Monday, November 16 - 5:30 PM - 7 PM"
        self.assertEqual((e["start"], e["end"]), (dt.datetime(2026, 11, 16, 17, 30), dt.datetime(2026, 11, 16, 19, 0)))
        self.assertEqual(e["loc"], "Public Trust, 4017 Walnut Street, Philadelphia, PA 19104")

    def test_two_day_event_keeps_its_own_end(self):
        e = self.events["Advances in Microbiome Research: Host Communities to the Global Environment"]
        self.assertEqual(e["start"], dt.datetime(2026, 12, 2, 8, 30))
        self.assertEqual(e["end"], dt.datetime(2026, 12, 3, 17, 0))
        self.assertEqual(e["loc"], "Biomedical Research Building (BRB), 421 Curie Boulevard, Philadelphia, PA 19104")

    def test_hidden_end_is_left_out(self):
        e = self.events["WXPN Philly Anthems LIVE"]             # event page: "Starts at 7:30 PM"
        self.assertEqual(e["start"], dt.datetime(2026, 12, 10, 19, 30))
        self.assertIsNone(e["end"])

    def test_venue_named_after_its_street_is_written_once(self):
        self.assertEqual(self.events["WXPN Philly Anthems LIVE"]["loc"], "3025 Walnut Street, Philadelphia, PA 19104")
        self.assertEqual(self.events['SGDI "The Return" Popup shop']["loc"], "2233 North 7th Street, Philadelphia, PA 19133")

    def test_links_carry_no_tracking_parameters(self):
        for e in self.events.values():
            self.assertRegex(e["url"], r"^https://www\.eventbrite\.com/e/[a-z0-9-]+-\d+$")

    def test_online_cancelled_and_hidden_date_events_are_dropped(self):
        for flag in ("is_online_event", "is_cancelled", "hide_start_date"):
            body = self.body.replace('"name":"Sankofa"', '"name":"Sankofa","%s":true' % flag, 1)
            self.assertNotEqual(body, self.body)
            body = body.replace('"%s":false,' % flag, "").replace('"%s":null,' % flag, "")
            titles = [e["title"] for e in R.parse(body, SRC)]
            self.assertNotIn("Sankofa", titles, flag)
            self.assertEqual(len(titles), 4, flag)

    def test_event_in_another_time_zone_is_converted(self):
        body = self.body.replace('"name":"Sankofa"', '"name":"Sankofa (Chicago clock)"', 1)
        i = body.index("Sankofa (Chicago clock)")
        j = body.index('"timezone":"America/New_York"', i)
        body = body[:j] + '"timezone":"America/Chicago"' + body[j + len('"timezone":"America/New_York"'):]
        e = {e["title"]: e for e in R.parse(body, SRC)}["Sankofa (Chicago clock)"]
        self.assertEqual(e["start"], dt.datetime(2026, 12, 1, 19, 30))      # 6:30 PM Central

    def test_date_without_a_time_is_all_day(self):
        self.assertEqual(R.when("2026-12-01", None, "America/New_York"), (dt.date(2026, 12, 1), True))
        self.assertEqual(R.when("2026-12-01", "18:30:00", "America/New_York"), (dt.datetime(2026, 12, 1, 18, 30), False))
        self.assertIsNone(R.when("soon", "18:30", "America/New_York"))

    def test_page_without_event_data_is_an_error(self):
        with self.assertRaises(ValueError):
            R.parse("<html><body>Just a moment...</body></html>", SRC)


class OrganizerPage(unittest.TestCase):
    def test_upcoming_events(self):
        ev = R.parse(load("combined_eventbrite_organizer.html"), ORG)
        self.assertEqual([e["title"] for e in ev], ["PHLAFF Presents: Family Friendly Film Block", "Sankofa", "Uncommitted"])
        self.assertEqual([e["start"] for e in ev], [dt.datetime(2026, 11, 17, 18, 30), dt.datetime(2026, 12, 1, 18, 30),
                                                    dt.datetime(2026, 12, 8, 18, 30)])
        # the organizer page repeats the start time as the end time: no end is given
        self.assertEqual([e["end"] for e in ev], [None, None, None])
        self.assertEqual(ev[0]["loc"], "Village of Industry & Art, 320 South Broad Street, Philadelphia, PA 19102")
        self.assertEqual(ev[2]["url"], "https://www.eventbrite.com/e/uncommitted-tickets-2003799601549")
        self.assertEqual(ev[0]["source"], "People's Cinema Club")

    def test_cancelled_event_and_weekly_series(self):
        body = load("combined_eventbrite_organizer2.html")       # HoneyTree EvilEye, 3 of its 12 records
        self.assertEqual([r["name"][:10] for r in R.records(body)], ["Hump(!) We", "Ritual VII", "BRRRlesque"])
        ev = R.parse(body, dict(ORG, id="eventbrite_honeytreeevileye", name="HoneyTree EvilEye"))
        # "BRRRlesque" carries the page's "Cancelled" badge (is_cancelled is false, event_sales_status says cancelled)
        self.assertEqual([e["title"] for e in ev], ["Hump(!) Wednesdays -free weekly burlesque show at 254",
                                                    "Ritual VIII: The Darkness"])
        # the weekly series is one record at its next date (card text: "Wednesday - 8:00 PM and 4 more")
        self.assertEqual(ev[0]["start"], dt.datetime(2026, 11, 18, 20, 0))
        self.assertEqual(ev[0]["loc"], "254, 254 South 12th Street, Philadelphia, PA 19107")
        self.assertEqual(ev[1]["start"], dt.datetime(2026, 12, 15, 20, 0))      # card text: "Tue, Dec 15 - 8:00 PM"
        self.assertEqual(ev[1]["loc"], "Doom, 421 North 7th Street, Philadelphia, PA 19123")

    def test_failed_event_lookup_is_an_error_not_an_empty_list(self):
        body = load("combined_eventbrite_organizer.html").replace('"upcomingEventsFailed":false', '"upcomingEventsFailed":true')
        with self.assertRaises(ValueError):
            R.parse(body, ORG)


class Read(unittest.TestCase):
    def ctx(self, day, detail):
        return {"lo": day - dt.timedelta(days=3), "hi": day + dt.timedelta(days=120), "today": day, "detail": detail}

    def test_at_most_five_requests(self):
        self.assertEqual(R.page_urls(SRC), [SRC["url"]] + [SRC["url"] + "?page=%d" % i for i in (2, 3, 4, 5)])
        self.assertEqual(len(R.page_urls(dict(SRC, pages=40))), 5)
        self.assertEqual(R.page_urls(ORG), [ORG["url"]])
        self.assertEqual(len(R.page_urls(dict(SRC, urls=[SRC["url"] + "?page=%d" % i for i in range(1, 9)]))), 5)
        seen = []
        with mock.patch.object(R.C, "get_text", side_effect=lambda u: seen.append(u) or load("combined_eventbrite.html")):
            ev = R.read(dict(SRC, pages=40), self.ctx(dt.date(2026, 11, 15), {}))
        self.assertEqual(len(seen), 5)
        self.assertEqual(len(ev), 5)                # the same events on every page are counted once

    def test_listing_event_is_remembered_for_a_week_after_it_drops_off(self):
        full = load("combined_eventbrite.html")
        short = without(full, "Sankofa")
        detail, src = {}, dict(SRC, pages=1)
        with mock.patch.object(R.C, "get_text", return_value=full):
            first = R.read(src, self.ctx(dt.date(2026, 11, 15), detail))
        self.assertEqual(len(first), 5)
        self.assertEqual(len(detail), 5)
        self.assertEqual(detail["https://www.eventbrite.com/e/sankofa-tickets-2003796766068"]["fetched"], "2026-11-15")
        with mock.patch.object(R.C, "get_text", return_value=short):
            later = R.read(src, self.ctx(dt.date(2026, 11, 18), detail))
            gone = R.read(src, self.ctx(dt.date(2026, 11, 23), detail))
        kept = {e["title"]: e for e in later}
        self.assertIn("Sankofa", kept)              # not on the listing any more, seen 3 days ago
        self.assertEqual(kept["Sankofa"]["start"], dt.datetime(2026, 12, 1, 18, 30))
        self.assertNotIn("Sankofa", [e["title"] for e in gone])     # last seen 8 days ago
        self.assertEqual(len([e for e in later if e["title"] == "Sankofa"]), 1)

    def test_remembered_event_that_has_started_is_not_returned(self):
        full = load("combined_eventbrite.html")
        detail, src = {}, dict(SRC, pages=1)
        with mock.patch.object(R.C, "get_text", return_value=full):
            R.read(src, self.ctx(dt.date(2026, 11, 15), detail))
        with mock.patch.object(R.C, "get_text", return_value=without(full, "Nickel and Dimed")):
            later = R.read(src, self.ctx(dt.date(2026, 11, 17), detail))
        self.assertNotIn("Nickel and Dimed, 25 Years Later", [e["title"] for e in later])    # it was on Nov 16

    def test_organizer_page_remembers_nothing(self):
        detail = {}
        with mock.patch.object(R.C, "get_text", return_value=load("combined_eventbrite_organizer.html")):
            ev = R.read(ORG, self.ctx(dt.date(2026, 11, 15), detail))
        self.assertEqual(len(ev), 3)
        self.assertEqual(detail, {})

    def test_later_page_failure_keeps_earlier_pages_and_first_page_failure_raises(self):
        pages = iter([load("combined_eventbrite.html"), "<html>oops</html>"])
        with mock.patch.object(R.C, "get_text", side_effect=lambda u: next(pages)):
            self.assertEqual(len(R.read(dict(SRC, pages=3), self.ctx(dt.date(2026, 11, 15), {}))), 5)
        with mock.patch.object(R.C, "get_text", return_value="<html>oops</html>"):
            with self.assertRaises(ValueError):
                R.read(SRC, self.ctx(dt.date(2026, 11, 15), {}))
        with mock.patch.object(R.C, "get_text", side_effect=R.C.http.BlockedError("403 from www.eventbrite.com")):
            with self.assertRaises(R.C.http.BlockedError):
                R.read(SRC, self.ctx(dt.date(2026, 11, 15), {}))


if __name__ == "__main__":
    unittest.main()
