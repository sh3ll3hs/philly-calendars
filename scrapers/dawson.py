"""Dawson Street Pub, Manayunk.

Source: the pub's own static page http://beta.dawsonstreetpub.com/index.php (one
request per run). The www host doesn't load; the beta host has no robots.txt.
    <div id="eventschedule"> ... <tr><td><span class='schedule_month'>NOV</span><br />
      <span class='schedule_day'>13</span></td><td><span class='schedule_description'>Act</span></td></tr>
One description cell can hold several acts on separate lines. Times are almost
never listed, so most records are needs_manual - by design; no time is invented.
Raises if #eventschedule disappears, rather than quietly returning nothing.
"""
import datetime as dt
import re
import sys

from bs4 import BeautifulSoup

from common import http
from common.normalize import first_time, infer_year, month_num, record

VENUE = "Dawson Street Pub"
URL = "http://beta.dawsonstreetpub.com/index.php"
TIME = re.compile(r"\b\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?\b", re.I)


def parse(html, today=None):
    today = today or dt.date.today()
    box = BeautifulSoup(html, "html.parser").select_one("#eventschedule")
    if not box:
        raise RuntimeError("dawson: #eventschedule missing - page layout changed")
    out = []
    for tr in box.select("table tr"):
        mo, dy, ds = (tr.select_one(s) for s in (".schedule_month", ".schedule_day", ".schedule_description"))
        if not (mo and dy and ds):
            continue
        d = infer_year(month_num(mo.get_text(strip=True)), int(dy.get_text(strip=True)), today, lookback_days=7)
        if not d:
            continue
        for line in (l.strip() for l in ds.get_text("\n").split("\n")):
            if not line:
                continue
            out.append(record(VENUE, TIME.sub("", line).strip(" -"), d, show_time=first_time(line),
                              url=URL, source="html"))
    return out


def fetch():
    return parse(http.get_text(URL))


if __name__ == "__main__":
    ev = fetch()
    print(len(ev), "records;", sum(e["needs_manual"] for e in ev), "need manual")
    for e in ev[:3]:
        print(e)
    sys.exit(0)
