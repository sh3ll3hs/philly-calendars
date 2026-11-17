"""Queer in AI — conference workshops and socials read from the News block on
https://www.queerinai.com/ and conference subpages like https://www.queerinai.com/neurips-2026.
"""
import datetime as dt
import re
from bs4 import BeautifulSoup

import combined_to_ics as C
from combined_readers import qt_common as Q

CONF_RE = re.compile(
    r"([A-Za-z0-9\s\-]+?)\s*\(([A-Za-z]+)\s+(\d{1,2})\s*[-–]\s*(\d{1,2})\)\s*:\s*([^\.]+)"
)


def parse(html_text: str, src: dict, today: dt.date | None = None, base_url: str = "https://www.queerinai.com/") -> list[dict]:
    today = today or dt.datetime.now(Q.EASTERN).date()
    soup = BeautifulSoup(html_text, "html.parser")
    events, seen = [], set()
    for li in soup.find_all("li"):
        text = " ".join(li.stripped_strings)
        match = CONF_RE.search(text)
        if not match:
            continue
        conf_name, month_str, start_day, end_day, summary = match.groups()
        if ":" in conf_name:
            conf_name = conf_name.rsplit(":", 1)[-1]
        conf_name = conf_name.strip()
        summary = summary.split("We will be hosting")[0].strip() or summary.strip()
        year_match = re.search(r"20\d{2}", conf_name)
        year = int(year_match.group(0)) if year_match else today.year
        dt_start = dt.datetime.strptime(f"{month_str} {start_day} {year}", "%B %d %Y").date()
        dt_end = dt.datetime.strptime(f"{month_str} {end_day} {year}", "%B %d %Y").date()
        if dt_end < today:
            continue
        dedup_key = (conf_name.lower(), dt_start)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        link_tag = li.find("a", href=True)
        event_url = (
            f"https://www.queerinai.com{link_tag['href']}"
            if link_tag and link_tag["href"].startswith("/")
            else (link_tag["href"] if link_tag else base_url)
        )
        venue_match = re.search(r"venues\s*\(([^)]+)\)", text, re.IGNORECASE)
        location = venue_match.group(1) if venue_match else "See conference page"
        title = f"Queer in AI @ {conf_name}: {summary}"
        e = C.event(src, f"{title}|{dt_start}", title, dt_start, dt_end, True, location, event_url, "")
        if e:
            events.append(e)
    return events


def scrape_queer_in_ai(src: dict | None = None, today: dt.date | None = None) -> list[dict]:
    src = src or {"id": "qt_queerinai", "name": "Queer in AI", "url": "https://www.queerinai.com/"}
    url = src.get("url") or "https://www.queerinai.com/"
    html_text = C.get_text(url)
    return parse(html_text, src, today=today, base_url=url)


def read(src, ctx):
    return scrape_queer_in_ai(src=src, today=ctx["today"])
