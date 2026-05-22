from __future__ import annotations

import argparse
import sys
from argparse import Namespace

from .cli import main as cli_main
from .dates import parse_date_range_text, pretty_date, return_offset_from_dates


def build_dispatch(args: Namespace) -> tuple[str, list[str]]:
    common = [
        "--origin",
        args.origin,
        "--scope",
        getattr(args, "scope", "auto"),
        "--adults",
        str(getattr(args, "adults", 1)),
        "--cabin",
        getattr(args, "cabin", "ECONOMY"),
    ]
    if getattr(args, "repo_path", None):
        common.extend(["--repo-path", args.repo_path])
    for source_name, flag in [
        ("time_pref", "--time-pref"),
        ("depart_after", "--depart-after"),
        ("return_after", "--return-after"),
        ("exclude_early_before", "--exclude-early-before"),
        ("prefer", "--prefer"),
    ]:
        value = getattr(args, source_name, None)
        if value:
            common.extend([flag, str(value)])
    if getattr(args, "json", False):
        common.append("--json")
    destination_value = getattr(args, "destinations", None) or getattr(args, "destination", None)
    if not destination_value:
        raise SystemExit("--destination 또는 --destinations 가 필요합니다.")
    has_multi_dest = bool(getattr(args, "destinations", None) and "," in args.destinations or (getattr(args, "destinations", None) and getattr(args, "destination", None)))
    if getattr(args, "when", None) and not getattr(args, "departure", None):
        start_dt, end_dt = parse_date_range_text(args.when)
        single_day = start_dt == end_dt
        if has_multi_dest or not single_day or getattr(args, "return_offset", 0) > 0:
            command = "matrix" if has_multi_dest else "range"
            legacy_name = "search_destination_date_matrix.py" if has_multi_dest else "search_date_range.py"
            dest_flag = "--destinations" if has_multi_dest else "--destination"
            return legacy_name, [
                command,
                *common,
                dest_flag,
                destination_value,
                "--start-date",
                pretty_date(start_dt),
                "--end-date",
                pretty_date(end_dt),
                "--return-offset",
                str(getattr(args, "return_offset", 0)),
            ]
        return "search_flights.py", ["search", *common, "--destination", destination_value, "--departure", pretty_date(start_dt)]
    if has_multi_dest:
        command = "matrix"
        extra = [command, *common, "--destinations", destination_value]
        if getattr(args, "departure", None):
            extra.extend(["--departure", args.departure])
        if getattr(args, "return_date", None):
            extra.extend(["--return-date", args.return_date])
        if getattr(args, "return_offset", 0):
            extra.extend(["--return-offset", str(args.return_offset)])
        return "search_destination_date_matrix.py", extra
    if getattr(args, "departure", None) and getattr(args, "return_offset", 0) > 0 and not getattr(args, "return_date", None):
        return "search_date_range.py", [
            "range",
            *common,
            "--destination",
            destination_value,
            "--start-date",
            args.departure,
            "--end-date",
            args.departure,
            "--return-offset",
            str(args.return_offset),
        ]
    if getattr(args, "departure", None):
        extra = ["search", *common, "--destination", destination_value, "--departure", args.departure]
        if getattr(args, "return_date", None):
            extra.extend(["--return-date", args.return_date])
        return "search_flights.py", extra
    raise SystemExit("날짜 정보가 없습니다. --when 또는 --departure 를 제공하세요.")


def parse_chat_args(argv: list[str]) -> Namespace:
    parser = argparse.ArgumentParser(description="Legacy chat-friendly wrapper")
    parser.add_argument("--origin", required=True)
    parser.add_argument("--destination")
    parser.add_argument("--destinations")
    parser.add_argument("--when")
    parser.add_argument("--departure")
    parser.add_argument("--return-date")
    parser.add_argument("--return-offset", type=int, default=0)
    parser.add_argument("--scope", default="auto", choices=["auto", "domestic", "international"])
    parser.add_argument("--adults", type=int, default=1)
    parser.add_argument("--cabin", default="ECONOMY", choices=["ECONOMY", "BUSINESS", "FIRST"])
    parser.add_argument("--time-pref")
    parser.add_argument("--depart-after")
    parser.add_argument("--return-after")
    parser.add_argument("--exclude-early-before")
    parser.add_argument("--prefer", choices=["late", "morning", "afternoon", "evening"])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--repo-path")
    return parser.parse_args(argv)


def main_for_script(script_name: str, argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if script_name in {"search_flights.py", "search_domestic.py"}:
        return cli_main(["search", *argv])
    if script_name == "search_date_range.py":
        return cli_main(["range", *argv])
    if script_name in {"search_destination_date_matrix.py", "search_multi_destination.py"}:
        return cli_main(["matrix", *argv])
    if script_name == "price_alerts.py":
        return cli_main(["alert", *argv])
    if script_name == "hybrid_live_dry_run.py":
        return cli_main(["doctor", *argv, "--json"])
    if script_name == "chat_search.py":
        _, dispatched = build_dispatch(parse_chat_args(argv))
        return cli_main(dispatched)
    raise SystemExit(f"Unknown legacy script: {script_name}")
