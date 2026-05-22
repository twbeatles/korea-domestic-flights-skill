from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from korea_flights.airports import normalize_airport, resolve_route_scope
from korea_flights.alerts import STORE_VERSION, build_notification, compute_dedupe_key, load_store, make_rule
from korea_flights.cli import build_parser
from korea_flights.diagnostics import choose_fallback_plan
from korea_flights.legacy import build_dispatch
from korea_flights.results import normalize_result_payload
from korea_flights.strategy import HybridStrategyEngine, StrategyLimits


class FakeAdapter:
    def broad_date_range(self, *, origin, destination, dates, return_offset=0, adults=1, cabin_class="ECONOMY", progress_callback=None):
        prices = {
            "20260325": (120000, "대한항공"),
            "20260326": (90000, "진에어"),
            "20260327": (95000, "제주항공"),
            "20260328": (110000, "아시아나항공"),
        }
        return {date: prices.get(date, (0, "N/A")) for date in dates}

    def search(self, *, origin, destination, departure_date, return_date=None, adults=1, cabin_class="ECONOMY", max_results=1000, background_mode=False, progress_callback=None):
        if departure_date == "2026-03-26":
            return [
                {
                    "airline": "진에어",
                    "price": 90000,
                    "departure_time": "19:10",
                    "arrival_time": "20:10",
                    "return_departure_time": "19:30" if return_date else "",
                    "duration": "1h",
                    "stops": 0,
                    "flight_number": "LJ001",
                    "benefit_price": 87000,
                    "benefit_label": "카드혜택",
                    "source": "Interpark",
                    "extraction_source": "domestic_api",
                    "confidence": 0.9,
                }
            ]
        if departure_date == "2026-03-27":
            return [
                {
                    "airline": "제주항공",
                    "price": 95000,
                    "departure_time": "07:10",
                    "arrival_time": "08:10",
                    "source": "Interpark",
                    "extraction_source": "domestic_api",
                    "confidence": 0.8,
                }
            ]
        return []


def _args(**overrides):
    defaults = {
        "origin": "김포",
        "destination": "제주",
        "destinations": None,
        "departure": "2026-03-25",
        "return_date": None,
        "date_range": None,
        "return_offset": 0,
        "scope": "auto",
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


def test_airport_scope_and_result_normalization():
    assert normalize_airport("도쿄") == "TYO"
    assert resolve_route_scope("ICN", ["NRT"], "international") == "international"
    payload = normalize_result_payload({"price": 123, "duration": "2h", "benefit_price": 100})
    assert payload["duration"] == "2h"
    assert payload["benefit_price"] == 100
    assert payload["flight_number"] == ""


def test_cli_parser_exposes_required_subcommands():
    parser = build_parser()
    help_text = parser.format_help()
    assert "search" in help_text
    assert "range" in help_text
    assert "matrix" in help_text
    assert "alert" in help_text
    assert "doctor" in help_text
    assert "live-smoke" in help_text


def test_strategy_engine_range_scores_refines_and_preserves_fields():
    engine = HybridStrategyEngine(source_adapter=FakeAdapter(), limits=StrategyLimits(refine_budget=2, fallback_budget=1))
    payload = engine.search_range(
        origin="GMP",
        destination="CJU",
        start_date="2026-03-25",
        end_date="2026-03-28",
        time_pref="저녁",
    )
    assert payload["status"] == "success"
    assert payload["strategy_metadata"]["pipeline"] == HybridStrategyEngine.pipeline
    assert payload["strategy_metadata"]["broad_count"] == 4
    assert payload["summary"]["best_date"]["departure_date"] == "2026-03-26"
    assert payload["summary"]["best_date"]["duration"] == "1h"
    assert payload["summary"]["best_date"]["benefit_price"] == 87000
    assert payload["summary"]["best_date"]["extraction_source"] == "domestic_api"
    assert payload["strategy_metadata"]["verified_results_required"] is True


def test_strategy_engine_matrix_keeps_unverified_broad_candidates():
    engine = HybridStrategyEngine(source_adapter=FakeAdapter(), limits=StrategyLimits(refine_budget=1, fallback_budget=0))
    payload = engine.search_matrix(
        origin="GMP",
        destinations=["CJU", "PUS"],
        start_date="2026-03-25",
        end_date="2026-03-28",
        time_pref="저녁",
    )
    assert payload["query"]["destinations"] == ["CJU", "PUS"]
    assert payload["strategy_metadata"]["broad_count"] == 8
    assert "unverified_candidates" in payload["summary"]


def test_fallback_plan_triggers_on_shortfall_and_extraction_signal():
    plan = choose_fallback_plan(
        {
            "broad_available": 5,
            "success": 0,
            "remaining_available": 3,
            "rejected": 1,
            "extraction_incomplete": 1,
            "empty_like": 1,
            "rejection_ratio": 0.5,
            "empty_like_ratio": 0.5,
            "extraction_incomplete_ratio": 0.5,
            "dominant_reason": "detail_empty_after_broad_hit",
            "dominant_reason_category": "extraction",
        },
        minimum_target=2,
        hard_cap=4,
        pad=2,
    )
    assert plan["triggered"] is True
    assert "signal.broad_detail_disagreement" in plan["reasons"]


def test_legacy_chat_dispatch_returns_old_names_with_new_cli_args():
    script_name, cli_args = build_dispatch(
        Namespace(
            origin="ICN",
            destination="NRT",
            destinations=None,
            when=None,
            departure="2026-04-20",
            return_date=None,
            return_offset=0,
            scope="international",
            adults=1,
            cabin="ECONOMY",
            time_pref=None,
            depart_after=None,
            return_after=None,
            exclude_early_before=None,
            prefer=None,
            json=True,
            repo_path=None,
        )
    )
    assert script_name == "search_flights.py"
    assert cli_args[:2] == ["search", "--origin"]
    assert "--scope" in cli_args and "international" in cli_args


def test_alert_store_migration_and_round_trip_dedupe(tmp_path: Path):
    store = tmp_path / "alerts.json"
    store.write_text(
        json.dumps(
            {
                "version": 2,
                "timezone": "Asia/Seoul",
                "rules": [
                    {
                        "id": "kf-old",
                        "label": "old",
                        "query": {
                            "origin": "GMP",
                            "destination": "CJU",
                            "departure": "2026-03-25",
                            "return_date": None,
                            "date_range": None,
                            "return_offset": 0,
                            "adults": 1,
                            "cabin": "ECONOMY",
                        },
                        "target_price_krw": 100000,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    migrated = load_store(store)
    assert migrated["version"] == STORE_VERSION
    assert migrated["rules"][0]["query"]["scope"] == "domestic"
    rule = make_rule(_args(return_offset=2))
    assert rule["query"]["date_range"] == {"start_date": "2026-03-25", "end_date": "2026-03-25"}
    result = {
        "matched": True,
        "observed_price_krw": 90000,
        "search_type": "single",
        "best_option": {
            "destination": "CJU",
            "departure_date": "2026-03-25",
            "return_date": "2026-03-27",
            "airline": "대한항공",
            "departure_time": "09:00",
            "arrival_time": "10:00",
            "return_airline": "아시아나항공",
            "return_departure_time": "20:00",
            "return_arrival_time": "21:00",
        },
    }
    changed = json.loads(json.dumps(result))
    changed["best_option"]["return_departure_time"] = "21:00"
    assert compute_dedupe_key(rule, result) != compute_dedupe_key(rule, changed)
    assert "오는편 항공사" in build_notification(rule, result)
