#!/usr/bin/env python3
"""Run every venue scraper and write the combined results.

    python3 run_all.py                      # writes data/events.json and data/events.csv
    python3 run_all.py --out-dir docs/venues
    python3 run_all.py --only south,parx

Prints per-venue counts and how many records still have show_time=None, so the
remaining gap is visible. A venue that errors is reported and skipped; the others
still run, and the previous output for that venue is kept rather than wiped.
"""
import argparse
import csv
import importlib
import json
import os
import sys
import traceback

from scrapers import VENUES

FIELDS = ["venue", "title", "subtitle", "date", "show_time", "doors_time", "set_times",
          "url", "ticket_url", "price", "source", "needs_manual", "room"]


def collect(only=None, previous=None):
    """Run the scrapers. Returns (records, per-venue status)."""
    previous = previous or []
    out, status = [], {}
    for name in VENUES:
        if only and name not in only:
            continue
        try:
            recs = importlib.import_module(f"scrapers.{name}").fetch()
            status[name] = ("ok", len(recs))
        except Exception as e:
            print(f"!! {name}: {type(e).__name__}: {e}", file=sys.stderr)
            traceback.print_exc(limit=1, file=sys.stderr)
            mod = importlib.import_module(f"scrapers.{name}")
            venue = getattr(mod, "VENUE", None)
            recs = [r for r in previous if venue and r.get("venue") == venue]  # keep last good data
            status[name] = (f"error, kept {len(recs)} from last run", len(recs))
        out += recs
    return out, status


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default="data")
    ap.add_argument("--only", default="", help="comma-separated scraper names")
    a = ap.parse_args()
    only = {x.strip() for x in a.only.split(",") if x.strip()}

    os.makedirs(a.out_dir, exist_ok=True)
    jpath, cpath = os.path.join(a.out_dir, "events.json"), os.path.join(a.out_dir, "events.csv")
    previous = []
    if os.path.exists(jpath):
        with open(jpath) as f:
            previous = json.load(f)

    recs, status = collect(only, previous)
    recs.sort(key=lambda r: (r["date"] or "", r["show_time"] or "", r["venue"]))
    with open(jpath, "w") as f:
        json.dump(recs, f, indent=1, ensure_ascii=False)
    with open(cpath, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in recs:
            w.writerow({**r, "set_times": " ".join(r.get("set_times") or [])})

    print(f"\n{'scraper':16} {'records':>7} {'no time':>8}  status")
    by_venue = {}
    for r in recs:
        by_venue.setdefault(r["venue"], []).append(r)
    for name, (st, n) in status.items():
        venue = getattr(importlib.import_module(f"scrapers.{name}"), "VENUE", name)
        rs = by_venue.get(venue, []) if name != "livenation_tm" else [r for r in recs if r["source"] == "tm-discovery"]
        print(f"{name:16} {n:>7} {sum(1 for r in rs if not r['show_time']):>8}  {st}")
    print(f"{'TOTAL':16} {len(recs):>7} {sum(1 for r in recs if not r['show_time']):>8}")
    print(f"\nwrote {jpath} and {cpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
