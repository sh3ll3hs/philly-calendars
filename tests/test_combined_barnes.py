"""Barnes Foundation reader against trimmed copies of its What's On page and two "View More" pages (no network)."""
import datetime as dt
import importlib
import os
import unittest

R = importlib.import_module("combined_readers.barnes")

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SRC = {"id": "barnes", "name": "Barnes Foundation", "method": "custom", "reader": "barnes",
       "url": "https://www.barnesfoundation.org/whats-on"}
TODAY = dt.date(2026, 11, 15)
BARNES = "Barnes Foundation, 2025 Benjamin Franklin Pkwy, Philadelphia, PA 19130"
P2, P3, P4 = (f"https://www.barnesfoundation.org/whats-on/p{n}?ajax=1" for n in (2, 3, 4))


def fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


class Barnes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page1, cls.page3, cls.page4 = (fixture(n) for n in
                                           ("combined_barnes.html", "combined_barnes_p3.html", "combined_barnes_p4.html"))
        cls.ev = {e["title"]: e for e in R.parse(cls.page1, SRC, TODAY)}

    def test_titles_dates_times_and_place(self):
        talk = self.ev["In Conversation: Brandon Shimoda and Rea Tajiri"]
        self.assertEqual(talk["start"], dt.datetime(2026, 12, 2, 18, 0))         # "Wednesday, December 2, 6 – 7pm"
        self.assertEqual(talk["end"], dt.datetime(2026, 12, 2, 19, 0))
        self.assertFalse(talk["all_day"])
        self.assertEqual(talk["loc"], BARNES)
        self.assertEqual(talk["url"],
                         "https://www.barnesfoundation.org/whats-on/talks/in-conversation-brandon-shimoda-and-rea-tajiri")
        self.assertTrue(talk["desc"].startswith("Free / Talks\n\nWednesday, December 2, 6 – 7pm"))
        friday = self.ev["First Friday: Sky Hopinka, Raven Chacon & Andrew Yong Hoon Lee"]
        self.assertEqual((friday["start"], friday["end"]),                        # "Friday, December 4, 6 – 9pm"
                         (dt.datetime(2026, 12, 4, 18, 0), dt.datetime(2026, 12, 4, 21, 0)))
        gallery = self.ev["Members-Only Gallery Talk: Plastic Utopia: Art, Industry, and Culture in the Atomic Age"]
        self.assertEqual((gallery["start"], gallery["end"]),                      # "Sunday, November 22, 10:15 – 11am"
                         (dt.datetime(2026, 11, 22, 10, 15), dt.datetime(2026, 11, 22, 11, 0)))

    def test_online_programs_are_not_placed_at_the_museum(self):
        tour = self.ev["Members-Only Online Evening Tour: Decoding the Barnes Ensembles"]
        self.assertEqual(tour["loc"], "Online")
        self.assertEqual((tour["start"], tour["end"]),                            # "Monday, November 16, 5:30 – 6:30pm"
                         (dt.datetime(2026, 11, 16, 17, 30), dt.datetime(2026, 11, 16, 18, 30)))

    def test_two_line_date_uses_the_first_session(self):
        seminar = self.ev["Exhibition Seminar: Noguchi to Asawa: Designing Postwar America"]
        self.assertEqual((seminar["start"], seminar["end"]),                      # "Tuesday, November 17" / "11am – 1pm or 3 – 5pm"
                         (dt.datetime(2026, 11, 17, 11, 0), dt.datetime(2026, 11, 17, 13, 0)))
        self.assertIn("Tuesday, November 17, 11am – 1pm or 3 – 5pm", seminar["desc"])

    def test_standing_tours_and_current_exhibitions_are_left_out(self):
        self.assertEqual(len(self.ev), 8)                                         # of the page's 21 cards
        for title in ("The Barnes Collection", "Highlights Tour", "Daily Gallery Talks",
                      "Sky Hopinka: Red Metal Dust",                              # "Until January 18, 2027"
                      "Noguchi to Asawa: Designing Postwar America",              # "Until January 10, 2027"
                      "December Spotlight Tour: Decoding the Barnes Ensembles"):  # "Thursday–Monday, 1pm"
            self.assertNotIn(title, self.ev)
        self.assertFalse([e for e in self.ev.values() if R.C.day_of(e) in (dt.date(2027, 1, 18), dt.date(2027, 1, 10),
                                                                           dt.date(2027, 2, 22))])

    def test_upcoming_exhibition_is_all_day_with_its_closing_day(self):
        show = self.ev["Rochelle Feinstein: The Today Show"]                      # "February 21 – May 9, 2027"
        self.assertTrue(show["all_day"])
        self.assertEqual((show["start"], show["end"]), (dt.date(2027, 2, 21), dt.date(2027, 5, 9)))

    def test_later_pages_new_year_and_weekly_class(self):
        ev = {e["title"]: e for e in R.parse(self.page3, SRC, TODAY)}
        self.assertEqual(len(ev), 6)
        self.assertEqual(ev["Barnes Cinema: Strawberry Fields by Rea Tajiri"]["start"], dt.datetime(2027, 1, 9, 13, 0))
        self.assertEqual(ev["Art, Ritual, and Death in the 19th Century"]["loc"], "Online")     # type "Workshops / Online"
        course = ev["Courbet: Painter of Women"]                  # "Wednesdays, February 10 – February 17, 2 – 4pm"
        self.assertEqual((course["start"], course["end"]),
                         (dt.datetime(2027, 2, 10, 14, 0), dt.datetime(2027, 2, 17, 16, 0)))
        last = {e["title"]: e for e in R.parse(self.page4, SRC, TODAY)}
        self.assertEqual(last["Barnes Curious? Let’s Talk about Picasso"]["start"], dt.datetime(2027, 5, 10, 18, 0))

    def test_date_lines(self):
        w = lambda line: R.when(line, TODAY)
        self.assertIsNone(w("Until January 18, 2027"))
        self.assertIsNone(w("Ongoing"))
        self.assertIsNone(w("Thursday–Monday, 11:30am, 12:30pm & 1:30pm"))
        self.assertIsNone(w("Mondays & Thursdays, 2pm"))
        self.assertEqual(w("Friday, December 11, 12 – 12:30pm"),
                         (dt.datetime(2026, 12, 11, 12, 0), dt.datetime(2026, 12, 11, 12, 30), False))
        self.assertEqual(w("Saturday, December 5"), (dt.date(2026, 12, 5), None, True))          # no time: all-day
        self.assertEqual(w("December 5 – 6, 10am – 5pm"),
                         (dt.datetime(2026, 12, 5, 10, 0), dt.datetime(2026, 12, 6, 17, 0), False))
        self.assertEqual(w("November 28, 2026 – January 3, 2027"), (dt.date(2026, 11, 28), dt.date(2027, 1, 3), True))
        self.assertEqual(w("December 12 – March 7, 2027"), (dt.date(2026, 12, 12), dt.date(2027, 3, 7), True))
        self.assertEqual(w("Sunday, January 3, 10am – 5pm")[0], dt.datetime(2027, 1, 3, 10, 0))  # weekday fixes the year

    def test_read_follows_view_more_the_way_the_site_does(self):
        C, asked = R.C, []
        pages = {SRC["url"]: self.page1, P2: self.page3.replace("/whats-on/p4", "/whats-on/p3"), P3: self.page3,
                 P4: self.page4}
        real = C.get_text
        C.get_text = lambda url: asked.append(url) or pages[url]
        try:
            ev = R.read(SRC, {"lo": TODAY - dt.timedelta(days=3), "hi": TODAY + dt.timedelta(days=120), "today": TODAY,
                              "detail": {}})
        finally:
            C.get_text = real
        self.assertEqual(asked, [SRC["url"], P2, P3, P4])  # page 4 has no "View More"
        self.assertEqual(len(ev), 8 + 6 + 4)               # the repeated page adds nothing


if __name__ == "__main__":
    unittest.main()
