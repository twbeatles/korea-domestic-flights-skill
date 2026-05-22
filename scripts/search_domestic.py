#!/usr/bin/env python3
from __future__ import annotations

import sys

from _bootstrap import ensure_src_path

ensure_src_path()

from korea_flights.legacy import main_for_script


if __name__ == "__main__":
    raise SystemExit(main_for_script("search_domestic.py", sys.argv[1:]))
