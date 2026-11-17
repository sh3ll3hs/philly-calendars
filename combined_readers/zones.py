"""Time zones for events held outside Philadelphia.

The feeds here are written in America/New_York. A national organization prints each
event's clock time as local time at the venue ("5:30 pm" for a mixer in Denver), so the
time has to be moved to Eastern before it goes in the feed, and that takes the venue's
time zone. `zone_for` works one out from the written address and returns None when it
cannot tell. Callers then keep the date, make the event all-day and quote the printed
time in the description (`unplaced`) instead of guessing.

What is recognized:
  * a US state, as "City, ST 12345", "City, ST" or the state's full name. States that
    lie in two zones are answered only for the cities listed in US_CITY (Nashville is
    Central, Knoxville Eastern), or with the zone nearly the whole state uses when the
    other part is a few rural counties (Texas, Florida, Michigan, Oregon, ...; El Paso
    and Pensacola are listed);
  * a Canadian province ("Toronto, ON", "Montréal, QC");
  * with no state or province code in the address, the cities and countries in CITY
    (Amsterdam, London, Berlin, Manila, a few large US cities) and US state names.
An address with none of these gives None.
"""
import datetime as dt
import re
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
E, CT, MT, PT = "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles"

STATE = {
    "CT": E, "DE": E, "DC": E, "GA": E, "ME": E, "MD": E, "MA": E, "NH": E, "NJ": E, "NY": E, "NC": E, "OH": E,
    "PA": E, "RI": E, "SC": E, "VT": E, "VA": E, "WV": E, "FL": E, "MI": E,
    "AL": CT, "AR": CT, "IL": CT, "IA": CT, "LA": CT, "MN": CT, "MS": CT, "MO": CT, "OK": CT, "WI": CT, "TX": CT,
    "CO": MT, "MT": MT, "NM": MT, "UT": MT, "WY": MT, "AZ": "America/Phoenix",
    "CA": PT, "NV": PT, "WA": PT, "OR": PT, "HI": "Pacific/Honolulu", "AK": "America/Anchorage", "PR": "America/Puerto_Rico",
    # Canada
    "ON": "America/Toronto", "QC": "America/Toronto", "BC": "America/Vancouver", "AB": "America/Edmonton",
    "MB": "America/Winnipeg", "NS": "America/Halifax", "NB": "America/Moncton",
}
# Two-zone states: answered only for a city in US_CITY
SPLIT = {"TN", "KY", "IN", "ID", "KS", "NE", "ND", "SD"}
STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO",
    "connecticut": "CT", "delaware": "DE", "district of columbia": "DC", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "illinois": "IL", "iowa": "IA", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO",
    "montana": "MT", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM",
    "new york": "NY", "north carolina": "NC", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}
# Cities that settle a two-zone state, and the three that differ from the rest of their state
US_CITY = {
    "el paso": MT, "pensacola": CT, "panama city": CT,
    "nashville": CT, "memphis": CT, "knoxville": E, "chattanooga": E, "louisville": E, "lexington": E,
    "indianapolis": E, "boise": "America/Boise", "kansas city": CT, "wichita": CT, "omaha": CT, "lincoln": CT,
    "sioux falls": CT, "fargo": CT,
}
# Places recognized when the address has no state or province code
CITY = {
    "washington dc": E, "washington, dc": E, "washington d.c.": E, "new york city": E, "philadelphia": E,
    "san francisco": PT, "los angeles": PT, "seattle": PT, "chicago": CT, "boston": E, "denver": MT,
    "amsterdam": "Europe/Amsterdam", "netherlands": "Europe/Amsterdam", "london": "Europe/London",
    "united kingdom": "Europe/London", "edinburgh": "Europe/London",
    "dublin": "Europe/Dublin", "ireland": "Europe/Dublin", "berlin": "Europe/Berlin", "munich": "Europe/Berlin",
    "germany": "Europe/Berlin", "paris": "Europe/Paris", "france": "Europe/Paris", "madrid": "Europe/Madrid",
    "barcelona": "Europe/Madrid", "zurich": "Europe/Zurich", "stockholm": "Europe/Stockholm",
    "copenhagen": "Europe/Copenhagen", "toronto": "America/Toronto", "montreal": "America/Toronto",
    "montréal": "America/Toronto", "ottawa": "America/Toronto", "vancouver": "America/Vancouver",
    "calgary": "America/Edmonton", "edmonton": "America/Edmonton", "halifax": "America/Halifax",
    "mexico city": "America/Mexico_City", "são paulo": "America/Sao_Paulo", "sao paulo": "America/Sao_Paulo",
    "tel aviv": "Asia/Jerusalem", "singapore": "Asia/Singapore", "hong kong": "Asia/Hong_Kong",
    "tokyo": "Asia/Tokyo", "manila": "Asia/Manila", "philippines": "Asia/Manila", "bengaluru": "Asia/Kolkata",
    "bangalore": "Asia/Kolkata", "mumbai": "Asia/Kolkata", "india": "Asia/Kolkata", "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
}
# Letters a site may print after a clock time ("12:00 PM ET")
ABBR = {"ET": E, "EST": E, "EDT": E, "EASTERN": E, "CT": CT, "CST": CT, "CDT": CT, "CENTRAL": CT,
        "MT": MT, "MST": MT, "MDT": MT, "MOUNTAIN": MT, "PT": PT, "PST": PT, "PDT": PT, "PACIFIC": PT,
        "GMT": "Etc/UTC", "UTC": "Etc/UTC", "BST": "Europe/London", "CET": "Europe/Berlin", "CEST": "Europe/Berlin"}


def zone_for(address):
    """IANA zone name for a written address or place, or None when it cannot be told.
    A state or province code decides first ("London Grill, Philadelphia, PA" is Eastern);
    city and country names are only consulted when the address has no such code, or to
    settle a state that lies in two zones."""
    a = " ".join(str(address or "").split())
    if not a:
        return None
    low = a.lower()

    def named(names):
        for name in sorted(names, key=len, reverse=True):
            if re.search(r"(?<![a-zà-ÿ])" + re.escape(name) + r"(?![a-zà-ÿ])", low):
                return name
        return None

    codes = [c for c in re.findall(r",\s*([A-Z]{2})(?=\s+\d{5}(?:-\d{4})?\b|\s+[A-Z]\d[A-Z]\s?\d[A-Z]\d\b|\s*(?:,|$))", a)
             if c in STATE or c in SPLIT]
    if codes:
        st = codes[-1]
        city = named(US_CITY)
        if st in SPLIT or (city and (st, city) in (("TX", "el paso"), ("FL", "pensacola"), ("FL", "panama city"))):
            return US_CITY.get(city)
        return STATE[st]
    hit = named(CITY)
    if hit:
        return CITY[hit]
    hit = named(STATE_NAMES)                      # "New York City", "Philadelphia, Pennsylvania"
    return STATE.get(STATE_NAMES[hit]) if hit else None


def to_ny(wall, zone):
    """Naive wall time in `zone` -> naive America/New_York wall time."""
    return wall.replace(tzinfo=ZoneInfo(zone)).astimezone(NY).replace(tzinfo=None)


def clock_text(start, end=None):
    """'5:30 PM' or '5:30 PM - 7:30 PM' for the printed-time note."""
    def one(t):
        return t.strftime("%-I:%M %p")
    return one(start) + (f" - {one(end)}" if end else "")


def unplaced(day, start, end=None):
    """What to do with a clock time whose zone is unknown: the note for the description."""
    return f"Time as listed: {clock_text(start, end)} (local time at the venue; time zone not given)"


def relocate(e):
    """An event read with its clock time taken as Eastern, when the time is really local to
    the venue (registry entry with "tz": "venue"): move it to Eastern by the venue's zone,
    or make it all-day with the printed time quoted when the venue's zone cannot be told."""
    st, en = e.get("start"), e.get("end")
    if e.get("all_day") or "raw" in e or not isinstance(st, dt.datetime):
        return e
    zone = zone_for(e.get("loc"))
    if zone == E:
        return e
    e = dict(e)
    if zone:
        e["start"] = to_ny(st, zone)
        if isinstance(en, dt.datetime):
            e["end"] = to_ny(en, zone)
        return e
    note = unplaced(st.date(), st, en if isinstance(en, dt.datetime) else None)
    e.update(start=st.date(), end=None, all_day=True, desc="\n\n".join(x for x in (e.get("desc"), note) if x))
    return e
