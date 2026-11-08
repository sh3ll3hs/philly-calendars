"""Polite HTTP session shared by every venue scraper.

- A real browser User-Agent and Accept-Language (some sites reject the default
  python-requests client outright).
- Retries with exponential backoff on connection errors and 429/5xx.
- At least DELAY seconds between requests to the same domain.

Deliberately NOT here: browser-fingerprint headers (Sec-Fetch-*, faked Referer)
or anything else meant to get past a site's bot protection. If a site answers
403/406 to an honest request, the scraper reports it and moves on.
"""
import threading
import time
import urllib.parse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
DELAY = 1.5  # seconds between requests to one domain
TIMEOUT = 30

_last_hit = {}
_lock = threading.Lock()


class BlockedError(RuntimeError):
    """The site refused an ordinary request (403/406). Not retried, not worked around."""


def session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    retry = Retry(total=3, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET",), respect_retry_after_header=True)
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


_SESSION = session()


def _wait(url):
    host = urllib.parse.urlsplit(url).netloc
    with _lock:
        gap = time.monotonic() - _last_hit.get(host, 0)
        if gap < DELAY:
            time.sleep(DELAY - gap)
        _last_hit[host] = time.monotonic()


def get(url, **kw):
    """GET with per-domain politeness. Raises BlockedError on 403/406."""
    _wait(url)
    r = _SESSION.get(url, timeout=kw.pop("timeout", TIMEOUT), **kw)
    if r.status_code in (403, 406):
        raise BlockedError(f"{r.status_code} from {urllib.parse.urlsplit(url).netloc}")
    r.raise_for_status()
    return r


def get_text(url, **kw):
    return get(url, **kw).text


def get_json(url, **kw):
    headers = {"Accept": "application/json", **kw.pop("headers", {})}
    return get(url, headers=headers, **kw).json()
