from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .alerts import build_notification, check_rule, describe_rule, load_store, make_rule, save_store
from .formatting import emit_json, format_human
from .source import doctor
from .strategy import HybridStrategyEngine, StrategyLimits


def _add_common_search_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scope", default="auto", choices=["auto", "domestic", "international"])
    parser.add_argument("--adults", type=int, default=1)
    parser.add_argument("--cabin", default="ECONOMY", choices=["ECONOMY", "BUSINESS", "FIRST"])
    parser.add_argument("--time-pref")
    parser.add_argument("--depart-after")
    parser.add_argument("--return-after")
    parser.add_argument("--exclude-early-before")
    parser.add_argument("--prefer", choices=["late", "morning", "afternoon", "evening"])
    parser.add_argument("--repo-path")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--human", action="store_true")


def _add_strategy_limit_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--max-days", type=int, default=45)
    parser.add_argument("--max-combos", type=int, default=120)
    parser.add_argument("--refine-budget", type=int, default=8)
    parser.add_argument("--fallback-budget", type=int, default=6)


def _engine(args) -> HybridStrategyEngine:
    return HybridStrategyEngine(
        repo_path=getattr(args, "repo_path", None),
        limits=StrategyLimits(
            max_days=getattr(args, "max_days", 45),
            max_combos=getattr(args, "max_combos", 120),
            refine_budget=getattr(args, "refine_budget", 8),
            fallback_budget=getattr(args, "fallback_budget", 6),
        ),
    )


def _print_payload(payload: dict, *, as_json: bool) -> int:
    if as_json:
        emit_json(payload)
    else:
        print(format_human(payload))
    return 0


def command_search(args) -> int:
    payload = _engine(args).search_single(
        origin=args.origin,
        destination=args.destination,
        departure=args.departure,
        return_date=args.return_date,
        scope=args.scope,
        adults=args.adults,
        cabin=args.cabin,
        max_results=args.max_results,
        time_pref=args.time_pref,
        depart_after=args.depart_after,
        return_after=args.return_after,
        exclude_early_before=args.exclude_early_before,
        prefer=args.prefer,
    )
    return _print_payload(payload, as_json=args.json)


def command_range(args) -> int:
    payload = _engine(args).search_range(
        origin=args.origin,
        destination=args.destination,
        start_date=args.start_date,
        end_date=args.end_date,
        date_range=args.date_range,
        return_offset=args.return_offset,
        scope=args.scope,
        adults=args.adults,
        cabin=args.cabin,
        time_pref=args.time_pref,
        depart_after=args.depart_after,
        return_after=args.return_after,
        exclude_early_before=args.exclude_early_before,
        prefer=args.prefer,
    )
    return _print_payload(payload, as_json=args.json)


def command_matrix(args) -> int:
    destinations = [item.strip() for item in args.destinations.split(",") if item.strip()]
    payload = _engine(args).search_matrix(
        origin=args.origin,
        destinations=destinations,
        start_date=args.start_date,
        end_date=args.end_date,
        date_range=args.date_range,
        departure=args.departure,
        return_date=args.return_date,
        return_offset=args.return_offset,
        scope=args.scope,
        adults=args.adults,
        cabin=args.cabin,
        time_pref=args.time_pref,
        depart_after=args.depart_after,
        return_after=args.return_after,
        exclude_early_before=args.exclude_early_before,
        prefer=args.prefer,
    )
    return _print_payload(payload, as_json=args.json)


def command_doctor(args) -> int:
    try:
        health = doctor(args.repo_path, import_check=args.import_check).to_dict()
    except Exception as exc:
        health = {"ok": False, "error": str(exc)}
    if args.json:
        emit_json({"status": "success" if health.get("ok") else "error", "doctor": health})
    else:
        print("OK" if health.get("ok") else "ERROR")
        print(health.get("repo_path") or health.get("error"))
        if health.get("required_files"):
            for name, ok in health["required_files"].items():
                print(f"- {name}: {'OK' if ok else 'MISSING'}")
        if health.get("import_checked"):
            print(f"- import: {'OK' if health.get('import_ok') else health.get('import_error')}")
    return 0 if health.get("ok") else 1


def command_live_smoke(args) -> int:
    engine = _engine(args)
    departure = args.departure or "30일 뒤"
    checks = []
    for origin, destination, scope in [("GMP", "CJU", "domestic"), ("ICN", "NRT", "international")]:
        try:
            payload = engine.search_single(
                origin=origin,
                destination=destination,
                departure=departure,
                scope=scope,
                max_results=5,
                adults=1,
                cabin="ECONOMY",
            )
            best = payload.get("summary", {}).get("best_option") or {}
            checks.append(
                {
                    "route": f"{origin}->{destination}",
                    "ok": payload.get("status") == "success",
                    "count": len(payload.get("results") or []),
                    "extraction_source": best.get("extraction_source"),
                    "price": best.get("price", 0),
                }
            )
        except Exception as exc:
            checks.append({"route": f"{origin}->{destination}", "ok": False, "error": str(exc)})
    status_ok = all(item.get("ok") for item in checks)
    payload = {"status": "success" if status_ok else "error", "checks": checks}
    return _print_payload(payload, as_json=args.json)


def command_alert_add(args) -> int:
    if not args.date_range and not args.departure:
        raise SystemExit("add 에서는 --departure 또는 --date-range 가 필요합니다.")
    path = Path(args.store)
    data = load_store(path)
    rule = make_rule(args)
    duplicate = next((item for item in data["rules"] if item.get("fingerprint") == rule["fingerprint"]), None)
    if duplicate:
        raise SystemExit(f"중복 규칙입니다. 기존 규칙 id={duplicate['id']} label={duplicate['label']}")
    data["rules"].append(rule)
    save_store(path, data)
    print("규칙 저장 완료")
    print(describe_rule(rule))
    print(f"저장 파일: {path}")
    return 0


def command_alert_list(args) -> int:
    rules = load_store(Path(args.store)).get("rules", [])
    if args.json:
        emit_json({"status": "success", "rules": rules})
        return 0
    if not rules:
        print("저장된 가격 감시 규칙이 없습니다.")
        return 0
    for idx, rule in enumerate(rules, start=1):
        print(f"{idx}. {describe_rule(rule)}")
    return 0


def command_alert_check(args) -> int:
    store_path = Path(args.store)
    data = load_store(store_path)
    matched_messages: list[str] = []
    failures: list[str] = []
    checked = 0
    suppressed = 0
    limits = StrategyLimits(
        max_days=getattr(args, "max_days", 45),
        max_combos=getattr(args, "max_combos", 120),
        refine_budget=getattr(args, "refine_budget", 8),
        fallback_budget=getattr(args, "fallback_budget", 6),
    )
    for rule in data.get("rules", []):
        if not rule.get("enabled", True):
            continue
        if args.rule_id and rule["id"] != args.rule_id:
            continue
        checked += 1
        try:
            result = check_rule(rule, repo_path=args.repo_path, limits=limits)
            rule["last_checked_at"] = __import__("korea_flights.alerts", fromlist=["now_iso"]).now_iso()
            rule["last_result"] = result
            if result["matched"]:
                from .alerts import compute_dedupe_key

                dedupe_key = compute_dedupe_key(rule, result)
                if args.no_dedupe or rule.get("notify", {}).get("dedupe_key") != dedupe_key:
                    matched_messages.append(build_notification(rule, result))
                    rule.setdefault("notify", {})["dedupe_key"] = dedupe_key
                    rule["notify"]["last_sent_at"] = rule["last_checked_at"]
                else:
                    suppressed += 1
        except Exception as exc:
            failures.append(f"{rule['id']}: {exc}")
            rule["last_checked_at"] = __import__("korea_flights.alerts", fromlist=["now_iso"]).now_iso()
            rule["last_result"] = {"matched": False, "error": str(exc)}
    save_store(store_path, data)
    if args.json:
        emit_json({"status": "error" if failures else "success", "checked": checked, "matched": len(matched_messages), "failures": failures, "suppressed": suppressed})
    else:
        if failures:
            print("[점검 오류]", file=sys.stderr)
            for item in failures:
                print(f"- {item}", file=sys.stderr)
        if matched_messages:
            print("\n\n".join(matched_messages))
        else:
            print(f"점검 완료: {checked}개 규칙 확인, 목표가 충족 알림 없음")
    return 0 if not failures else 1


def command_alert_remove(args) -> int:
    path = Path(args.store)
    data = load_store(path)
    before = len(data.get("rules", []))
    data["rules"] = [rule for rule in data.get("rules", []) if rule["id"] != args.rule_id]
    if before == len(data["rules"]):
        raise SystemExit(f"삭제할 규칙을 찾지 못했습니다: {args.rule_id}")
    save_store(path, data)
    print(f"규칙 삭제 완료: {args.rule_id}")
    return 0


def command_alert_render(args) -> int:
    rule = next((item for item in load_store(Path(args.store)).get("rules", []) if item["id"] == args.rule_id), None)
    if not rule:
        raise SystemExit(f"규칙을 찾지 못했습니다: {args.rule_id}")
    if not rule.get("last_result"):
        raise SystemExit("아직 last_result 가 없습니다. 먼저 check 를 실행하세요.")
    print(build_notification(rule, rule["last_result"]))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="korea-flights", description="Korea Flights package CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="single-route search")
    search.add_argument("--origin", required=True)
    search.add_argument("--destination", required=True)
    search.add_argument("--departure", required=True)
    search.add_argument("--return-date")
    search.add_argument("--max-results", type=int, default=20)
    _add_common_search_args(search)
    search.set_defaults(func=command_search)

    range_cmd = sub.add_parser("range", help="date-range search")
    range_cmd.add_argument("--origin", required=True)
    range_cmd.add_argument("--destination", required=True)
    range_cmd.add_argument("--start-date")
    range_cmd.add_argument("--end-date")
    range_cmd.add_argument("--date-range")
    range_cmd.add_argument("--return-offset", type=int, default=0)
    _add_common_search_args(range_cmd)
    _add_strategy_limit_args(range_cmd)
    range_cmd.set_defaults(func=command_range)

    matrix = sub.add_parser("matrix", help="destination/date matrix search")
    matrix.add_argument("--origin", required=True)
    matrix.add_argument("--destinations", required=True)
    matrix.add_argument("--start-date")
    matrix.add_argument("--end-date")
    matrix.add_argument("--date-range")
    matrix.add_argument("--departure")
    matrix.add_argument("--return-date")
    matrix.add_argument("--return-offset", type=int, default=0)
    _add_common_search_args(matrix)
    _add_strategy_limit_args(matrix)
    matrix.set_defaults(func=command_matrix)

    doctor_cmd = sub.add_parser("doctor", help="check source repo wiring")
    doctor_cmd.add_argument("--repo-path")
    doctor_cmd.add_argument("--import-check", action="store_true")
    doctor_cmd.add_argument("--json", action="store_true")
    doctor_cmd.set_defaults(func=command_doctor)

    live = sub.add_parser("live-smoke", help="run shallow live source smoke")
    live.add_argument("--repo-path")
    live.add_argument("--departure")
    live.add_argument("--json", action="store_true")
    _add_strategy_limit_args(live)
    live.set_defaults(func=command_live_smoke)

    alert = sub.add_parser("alert", help="price alert store")
    alert.add_argument("--store", default="price-alert-rules.json")
    alert.add_argument("--repo-path")
    alert_sub = alert.add_subparsers(dest="alert_command", required=True)
    add = alert_sub.add_parser("add")
    add.add_argument("--rule-id")
    add.add_argument("--label")
    add.add_argument("--origin", required=True)
    dest_group = add.add_mutually_exclusive_group(required=True)
    dest_group.add_argument("--destination")
    dest_group.add_argument("--destinations")
    add.add_argument("--departure")
    add.add_argument("--return-date")
    add.add_argument("--date-range")
    add.add_argument("--scope", default="auto", choices=["auto", "domestic", "international"])
    add.add_argument("--return-offset", type=int, default=0)
    add.add_argument("--adults", type=int, default=1)
    add.add_argument("--cabin", default="ECONOMY", choices=["ECONOMY", "BUSINESS", "FIRST"])
    add.add_argument("--target-price", type=int, required=True)
    add.add_argument("--time-pref")
    add.add_argument("--depart-after")
    add.add_argument("--return-after")
    add.add_argument("--exclude-early-before")
    add.add_argument("--prefer", choices=["late", "morning", "afternoon", "evening"])
    add.add_argument("--notes")
    add.add_argument("--message-template")
    add.set_defaults(func=command_alert_add)
    list_cmd = alert_sub.add_parser("list")
    list_cmd.add_argument("--json", action="store_true")
    list_cmd.set_defaults(func=command_alert_list)
    check = alert_sub.add_parser("check")
    check.add_argument("--rule-id")
    check.add_argument("--no-dedupe", action="store_true")
    check.add_argument("--json", action="store_true")
    _add_strategy_limit_args(check)
    check.set_defaults(func=command_alert_check)
    remove = alert_sub.add_parser("remove")
    remove.add_argument("--rule-id", required=True)
    remove.set_defaults(func=command_alert_remove)
    render = alert_sub.add_parser("render")
    render.add_argument("--rule-id", required=True)
    render.set_defaults(func=command_alert_render)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        emit_json({"status": "error", "message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
