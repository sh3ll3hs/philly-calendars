"""Philadelphia Museum of Art reader against saved copies of the events sitemap and two event pages (no network)."""
import datetime as dt
import importlib
import os
import unittest

R = importlib.import_module("combined_readers.philamuseum")

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SRC = {"id": "philamuseum", "name": "Philadelphia Museum of Art", "method": "custom", "reader": "philamuseum",
       "url": "https://www.philamuseum.org/sitemap-events.xml", "page": "https://www.philamuseum.org/events"}
BASE = "https://www.philamuseum.org/events/"
RODIN, JAZZ, ALTER = BASE + "exhibition-tour-rodins-hands", BASE + "friday-holiday-jazz-market-edition", BASE + "alter-ego-family-festival"
TODAY = dt.date(2026, 11, 15)


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def D(*a):
    return dt.datetime(*a)


class PhilaMuseum(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sitemap = fixture("combined_philamuseum_sitemap.xml")
        cls.rodin = fixture("combined_philamuseum.html")           # a daily tour: 23 of its occurrences kept
        cls.jazz = fixture("combined_philamuseum_event.html")      # a single evening in the Main Building

    def test_sitemap(self):
        pages = R.parse_sitemap(self.sitemap)
        self.assertEqual(len(pages), 6)                             # the /events index itself is not an event page
        self.assertEqual(pages[0], (ALTER, "2026-11-13T19:14:47Z"))  # most recently changed first
        self.assertEqual(pages[1], (JAZZ, "2026-11-12T18:47:01Z"))
        self.assertEqual(pages[2], (RODIN, "2026-11-04T15:04:30Z"))
        self.assertEqual(pages[-1][1], "2026-01-30T17:12:13Z")

    def test_occurrences_titles_times_location(self):
        ev = R.parse(self.rodin, SRC)
        self.assertEqual(len(ev), 23)
        self.assertEqual({e["title"] for e in ev}, {"Exhibition Tour: Rodin’s Hands"})
        by = {e["start"]: e for e in ev}
        today = by[D(2026, 11, 15, 13, 0)]          # the page shows "Sunday, November 15, 2026 / 1:00 pm - 2:00 pm"
        self.assertIn("<p>Sunday, November 15, 2026</p><p>1:00 pm - 2:00 pm</p>", self.rodin)
        self.assertEqual(today["end"], D(2026, 11, 15, 14, 0))
        self.assertFalse(today["all_day"])
        self.assertEqual(today["loc"], "Rodin Museum (Main Gallery), 2151 Benjamin Franklin Parkway, Philadelphia, PA 19130")
        self.assertEqual(today["url"], RODIN + "?start=2026-11-15T18:00:00.000Z&end=2026-11-15T19:00:00.000Z")
        self.assertTrue(today["desc"].startswith("Tours\n\nEnjoy a guided tour of The Rodin Museum."))
        # 17:00Z before the clocks changed on Nov 1 and 18:00Z after are both 1:00 pm in Philadelphia
        self.assertIn(D(2026, 10, 31, 13, 0), by)
        self.assertEqual(by[D(2026, 10, 31, 13, 0)]["url"], RODIN + "?start=2026-10-31T17:00:00.000Z&end=2026-10-31T18:00:00.000Z")
        self.assertIn(D(2026, 11, 6, 13, 0), by)
        self.assertIn(D(2026, 3, 1, 13, 0), by)                    # past occurrences are returned too; read() drops them

    def test_single_evening_in_the_main_building(self):
        ev = R.parse(self.jazz, SRC)                # the page shows "Fri, Dec 11, 2026 5:00 pm" / "Fri, Dec 11, 2026 8:30 pm"
        self.assertEqual(len(ev), 1)
        e = ev[0]
        self.assertEqual(e["title"], "Friday Night: Holiday Jazz & Artist Market")
        self.assertEqual((e["start"], e["end"]), (D(2026, 12, 11, 17, 0), D(2026, 12, 11, 20, 30)))
        self.assertEqual(e["loc"], "Philadelphia Museum of Art (Main Building, Multiple locations), "
                                   "2600 Benjamin Franklin Parkway, Philadelphia, PA 19130")
        self.assertEqual(e["url"], JAZZ + "?start=2026-12-11T22:00:00.000Z&end=2026-12-12T01:30:00.000Z")
        self.assertIn("<p>Fri, Dec 11, 2026 5:00 pm</p><p>Fri, Dec 11, 2026 8:30 pm</p>", self.jazz)

    def test_cancelled_is_left_out(self):
        page = self.jazz.replace('\\"status\\":\\"active\\"', '\\"status\\":\\"cancelled\\"')
        self.assertNotEqual(page, self.jazz)
        self.assertEqual(R.parse(page, SRC), [])
        page = self.jazz.replace('\\"title\\":\\"Friday Night: Holiday Jazz', '\\"title\\":\\"Cancelled: Friday Night: Holiday Jazz')
        self.assertNotEqual(page, self.jazz)
        self.assertEqual(R.parse(page, SRC), [])

    def test_page_without_an_event_record(self):
        self.assertEqual(R.parse("<html><body><h1>Events</h1></body></html>", SRC), [])
        self.assertIsNone(R.event_record('<script>self.__next_f.push([1,"5:[\\"$\\",\\"x\\",null,{\\"page\\":{\\"events\\":null}}]\\n"])</script>'))

    def _run(self, ctx, sitemap=None, limit=None):
        pages = {SRC["url"]: sitemap or self.sitemap, RODIN: self.rodin, JAZZ: self.jazz}
        asked, real, cap = [], R.C.get_text, R.MAX_NEW_PAGES
        R.C.get_text = lambda url: (asked.append(url), pages.get(url, "<html></html>"))[1]
        if limit:
            R.MAX_NEW_PAGES = limit
        try:
            got = R.read(SRC, ctx)
        finally:
            R.C.get_text, R.MAX_NEW_PAGES = real, cap
        return asked, got

    def ctx(self, today=TODAY):
        return {"lo": today - dt.timedelta(days=3), "hi": today + dt.timedelta(days=120), "today": today, "detail": {}}

    def test_read_caches_pages_until_the_sitemap_says_they_changed(self):
        ctx = self.ctx()
        asked, got = self._run(ctx)
        self.assertEqual(asked[0], SRC["url"])
        self.assertEqual(asked[1:4], [ALTER, JAZZ, RODIN])          # newest first
        self.assertEqual(len(asked), 1 + 6)
        starts = sorted(e["start"] for e in got)
        self.assertEqual(starts[0], D(2026, 11, 13, 13, 0))         # nothing before the window (Nov 12)
        self.assertEqual(len(got), 12 + 1)                          # 12 tour dates from Nov 13 to 30, and the Dec 11 evening
        self.assertEqual(ctx["detail"][RODIN]["lastmod"], "2026-11-04T15:04:30Z")
        self.assertEqual(len(ctx["detail"][RODIN]["occ"]), 12)
        self.assertEqual(len(ctx["detail"][RODIN]["events"]), 1)    # one packed event, not one per date
        # next run, nothing changed: only the sitemap is asked for, and the same events come back
        ctx["today"] = TODAY + dt.timedelta(days=1)
        asked, again = self._run(ctx)
        self.assertEqual(asked, [SRC["url"]])
        self.assertEqual(sorted((e["start"], e["end"], e["title"], e["loc"], e["url"], e["key"]) for e in again),
                         sorted((e["start"], e["end"], e["title"], e["loc"], e["url"], e["key"]) for e in got))
        self.assertEqual(ctx["detail"][RODIN]["fetched"], "2026-11-16")     # confirmed today, so the script keeps it
        self.assertEqual(ctx["detail"][RODIN]["read"], "2026-11-15")
        # the sitemap reports a change to one page: only that page is read again
        changed = self.sitemap.replace("2026-11-04T15:04:30Z", "2026-11-16T09:00:00Z")
        asked, _ = self._run(ctx, changed)
        self.assertEqual(asked, [SRC["url"], RODIN])
        # 45 days later every page is read again even with the same sitemap dates
        ctx["today"] = TODAY + dt.timedelta(days=50)
        ctx["lo"], ctx["hi"] = ctx["today"] - dt.timedelta(days=3), ctx["today"] + dt.timedelta(days=120)
        asked, _ = self._run(ctx, changed)
        self.assertEqual(len(asked), 1 + 6)

    def test_read_opens_a_limited_number_of_pages_per_run(self):
        ctx = self.ctx()
        asked, got = self._run(ctx, limit=2)
        self.assertEqual(asked, [SRC["url"], ALTER, JAZZ])
        self.assertEqual([e["title"] for e in got], ["Friday Night: Holiday Jazz & Artist Market"])
        asked, got = self._run(ctx, limit=2)                         # the next run continues down the list
        self.assertEqual(asked[1], RODIN)
        self.assertEqual(len(asked), 3)
        self.assertEqual(len(got), 13)


if __name__ == "__main__":
    unittest.main()
