#!/usr/bin/env python3
from __future__ import annotations

import sys

from _bootstrap import ensure_src_path

ensure_src_path()

from korea_flights.legacy import build_dispatch, main_for_script

__all__ = ["build_dispatch"]


if __name__ == "__main__":
    raise SystemExit(main_for_script("chat_search.py", sys.argv[1:]))
