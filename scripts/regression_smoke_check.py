#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common_cli import emit_json, parse_flexible_date, resolve_source_repo, verified_priced_rows, verify_date_order, verify_return_offset
from price_alerts import build_notification, compute_dedupe_key, make_rule, now_iso


def _build_args(**overrides) -> Namespace:
    defaults = {
        "origin": "김포",
        "destination": "제주",
        "destinations": None,
        "departure": "2026-03-25",
        "return_date": None,
        "date_range": None,
        "return_offset": 0,
        "adults": 1,
        "cabin": "ECONOMY",
        "target_price": 100000,
        "label": None,
        "time_pref": None,
        "depart_after": None,
        "return_after": None,
        "exclude_early_before": None,
        "prefer": None,
        "rule_id": None,
        "message_template": None,
        "notes": None,
        "repo_path": None,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def test_verified_rows_exclude_broad_only() -> dict:
    rows = [
        {"price": 90000, "search_stage": "broad_only", "time_pref_match": None},
        {"price": 95000, "search_stage": "fallback", "time_pref_match": True},
        {"price": 98000, "search_stage": "refine", "time_pref_match": False},
    ]
    verified = verified_priced_rows(rows, time_pref_active=True)
    assert [row["price"] for row in verified] == [95000]
    return {"verified_prices": [row["price"] for row in verified]}


def test_single_date_return_offset_rule_promotes_date_range() -> dict:
    rule = make_rule(_build_args(return_offset=2))
    assert rule["query"]["date_range"] == {"start_date": "2026-03-25", "end_date": "2026-03-25"}
    assert rule["query"]["departure"] is None
    assert rule["query"]["return_offset"] == 2
    return {"query": rule["query"]}


def test_round_trip_dedupe_uses_return_fields() -> dict:
    rule = {
        "id": "kdf-test",
        "label": "왕복 테스트",
        "query": {
            "origin": "GMP",
            "destination": "CJU",
            "destinations": ["CJU"],
            "departure": "2026-03-25",
            "return_date": "2026-03-27",
            "date_range": None,
            "return_offset": 0,
            "adults": 1,
            "cabin": "ECONOMY",
            "time_preference": {},
        },
        "target_price_krw": 100000,
        "notify": {},
    }
    base = {
        "matched": True,
        "observed_price_krw": 95000,
        "search_type": "single_date",
        "best_option": {
            "destination": "CJU",
            "destination_label": "제주(CJU)",
            "departure_date": "2026-03-25",
            "return_date": "2026-03-27",
            "airline": "대한항공",
            "departure_time": "09:00",
            "arrival_time": "10:10",
            "return_airline": "대한항공",
            "return_departure_time": "19:00",
            "return_arrival_time": "20:10",
        },
    }
    changed = json.loads(json.dumps(base))
    changed["best_option"]["return_departure_time"] = "20:00"
    changed["best_option"]["return_airline"] = "아시아나항공"
    key_a = compute_dedupe_key(rule, base)
    key_b = compute_dedupe_key(rule, changed)
    assert key_a != key_b
    message = build_notification(rule, changed)
    assert "오는편 항공사" in message
    assert "오는편 시간" in message
    return {"key_a": key_a, "key_b": key_b}


def test_kst_time_and_date_helpers() -> dict:
    with mock.patch("common_cli.seoul_now", return_value=datetime(2026, 3, 25, 15, 0, tzinfo=ZoneInfo("Asia/Seoul"))):
        assert parse_flexible_date("오늘").strftime("%Y-%m-%d") == "2026-03-25"
        assert parse_flexible_date("내일").strftime("%Y-%m-%d") == "2026-03-26"
    assert now_iso().endswith("+09:00")
    return {"now_iso": now_iso()}


def test_repo_resolution_works_for_standalone_layout() -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        repo_root = root / "korea-domestic-flights-skill"
        scripts_dir = repo_root / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        source_repo = root / "tmp" / "Scraping-flight-information"
        source_repo.mkdir(parents=True, exist_ok=True)
        resolved = resolve_source_repo(script_path=scripts_dir / "search_domestic.py")
        assert resolved == source_repo
        return {"resolved": str(resolved)}


def test_input_validation_rejects_bad_ranges() -> dict:
    try:
        verify_date_order("2026-03-25", "2026-03-24")
    except ValueError as exc:
        date_error = str(exc)
    else:
        raise AssertionError("verify_date_order should reject return_date before departure")

    try:
        verify_return_offset(-1)
    except ValueError as exc:
        offset_error = str(exc)
    else:
        raise AssertionError("verify_return_offset should reject negative values")

    return {"date_error": date_error, "offset_error": offset_error}


def main() -> None:
    results = {
        "verified_rows_exclude_broad_only": test_verified_rows_exclude_broad_only(),
        "single_date_return_offset_rule_promotes_date_range": test_single_date_return_offset_rule_promotes_date_range(),
        "round_trip_dedupe_uses_return_fields": test_round_trip_dedupe_uses_return_fields(),
        "kst_time_and_date_helpers": test_kst_time_and_date_helpers(),
        "repo_resolution_works_for_standalone_layout": test_repo_resolution_works_for_standalone_layout(),
        "input_validation_rejects_bad_ranges": test_input_validation_rejects_bad_ranges(),
    }
    emit_json(results)


if __name__ == "__main__":
    main()
