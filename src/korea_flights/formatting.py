from __future__ import annotations

import json
import sys
from collections.abc import Sequence

from .airports import airport_label, route_scope_label
from .results import benefit_text, build_price_calendar, format_price


def cabin_label(code: str) -> str:
    return {
        "ECONOMY": "이코노미",
        "BUSINESS": "비즈니스",
        "FIRST": "일등석",
    }.get((code or "").upper(), code or "")


def format_time_or_fallback(value: str | None, fallback: str = "시간 정보 없음") -> str:
    text = str(value or "").strip()
    return text or fallback


def join_nonempty(parts: Sequence[str | None], sep: str = " · ") -> str:
    return sep.join(str(part) for part in parts if part)


def summarize_price_gap(best_price: int, next_price: int | None) -> str | None:
    if not best_price or not next_price or next_price <= best_price:
        return None
    gap = next_price - best_price
    ratio = round((gap / best_price) * 100)
    return f"2위보다 {gap:,}원 저렴합니다{f' (약 {ratio}% 차이)' if ratio >= 5 else ''}."


def recommendation_line(subject: str, best_price: int, next_price: int | None = None) -> str:
    gap = summarize_price_gap(best_price, next_price)
    if gap:
        return f"추천: 이번 조건에서는 {subject}이(가) 가장 유리합니다. {gap}"
    return f"추천: 이번 조건에서는 {subject}이(가) 가장 무난한 최저가 선택입니다."


def option_text(item: dict) -> str:
    if not item:
        return ""
    if item.get("destination_label"):
        subject = item.get("destination_label")
    else:
        subject = item.get("airline") or "옵션"
    time_bits = []
    if item.get("departure_time") or item.get("arrival_time"):
        time_bits.append(join_nonempty([format_time_or_fallback(item.get("departure_time")), item.get("arrival_time")], " -> "))
    if item.get("return_departure_time") or item.get("return_arrival_time"):
        time_bits.append("오는편 " + join_nonempty([format_time_or_fallback(item.get("return_departure_time")), item.get("return_arrival_time")], " -> "))
    return join_nonempty(
        [
            subject,
            item.get("departure_date"),
            f"~{item.get('return_date')}" if item.get("return_date") else None,
            format_price(item.get("price", 0)),
            benefit_text(item),
            item.get("airline") if item.get("destination_label") else None,
            join_nonempty(time_bits),
        ]
    )


def build_single_summary(query: dict, results: list[dict], route_scope: str) -> dict:
    route = f"{airport_label(query['origin'])} -> {airport_label(query['destination'])}"
    best = results[0] if results else None
    second = results[1]["price"] if len(results) > 1 else None
    return {
        "headline": (
            f"{route} 최저가 {format_price(best['price'])}" if best else f"{route} 검색 결과가 없습니다."
        ),
        "route": route,
        "trip_type": "왕복" if query.get("return_date") else "편도",
        "route_scope": route_scope,
        "best_option": best,
        "top_options": results[:5],
        "recommendation": recommendation_line(option_text(best), int(best.get("price", 0)), second) if best else None,
    }


def build_range_summary(query: dict, rows: list[dict], ranked: list[dict], metadata: dict, diagnostics: dict | None) -> dict:
    best = ranked[0] if ranked else None
    second = ranked[1]["price"] if len(ranked) > 1 else None
    route = f"{airport_label(query['origin'])} -> {airport_label(query['destination'])}"
    return {
        "headline": (
            f"{route} 날짜범위 최저가 {format_price(best['price'])}" if best else f"{route} 날짜범위 검색 결과가 없습니다."
        ),
        "route_scope": query["route_scope"],
        "range": f"{query['start_date']} ~ {query['end_date']}",
        "best_date": best,
        "top_dates": ranked[:7],
        "price_calendar": build_price_calendar(rows),
        "unverified_candidates": metadata.get("unverified_candidates", []),
        "recommendation": recommendation_line(option_text(best), int(best.get("price", 0)), second) if best else None,
        "diagnostic_hint": (diagnostics or {}).get("human_hint"),
    }


def build_matrix_summary(query: dict, rows: list[dict], ranked: list[dict], metadata: dict, diagnostics: dict | None) -> dict:
    best = ranked[0] if ranked else None
    second = ranked[1]["price"] if len(ranked) > 1 else None
    by_destination = []
    for destination in query["destinations"]:
        dest_rows = [row for row in rows if row.get("destination") == destination]
        dest_ranked = [row for row in ranked if row.get("destination") == destination]
        by_destination.append(
            {
                "destination": destination,
                "destination_label": airport_label(destination),
                "best_option": dest_ranked[0] if dest_ranked else None,
                "top_dates": dest_ranked[:3],
                "price_calendar": build_price_calendar(dest_rows),
            }
        )
    by_destination.sort(key=lambda item: int((item.get("best_option") or {}).get("price", 10**12) or 10**12))
    return {
        "headline": (
            f"{airport_label(query['origin'])} 출발 최적 조합은 {best['destination_label']} {best['departure_date']} {format_price(best['price'])}"
            if best
            else f"{airport_label(query['origin'])} 출발 목적지+날짜 범위 검색 결과가 없습니다."
        ),
        "route_scope": query["route_scope"],
        "range": f"{query['start_date']} ~ {query['end_date']}",
        "best_combo": best,
        "top_combos": ranked[:10],
        "by_destination": by_destination,
        "unverified_candidates": metadata.get("unverified_candidates", []),
        "recommendation": recommendation_line(option_text(best), int(best.get("price", 0)), second) if best else None,
        "diagnostic_hint": (diagnostics or {}).get("human_hint"),
    }


def emit_json(payload: dict) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def format_human(payload: dict) -> str:
    query = payload.get("query", {})
    summary = payload.get("summary", {})
    lines = [summary.get("headline") or payload.get("status", "")]
    if query:
        common = [
            f"조건: {route_scope_label(query.get('scope') or query.get('route_scope'))}",
            f"성인 {query.get('adults', 1)}명",
            cabin_label(query.get("cabin", "ECONOMY")),
        ]
        lines.append(" · ".join(common))
    if payload.get("strategy_metadata"):
        meta = payload["strategy_metadata"]
        lines.append(
            f"검색 방식: {' -> '.join(meta.get('pipeline', []))} · broad {meta.get('broad_count', 0)} · refined {meta.get('refined_count', 0)}"
        )
    if summary.get("diagnostic_hint"):
        lines.append(f"참고: {summary['diagnostic_hint']}")
    if summary.get("recommendation"):
        lines.append("")
        lines.append("[추천]")
        lines.append(summary["recommendation"])
    top_key = "top_combos" if "top_combos" in summary else ("top_dates" if "top_dates" in summary else "top_options")
    top_rows = summary.get(top_key) or []
    if top_rows:
        lines.append("")
        lines.append("[상위 결과]")
        for idx, row in enumerate(top_rows[:7], start=1):
            lines.append(f"{idx}. {option_text(row)}")
    unverified = summary.get("unverified_candidates") or []
    if unverified:
        lines.append("")
        lines.append("[빠른 스캔 후보]")
        for idx, row in enumerate(unverified[:5], start=1):
            lines.append(f"{idx}. {option_text(row)} (미검증)")
    return "\n".join(lines)
