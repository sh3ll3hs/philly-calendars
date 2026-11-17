"""Queer Tech Events feed: readers against saved pages (real pages, trimmed) and the
engine options the feed uses."""
import datetime as dt
import importlib
import os
import unittest

import combined_to_ics as C
from combined_readers import zones

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
TODAY = dt.date(2026, 11, 17)


def load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def reader(name):
    return importlib.import_module(f"combined_readers.{name}")


def src(sid, url, **kw):
    return dict({"id": sid, "name": sid, "method": "custom", "url": url}, **kw)


class Zones(unittest.TestCase):
    def test_state_code_decides_before_city_names(self):
        self.assertEqual(zones.zone_for("525 Santa Fe Dr., Denver, CO 80204"), "America/Denver")
        self.assertEqual(zones.zone_for("London Grill, 2301 Fairmount Ave, Philadelphia, PA 19130"), "America/New_York")
        self.assertEqual(zones.zone_for("Wrigleyville North, 3900 North Sheridan Road Chicago, IL, 60613"), "America/Chicago")
        self.assertEqual(zones.zone_for("1 Main St, El Paso, TX 79901"), "America/Denver")

    def test_two_zone_state_needs_a_known_city(self):
        self.assertEqual(zones.zone_for("Broadway, Nashville, TN 37203"), "America/Chicago")
        self.assertIsNone(zones.zone_for("Somewhere, TN 37000"))

    def test_abroad_and_unknown(self):
        self.assertEqual(zones.zone_for("119-HS Elandsstraat, 1016 RX Amsterdam"), "Europe/Amsterdam")
        self.assertEqual(zones.zone_for("Toronto, ON M4W 3X8"), "America/Toronto")
        self.assertIsNone(zones.zone_for("Virtual"))
        self.assertIsNone(zones.zone_for(""))

    def test_relocate_moves_or_falls_back_to_all_day(self):
        e = {"start": dt.datetime(2026, 12, 10, 18, 0), "end": dt.datetime(2026, 12, 10, 20, 0), "all_day": False,
             "loc": "Driftwood, 1225 Folsom Street San Francisco, CA, 94103", "desc": ""}
        moved = zones.relocate(e)
        self.assertEqual((moved["start"], moved["end"]), (dt.datetime(2026, 12, 10, 21, 0), dt.datetime(2026, 12, 10, 23, 0)))
        lost = zones.relocate(dict(e, loc="The usual place"))
        self.assertTrue(lost["all_day"])
        self.assertEqual(lost["start"], dt.date(2026, 12, 10))
        self.assertIn("Time as listed: 6:00 PM - 8:00 PM", lost["desc"])
        same = zones.relocate(dict(e, loc="208 West 13th Street New York, NY, 10011"))
        self.assertEqual(same["start"], e["start"])


class OutInTech(unittest.TestCase):
    R, S = reader("qt_outintech"), src("qt_outintech", "https://outintech.com/events/")

    def test_list_reads_the_upcoming_cards(self):
        items = self.R.parse_list(load("qt_outintech_list.html"), self.S)
        self.assertEqual(len(items), 9)                       # the "Past Events" cards have no <h3> and are left out
        den = next(i for i in items if "Denver" in i["title"])
        self.assertEqual((den["day"], den["loc"]), (dt.date(2026, 11, 17), "525 Santa Fe Dr., Denver, CO 80204"))
        self.assertEqual(den["url"], "https://outintech.com/event/out-in-tech-denver-november-monthly-mixer/")
        self.assertEqual(self.R.next_page(load("qt_outintech_list.html"), 1), "https://outintech.com/events/page/2/")

    def test_event_page_gives_venue_time_moved_to_eastern_and_the_signup_link(self):
        items = self.R.parse_list(load("qt_outintech_list.html"), self.S)
        den = next(i for i in items if "Denver" in i["title"])
        info = self.R.parse_detail(load("qt_outintech_detail.html"))
        self.assertEqual(info["when"], "November 17, 2026 5:30 pm - 7:30 pm")
        e = self.R.build(den, info, self.S)
        self.assertEqual((e["start"], e["end"]), (dt.datetime(2026, 11, 17, 19, 30), dt.datetime(2026, 11, 17, 21, 30)))
        self.assertTrue(e["rsvp"].startswith("https://www.eventbrite.com/e/out-in-tech-denver-november-monthly-mixer"))

    def test_no_event_page_or_no_zone_means_all_day_never_a_guess(self):
        items = self.R.parse_list(load("qt_outintech_list.html"), self.S)
        den = next(i for i in items if "Denver" in i["title"])
        e = self.R.build(den, None, self.S)
        self.assertTrue(e["all_day"])
        self.assertEqual(e["start"], dt.date(2026, 11, 17))
        info = dict(self.R.parse_detail(load("qt_outintech_detail.html")), venue="Virtual")
        e = self.R.build(dict(den, loc=""), info, self.S)
        self.assertTrue(e["all_day"])
        self.assertEqual(e["loc"], "Online")
        self.assertIn("Time as listed: 5:30 PM - 7:30 PM", e["desc"])


class OutAndEqual(unittest.TestCase):
    def test_cards(self):
        R = reader("qt_outandequal")
        ev = R.parse(load("qt_outandequal_list.html"), src("qt_outandequal", "https://outandequal.org/events/?_period=upcoming-events"), TODAY)
        self.assertEqual(len(ev), 6)
        first = ev[0]
        self.assertEqual(first["title"], "Quarterly Partner Learning Meetup: November")
        self.assertEqual(first["start"], dt.datetime(2026, 11, 18, 12, 0))      # "Wed, Nov 18 – 12:00 PM ET"
        self.assertEqual(first["loc"], "Online")
        self.assertEqual(first["url"], "https://outandequal.org/event/partner-learning-meetup-november-2026/")
        apac = next(e for e in ev if "APAC" in e["title"])
        self.assertEqual(apac["start"].date(), dt.date(2027, 2, 12))            # "Fri, Feb 12": the year comes from the weekday
        self.assertEqual(apac["loc"], "Manila, Philippines")

    def test_year_from_weekday(self):
        R = reader("qt_outandequal")
        m = R.DAY_RX.search("Fri, Feb 12 – 12:30 PM ET")
        self.assertEqual(R.day_from(m, TODAY), dt.date(2027, 2, 12))
        m = R.DAY_RX.search("Wed, Nov 18 – 12:00 PM ET")
        self.assertEqual(R.day_from(m, TODAY), dt.date(2026, 11, 18))


class IndependenceBusinessAlliance(unittest.TestCase):
    def test_home_page_cards(self):
        ev = reader("qt_thinkiba").parse(load("qt_thinkiba_home.html"), src("qt_thinkiba", "https://thinkiba.com/"))
        self.assertEqual(len(ev), 3)
        connx = ev[0]
        self.assertEqual(connx["title"], "November ConnX: with Philly Pride Visitor Center")
        self.assertEqual((connx["start"], connx["end"]), (dt.datetime(2026, 11, 19, 17, 30), dt.datetime(2026, 11, 19, 19, 0)))
        self.assertEqual(connx["loc"], "Philly Pride Visitor Center, 12th and Locust, Philadelphia, PA 19107")
        self.assertTrue(connx["rsvp"].startswith("https://members.thinkiba.com/ap/Events/Register/"))
        self.assertEqual(ev[1]["loc"], "Online (Zoom)")
        self.assertEqual(ev[1]["start"], dt.datetime(2026, 11, 17, 12, 0))


class TransWork(unittest.TestCase):
    R, S = reader("qt_transwork"), src("qt_transwork", "https://www.transwork.org/events")

    def test_list(self):
        items = self.R.parse_list(load("qt_transwork_list.html"), self.S)
        self.assertEqual(len(items), 30)
        self.assertEqual((items[0]["day"], items[0]["title"]), (dt.date(2026, 11, 10), "TransWork Happy Hour Networking at Val's Lesbian Bar"))
        self.assertEqual(items[0]["url"], "https://www.transwork.org/events/transwork-happy-hour-networking-vals-lesbian-bar")
        span = next(i for i in items if i["title"] == "FREE Trans Affirming Spaces Workshop")
        self.assertEqual((span["day"], span["end"]), (dt.date(2025, 1, 23), dt.date(2025, 2, 26)))

    def test_event_page(self):
        items = self.R.parse_list(load("qt_transwork_list.html"), self.S)
        info = self.R.parse_detail(load("qt_transwork_detail.html"))
        e = self.R.build(items[0], info, self.S)
        self.assertEqual(e["start"], dt.datetime(2026, 11, 10, 16, 0))          # "November 10, 2026 - 4:00pm"
        self.assertEqual(e["loc"], "605 S 3rd St, Philadelphia PA, 19147")
        self.assertTrue(e["rsvp"].startswith("https://members.thinkiba.com/ap/Events/Register/"))
        bare = self.R.build(items[0], None, self.S)                             # page not read yet: the date only
        self.assertTrue(bare["all_day"])


class OutLeadership(unittest.TestCase):
    def test_list_is_dates_only_and_skips_untitled_entries(self):
        ev = reader("qt_outleadership").parse(load("qt_outleadership_list.html"), src("qt_outleadership", "https://outleadership.com/events/"))
        self.assertTrue(ev and all(e["all_day"] and e["title"] for e in ev))
        got = {e["title"]: e["start"] for e in ev}
        self.assertEqual(got["Virtual OutNEXT 2026"], dt.date(2026, 3, 1))
        self.assertEqual(got["2025 Australia Summit"], dt.date(2025, 10, 21))
        self.assertNotIn(dt.date(2026, 11, 17), got.values())                   # the entry with an empty <h5>


class DateLine(unittest.TestCase):
    R = reader("qt_dateline")

    def test_heading_date_place_blocks(self):
        url = "https://reachingoutmba.org/events/"
        ev = self.R.parse(load("qt_romba_events.html"), src("qt_romba", url), url)
        got = {e["title"]: (e["start"], e["end"], e["loc"]) for e in ev}
        self.assertEqual(got["Club Leadership Summit"], (dt.date(2026, 4, 10), dt.date(2026, 4, 11), "Dallas, TX"))
        self.assertEqual(got["Boston Trek"], (dt.date(2026, 7, 21), None, "Boston, MA"))      # "July 21, 2026 (one day only)"
        self.assertEqual(got["Prospective MBA Admissions Summit"], (dt.date(2026, 8, 12), None, "Online"))
        self.assertEqual(got["ROMBA Conference 2026"], (dt.date(2026, 10, 1), dt.date(2026, 10, 3), "Dallas, TX"))
        self.assertEqual(len(ev), 6)

    def test_single_event_page_with_fixed_title(self):
        url = "https://lwtsquad.com/"
        ev = self.R.parse(load("qt_lwt_home.html"), src("qt_lwt", url, title="LWT Summit", limit=1), url)
        self.assertEqual([(e["title"], e["start"], e["end"], e["loc"]) for e in ev],
                         [("LWT Summit", dt.date(2027, 6, 7), dt.date(2027, 6, 9), "New York")])

    def test_a_date_without_a_year_is_ignored(self):
        page = "<h3>Spring Mixer</h3><p>April 10-11</p><p>Dallas, TX</p>"
        self.assertEqual(self.R.parse(page, src("x", "https://example.org/"), "https://example.org/"), [])


class Meetup(unittest.TestCase):
    def test_group_page(self):
        ev = reader("qt_meetup").parse(load("qt_meetup_toronto.html"), src("qt_queertech_toronto", "https://www.meetup.com/queertech-toronto/events/"))
        self.assertEqual(len(ev), 9)                                            # 11 on the page, 2 cancelled
        q = next(e for e in ev if e["title"] == "QT Qonference 2026")
        self.assertEqual((q["start"], q["end"]), (dt.datetime(2026, 11, 18, 8, 0), dt.datetime(2026, 11, 19, 17, 0)))
        self.assertIn("Evergreen Brick Works", q["loc"])
        self.assertIn("550 Bayview Ave", q["loc"])
        self.assertEqual(q["rsvp"], "https://www.meetup.com/queertech-toronto/events/315378030/")
        self.assertIn("Online", {e["loc"] for e in ev})


class EventbriteAnywhere(unittest.TestCase):
    R = reader("eventbrite")
    S = src("qt_outprofessionals", "https://www.eventbrite.com/o/out-professionals-2962025045", reader="eventbrite")

    def test_national_organizer_keeps_every_city_in_eastern_time(self):
        ev = self.R.parse(load("qt_eventbrite_outpro.html"), dict(self.S, anywhere=True))
        self.assertEqual(len(ev), 7)
        chi = next(e for e in ev if "Chicago" in e["loc"])
        self.assertEqual(chi["start"], dt.datetime(2026, 11, 18, 19, 0))        # 6:00 PM Central
        la = next(e for e in ev if "Los Angeles" in e["title"])
        self.assertEqual(la["start"], dt.datetime(2026, 12, 3, 21, 0))          # 6:00 PM Pacific
        self.assertTrue(all(e["rsvp"] == e["url"] for e in ev))

    def test_default_is_still_philadelphia_only(self):
        ev = self.R.parse(load("qt_eventbrite_outpro.html"), self.S)
        self.assertEqual([e["title"] for e in ev], ["OutPro Meaningful LGBTQ+ Networking - Philly"])
        self.assertNotIn("rsvp", ev[0])


class Engine(unittest.TestCase):
    def test_rsvp_lines(self):
        s = {"id": "x", "name": "Some Org", "url": "https://example.org/events"}
        a = C.event(s, "a", "With a link", dt.datetime(2026, 12, 1, 18, 0), None, False, "Online", "https://example.org/a",
                    rsvp="https://tickets.example.org/a")
        b = C.event(s, "b", "Without", dt.date(2026, 12, 2), None, True, "", "https://example.org/b")
        ics = C.unfold(C.build_ics([a, b], "Queer Tech Events", rsvp_lines=True))
        self.assertIn("X-WR-CALNAME:Queer Tech Events", ics)
        self.assertIn("Event page: https://example.org/a\\nRSVP: https://tickets.example.org/a", ics)
        self.assertIn("Event page: https://example.org/b\\nRSVP: on the event page", ics)
        plain = C.unfold(C.build_ics([b]))                                      # the combined feed is unchanged
        self.assertIn("X-WR-CALNAME:Philly combined events", plain)
        self.assertNotIn("RSVP", plain)

    def test_signup_link_found_on_an_event_page(self):
        from combined_readers import qt_common as Q
        page = ('<a href="/upcoming-events">Back to All Events</a> <a href="https://www.facebook.com/sharer?u=x">Share</a>'
                '<a href="http://www.google.com/calendar/event?action=TEMPLATE">Google Calendar</a>'
                '<a href="https://www.eventbrite.com/e/holiday-party-tickets-2004429990058">Get tickets</a>')
        self.assertEqual(Q.find_rsvp(page, "https://buildoutalliance.org/upcoming-events/x"),
                         "https://www.eventbrite.com/e/holiday-party-tickets-2004429990058")
        self.assertEqual(Q.find_rsvp('<a href="https://example.com/signup">Register here</a>', "https://example.org/e/1"),
                         "https://example.com/signup")
        self.assertEqual(Q.find_rsvp('<a href="/contact">Contact</a><a href="https://other.example/">Our partner</a>',
                                     "https://example.org/e/1"), "")

    def test_year_after_a_date_range(self):
        self.assertEqual([d for _, d in C._dates_in("April 10-11, 2026", TODAY)], [dt.date(2026, 4, 10)])
        self.assertEqual([d for _, d in C._dates_in("June 7 - July 2, 2026", TODAY)], [dt.date(2026, 6, 7), dt.date(2026, 7, 2)])
        self.assertEqual([d for _, d in C._dates_in("Dec 5", TODAY)], [dt.date(2026, 12, 5)])


class NewQueerTechReaders(unittest.TestCase):
    def test_accelevents_cards(self):
        R = reader("qt_outintech")
        html = '''
        <div class="org-desc">
          <div class="organizer-info">
            <div class="organizer-date-text">Wed, Dec 16, 2026 from 12:30 AM to 2:30 AM (GMT)</div>
            <div class="organizer-event-name-location">
              <a href="https://www.accelevents.com/e/denver122026">Out in Tech Denver | December Monthly Mixer</a>
              <div class="organizer-location-text"><span>Town Hall Collaborative, 525 Santa Fe Dr, Denver, CO, USA</span></div>
            </div>
          </div>
          <div class="price_wrap"><span>Free</span></div>
        </div>
        '''
        ev = R.parse_accelevents(html, src("qt_outintech", "https://outintech.com/events/"))
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["title"], "Out in Tech Denver | December Monthly Mixer")
        self.assertEqual(ev[0]["start"], dt.datetime(2026, 12, 15, 19, 30))
        self.assertEqual(ev[0]["end"], dt.datetime(2026, 12, 15, 21, 30))
        self.assertEqual(ev[0]["loc"], "Town Hall Collaborative, 525 Santa Fe Dr, Denver, CO, USA")
        self.assertEqual(ev[0]["url"], "https://events.outintech.com/e/denver122026")

    def test_qcal_jsonld(self):
        R = reader("qt_qcal")
        html = '''
        <script type="application/ld+json">
        {"@context":"https://schema.org","@graph":[
          {"@type":"Event","name":"Trans and Nonbinary Inclusion [Nov 19]","startDate":"2026-11-19T13:00:00-05:00","endDate":"2026-11-19T14:00:00-05:00",
           "location":{"@type":"VirtualLocation"},"offers":{"@type":"Offer","url":"https://qcal.app/event/test"}}
        ]}
        </script>
        '''
        ev = R.parse_qcal_event_page(html, "https://qcal.app/event/test", src("qt_prideatwork", "https://qcal.app/host/pride-at-work-canada"))
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["start"], dt.datetime(2026, 11, 19, 13, 0))
        self.assertEqual(ev[0]["loc"], "Online")

    def test_queer_in_ai_news_block(self):
        R = reader("qt_queerinai")
        html = '''
        <ul><li><p><a href="/neurips-2026"><strong>NeurIPS 2026</strong></a> <strong>(December 06-13): Workshop</strong></p>
        <ul><li><p>We will be hosting workshops and socials at all three venues (Atlanta, USA; Paris, France; Sydney, Australia) - more details to come soon!</p></li></ul></li></ul>
        '''
        ev = R.parse(html, src("qt_queerinai", "https://www.queerinai.com/"), today=TODAY)
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["title"], "Queer in AI @ NeurIPS 2026: Workshop")
        self.assertEqual((ev[0]["start"], ev[0]["end"]), (dt.date(2026, 12, 6), dt.date(2026, 12, 13)))
        self.assertEqual(ev[0]["loc"], "Atlanta, USA; Paris, France; Sydney, Australia")
        self.assertEqual(ev[0]["url"], "https://www.queerinai.com/neurips-2026")

    def test_maven_youth_detail_jsonld(self):
        R = reader("qt_mavenyouth")
        html = '''
        <script type="application/ld+json">
        {"@type":"Event","name":"2027 NYC Summer Camp","startDate":"2027-08-02T09:30:00-05:00","endDate":"2027-08-13T17:30:00-05:00",
         "location":{"@type":"Place","name":"Multiple Locations, Greater NYC Area"}}
        </script>
        '''
        ev = R.parse_detail_jsonld(html, "https://www.mavenyouth.org/event-details/2027-nyc-summer-camp", src("qt_mavenyouth", "https://www.mavenyouth.org/summer-camps"))
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["title"], "2027 NYC Summer Camp")
        self.assertEqual(ev[0]["loc"], "Multiple Locations, Greater NYC Area")

    def test_point_foundation_detail(self):
        R = reader("qt_pointfoundation")
        html = '''
        <main><h1>Partner Registration</h1>
        <p>The 2026 National Leadership Conference (NLC) will take place Thursday, July 16, through Sunday, July 19, at the Sheraton Universal Hotel in Universal City, CA.</p>
        </main>
        '''
        info = R.parse_detail(html, "https://pointfoundation.org/community/events/national-leadership-conference-partners", "Partner Registration")
        e = R.build_event("https://pointfoundation.org/community/events/national-leadership-conference-partners", info, src("qt_pointfoundation", "https://pointfoundation.org/community/events"))
        self.assertEqual(e["title"], "2026 National Leadership Conference (NLC)")
        self.assertEqual((e["start"], e["end"]), (dt.date(2026, 7, 16), dt.date(2026, 7, 19)))
        self.assertEqual(e["loc"], "Sheraton Universal Hotel in Universal City, CA")

    def test_mygwork_cards(self):
        from bs4 import BeautifulSoup
        R = reader("qt_mygwork")
        html = '''
        <div class="w-full"><a href="/events/eurout-2026"><h4>EUROUT 2026</h4></a>
        <p>Europe's leading LGBTQ+ business conference.</p>
        <div><span>Start:</span><span>November 19, 2026</span><span>at</span><span>9:00 AM</span><span>GMT</span>
        <span>End:</span><span>November 21, 2026</span><span>at</span><span>9:00 PM</span><span>GMT</span>
        <span>London Business School</span></div></div>
        '''
        ev = R.parse(BeautifulSoup(html, "html.parser"), src("qt_mygwork", "https://mygwork.com/en/events"))
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["title"], "EUROUT 2026")
        self.assertEqual(ev[0]["start"], dt.datetime(2026, 11, 19, 4, 0))
        self.assertEqual(ev[0]["loc"], "London Business School")



if __name__ == "__main__":
    unittest.main()
