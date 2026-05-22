from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .airports import airport_label, infer_routes_scope, normalize_airport, resolve_route_scope, unique_codes
from .dates import parse_date_range_text, parse_flexible_date, pretty_date, seoul_now, verify_date_order, verify_return_offset
from .formatting import cabin_label
from .results import format_price
from .source import resolve_source_repo
from .strategy import HybridStrategyEngine, StrategyLimits
from .timeprefs import describe_time_preference_payload

STORE_VERSION = 4
KST_LABEL = "Asia/Seoul"
DEFAULT_STORE = Path("price-alert-rules.json")
DEFAULT_MESSAGE_TEMPLATE = """[항공권 가격 알림] {label}
- 노선: {route}
- 조건: 성인 {adults}명 · {cabin_label}
- 목표가: {target_price}
- 확인된 최저가: {observed_price}
- 일정: {date_text}{best_destination_line}{airline_line}{time_line}
- 상태: {status_line}"""


def now_iso() -> str:
    return seoul_now().isoformat(timespec="seconds")


def _infer_query_scope(query: dict[str, Any]) -> str:
    origin = str(query.get("origin") or "").strip().upper()
    destinations = query.get("destinations") or ([query.get("destination")] if query.get("destination") else [])
    normalized_destinations = [str(code).strip().upper() for code in destinations if str(code or "").strip()]
    if not origin or not normalized_destinations:
        return "auto"
    return infer_routes_scope(origin, normalized_destinations)


def _migrate_rule(rule: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(rule)
    query = dict(migrated.get("query") or {})
    migrated["query"] = query
    notify = dict(migrated.get("notify") or {})
    migrated["notify"] = notify
    meta = dict(migrated.get("meta") or {})
    migrated["meta"] = meta
    notify.setdefault("channel", "stdout")
    notify.setdefault("dedupe_key", None)
    notify.setdefault("last_sent_at", None)
    notify.setdefault("message_template", None)
    meta.setdefault("source", "korea_flights.alerts")
    meta.setdefault("notes", "")
    if query.get("destinations"):
        query["destinations"] = [str(code).strip().upper() for code in query["destinations"] if str(code or "").strip()]
    elif query.get("destination"):
        query["destinations"] = [str(query["destination"]).strip().upper()]
    else:
        query["destinations"] = []
    query["destination"] = query["destinations"][0] if len(query["destinations"]) == 1 else query.get("destination")
    query["scope"] = str(query.get("scope") or _infer_query_scope(query))
    query.setdefault("time_preference", {})
    return migrated


def load_store(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": STORE_VERSION, "timezone": KST_LABEL, "updated_at": now_iso(), "rules": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    data["version"] = STORE_VERSION
    data.setdefault("timezone", KST_LABEL)
    data["rules"] = [_migrate_rule(rule) for rule in data.get("rules", []) if isinstance(rule, dict)]
    return data


def save_store(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["version"] = STORE_VERSION
    data["updated_at"] = now_iso()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def canonical_signature(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _parse_destinations(args) -> list[str]:
    if getattr(args, "destinations", None):
        return unique_codes([normalize_airport(item.strip()) for item in args.destinations.split(",") if item.strip()])
    if getattr(args, "destination", None):
        return [normalize_airport(args.destination)]
    raise ValueError("--destination 또는 --destinations 가 필요합니다.")


def make_rule(args) -> dict[str, Any]:
    origin = normalize_airport(args.origin)
    destinations = _parse_destinations(args)
    route_scope = resolve_route_scope(origin, destinations, getattr(args, "scope", "auto"))
    if getattr(args, "date_range", None) and getattr(args, "return_date", None):
        raise ValueError("--date-range 와 --return-date 는 함께 사용할 수 없습니다.")
    if getattr(args, "return_date", None) and getattr(args, "return_offset", 0) > 0:
        raise ValueError("--return-date 와 --return-offset 는 함께 사용할 수 없습니다.")
    stored_source_repo = None
    if getattr(args, "repo_path", None):
        stored_source_repo = str(resolve_source_repo(args.repo_path))

    return_offset = int(getattr(args, "return_offset", 0) or 0)
    if getattr(args, "date_range", None):
        start_dt, end_dt = parse_date_range_text(args.date_range)
        if end_dt < start_dt:
            raise ValueError("date-range 의 종료일은 시작일과 같거나 이후여야 합니다.")
        verify_return_offset(return_offset)
        departure = None
        return_date = None
        date_range = {"start_date": pretty_date(start_dt), "end_date": pretty_date(end_dt)}
    else:
        departure = pretty_date(parse_flexible_date(args.departure))
        return_date = pretty_date(parse_flexible_date(args.return_date)) if getattr(args, "return_date", None) else None
        verify_date_order(departure, return_date)
        if return_offset > 0 and not return_date:
            date_range = {"start_date": departure, "end_date": departure}
            departure = None
        else:
            verify_return_offset(return_offset)
            date_range = None

    trip_type = "round_trip" if return_date or return_offset > 0 else "one_way"
    date_label = f"{date_range['start_date']}~{date_range['end_date']}" if date_range else departure
    destination_label = airport_label(destinations[0]) if len(destinations) == 1 else ", ".join(airport_label(code) for code in destinations)
    time_preference = {
        "time_pref": getattr(args, "time_pref", None),
        "depart_after": getattr(args, "depart_after", None),
        "return_after": getattr(args, "return_after", None),
        "exclude_early_before": getattr(args, "exclude_early_before", None),
        "prefer": getattr(args, "prefer", None),
    }
    fingerprint_payload = {
        "origin": origin,
        "destinations": destinations,
        "departure": departure,
        "return_date": return_date,
        "date_range": date_range,
        "return_offset": return_offset,
        "adults": args.adults,
        "cabin": args.cabin,
        "scope": args.scope if getattr(args, "scope", "auto") != "auto" else route_scope,
        "trip_type": trip_type,
        "target_price_krw": args.target_price,
        "time_preference": time_preference,
    }
    return {
        "id": getattr(args, "rule_id", None) or f"kf-{uuid.uuid4().hex[:8]}",
        "enabled": True,
        "label": getattr(args, "label", None) or f"{airport_label(origin)}->{destination_label} {date_label}",
        "fingerprint": canonical_signature(fingerprint_payload),
        "query": {
            "origin": origin,
            "destination": destinations[0] if len(destinations) == 1 else None,
            "destinations": destinations,
            "departure": departure,
            "return_date": return_date,
            "date_range": date_range,
            "return_offset": return_offset,
            "adults": args.adults,
            "cabin": args.cabin,
            "scope": args.scope if getattr(args, "scope", "auto") != "auto" else route_scope,
            "trip_type": trip_type,
            "time_preference": time_preference,
            "source_repo_path": stored_source_repo,
        },
        "target_price_krw": args.target_price,
        "created_at": now_iso(),
        "last_checked_at": None,
        "last_result": None,
        "notify": {
            "channel": "stdout",
            "dedupe_key": None,
            "last_sent_at": None,
            "message_template": getattr(args, "message_template", None) or None,
        },
        "meta": {"source": "korea_flights.alerts", "notes": getattr(args, "notes", None) or ""},
    }


def describe_rule(rule: dict[str, Any]) -> str:
    q = rule["query"]
    destinations = q.get("destinations") or ([q["destination"]] if q.get("destination") else [])
    if q.get("date_range"):
        date_text = f"{q['date_range']['start_date']}~{q['date_range']['end_date']}"
        if q.get("return_offset"):
            date_text += f" (귀국 +{q['return_offset']}일)"
    else:
        date_text = q.get("departure") or ""
        if q.get("return_date"):
            date_text += f" ~ {q['return_date']}"
    time_pref_text = describe_time_preference_payload(q.get("time_preference") or {})
    time_line = f"\n- 시간 조건: {time_pref_text}" if time_pref_text else ""
    return (
        f"[{'ON' if rule.get('enabled', True) else 'OFF'}] {rule['id']} | {rule['label']}\n"
        f"- 노선: {airport_label(q['origin'])} -> {', '.join(airport_label(code) for code in destinations)}\n"
        f"- scope: {q.get('scope') or _infer_query_scope(q)}\n"
        f"- 일정: {date_text}\n"
        f"- 조건: 성인 {q['adults']}명 · {cabin_label(q['cabin'])} · 목표가 {format_price(rule['target_price_krw'])}{time_line}"
    )


def check_rule(rule: dict[str, Any], *, repo_path: str | None = None, limits: StrategyLimits | None = None) -> dict[str, Any]:
    q = rule["query"]
    destinations = q.get("destinations") or ([q["destination"]] if q.get("destination") else [])
    effective_repo_path = repo_path or q.get("source_repo_path")
    engine = HybridStrategyEngine(repo_path=effective_repo_path, limits=limits)
    tp = q.get("time_preference") or {}
    common = {
        "origin": q["origin"],
        "scope": q.get("scope", "auto"),
        "adults": q["adults"],
        "cabin": q["cabin"],
        "time_pref": tp.get("time_pref"),
        "depart_after": tp.get("depart_after"),
        "return_after": tp.get("return_after"),
        "exclude_early_before": tp.get("exclude_early_before"),
        "prefer": tp.get("prefer"),
    }
    if len(destinations) > 1 or q.get("date_range"):
        if len(destinations) == 1:
            payload = engine.search_range(
                **common,
                destination=destinations[0],
                start_date=(q.get("date_range") or {}).get("start_date"),
                end_date=(q.get("date_range") or {}).get("end_date"),
                return_offset=q.get("return_offset", 0),
            )
            best = payload.get("summary", {}).get("best_date")
            search_type = "date_range"
        else:
            date_range = q.get("date_range") or {"start_date": q.get("departure"), "end_date": q.get("departure")}
            payload = engine.search_matrix(
                **common,
                destinations=destinations,
                start_date=date_range.get("start_date"),
                end_date=date_range.get("end_date"),
                return_offset=q.get("return_offset", 0),
            )
            best = payload.get("summary", {}).get("best_combo")
            search_type = "matrix"
    else:
        payload = engine.search_single(
            **common,
            destination=destinations[0],
            departure=q["departure"],
            return_date=q.get("return_date"),
        )
        best = payload.get("summary", {}).get("best_option")
        search_type = "single"
    observed = int((best or {}).get("price", 0) or 0)
    return {
        "matched": bool(best and observed and observed <= rule["target_price_krw"]),
        "observed_price_krw": observed,
        "best_option": best,
        "search_type": search_type,
        "raw_summary": payload.get("summary"),
    }


def build_notification_context(rule: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    q = rule["query"]
    best = result.get("best_option") or {}
    destinations = q.get("destinations") or ([q["destination"]] if q.get("destination") else [])
    observed = int(result.get("observed_price_krw", 0) or 0)
    target = int(rule["target_price_krw"])
    departure_date = best.get("departure_date") or q.get("departure") or (q.get("date_range") or {}).get("start_date")
    return_date = best.get("return_date") or q.get("return_date")
    date_text = str(departure_date or "")
    if return_date:
        date_text += f" ~ {return_date}"
    best_destination_label = best.get("destination_label") or (airport_label(best.get("destination")) if best.get("destination") else "")
    airline = best.get("airline") or ""
    return_airline = best.get("return_airline") or ""
    time_bits = []
    if best.get("departure_time"):
        time_bits.append(f"\n- 가는편 시간: {best.get('departure_time')}")
    if best.get("return_departure_time"):
        time_bits.append(f"\n- 오는편 시간: {best.get('return_departure_time')}")
    return {
        "rule_id": rule["id"],
        "label": rule["label"],
        "route": f"{airport_label(q['origin'])} -> {', '.join(airport_label(code) for code in destinations)}",
        "adults": q["adults"],
        "cabin": q["cabin"],
        "cabin_label": cabin_label(q["cabin"]),
        "target_price": format_price(target),
        "target_price_krw": target,
        "observed_price": format_price(observed),
        "observed_price_krw": observed,
        "difference_krw": target - observed,
        "date_text": date_text,
        "best_destination_label": best_destination_label,
        "best_destination_line": f"\n- 최적 목적지: {best_destination_label}" if best_destination_label else "",
        "airline": airline,
        "return_airline": return_airline,
        "airline_line": (
            f"\n- 가는편 항공사: {airline}\n- 오는편 항공사: {return_airline}"
            if airline and return_airline
            else (f"\n- 항공사: {airline}" if airline else "")
        ),
        "time_line": "".join(time_bits),
        "status_line": f"목표가 충족 ({target - observed:,}원 여유)" if target >= observed else f"목표가 초과 ({observed - target:,}원 초과)",
    }


def _safe_format(template: str, context: dict[str, Any]) -> str:
    class SafeDict(dict):
        def __missing__(self, key):
            return ""

    return template.format_map(SafeDict({key: "" if value is None else value for key, value in context.items()})).strip()


def compute_dedupe_key(rule: dict[str, Any], result: dict[str, Any]) -> str:
    best = result.get("best_option") or {}
    return canonical_signature(
        {
            "rule_id": rule["id"],
            "search_type": result.get("search_type"),
            "observed_price_krw": result.get("observed_price_krw", 0),
            "destination": best.get("destination"),
            "departure_date": best.get("departure_date"),
            "return_date": best.get("return_date"),
            "airline": best.get("airline"),
            "departure_time": best.get("departure_time"),
            "arrival_time": best.get("arrival_time"),
            "return_airline": best.get("return_airline"),
            "return_departure_time": best.get("return_departure_time"),
            "return_arrival_time": best.get("return_arrival_time"),
        }
    )


def build_notification(rule: dict[str, Any], result: dict[str, Any]) -> str:
    template = rule.get("notify", {}).get("message_template") or DEFAULT_MESSAGE_TEMPLATE
    return _safe_format(template, build_notification_context(rule, result))
