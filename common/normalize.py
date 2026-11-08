"""Shared normalisation: clock times, year inference, multi-date expansion, record shape."""
import datetime as dt
import re

# One clock time: 8:00PM, 8:00 PM, 6:30pm, 7PM, 5pm, 7 p.m., 08:00PM
_CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?(?![a-z])", re.I)

MONTHS = {m: i for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}


def normalize_time(text):
    """All clock times in `text` as 'HH:MM' strings, in order.
    Handles '7:30PM & 9:30PM', '6:30PM and 9:00PM', '6pm/8:30pm'."""
    out = []
    for h, m, ap in _CLOCK.findall(text or ""):
        h = int(h)
        if not 1 <= h <= 12:
            continue
        h = h % 12 + (12 if ap.lower() == "p" else 0)
        out.append(f"{h:02d}:{int(m or 0):02d}")
    return out


def first_time(text):
    t = normalize_time(text)
    return t[0] if t else None


def month_num(word):
    return MONTHS.get((word or "").strip(".").lower()[:3])


def infer_year(month, day, today=None, lookback_days=30):
    """Listings without a year: pick this year, or next year if that date is
    already more than `lookback_days` in the past. None for impossible dates."""
    today = today or dt.date.today()
    for y in (today.year, today.year + 1):
        try:
            d = dt.date(y, month, day)
        except ValueError:  # Feb 29 in a non-leap year, etc.
            continue
        if d >= today - dt.timedelta(days=lookback_days):
            return d
    return None


_DAYNAME = r"(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?"
_MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"


def expand_dates(text, today=None):
    """Dates written in listing shorthand, expanded to one date each:
      'Sun Nov 8'                      -> [Nov 8]
      'FRI, SAT & SUN NOV 13, 14 & 15' -> [Nov 13, 14, 15]
      'FRI-SUN MAY 16-18'              -> [May 16, 17, 18]
      'FRI & SAT MAY 30 & 31'          -> [May 30, 31]
      'December 4, 5 & 6'              -> [Dec 4, 5, 6]
      'THURSDAY NOVEMBER 12'           -> [Nov 12]
    """
    t = re.sub(_DAYNAME, " ", (text or "").lower())
    m = re.search(_MONTH + r"\s+([\d,&\-–\sand]+)", t)
    if not m:
        return []
    month = month_num(m.group(1))
    nums = m.group(2)
    days = []
    rng = re.match(r"\s*(\d{1,2})\s*[-–]\s*(\d{1,2})", nums)
    if rng:
        a, b = int(rng.group(1)), int(rng.group(2))
        days = list(range(a, b + 1)) if a <= b else [a]
    else:
        days = [int(d) for d in re.findall(r"\d{1,2}", nums)]
    out = []
    for d in days:
        date = infer_year(month, d, today)
        if date and date not in out:
            out.append(date)
    return out


def record(venue, title, date, *, show_time=None, doors_time=None, set_times=None, subtitle=None,
           url="", ticket_url=None, price=None, source="html", room=None):
    """The one record shape every scraper returns."""
    set_times = list(set_times or [])
    show_time = show_time or (set_times[0] if set_times else None)
    rec = {
        "venue": venue,
        "title": (title or "").strip(),
        "subtitle": (subtitle or None) and subtitle.strip() or None,
        "date": date.isoformat() if isinstance(date, dt.date) else date,
        "show_time": show_time,
        "doors_time": doors_time,
        "set_times": set_times,
        "url": url,
        "ticket_url": ticket_url or None,
        "price": price or None,
        "source": source,
        "needs_manual": show_time is None,
    }
    if room:
        rec["room"] = room
    return rec
