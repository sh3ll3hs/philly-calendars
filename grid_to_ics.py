#!/usr/bin/env python3
"""grid_to_ics.py — kept for compatibility; Grid is now one of the sites in tribe_to_ics.py.

    python3 grid_to_ics.py --out docs/grid.ics      ==      python3 tribe_to_ics.py grid --out docs/grid.ics
"""
import sys

from tribe_to_ics import main

if __name__ == "__main__":
    sys.exit(main(["grid"] + sys.argv[1:]))
