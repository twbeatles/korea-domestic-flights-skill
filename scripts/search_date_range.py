#!/usr/bin/env python3
import argparse
import json
import math
import sys
from dataclasses import asdict, is_dataclass
from datetime import timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common_cli import (
    airport_label,
    build_balanced_option_reasons,
    build_best_option_reasons,
    build_price_calendar,
    cabin_label,
    choose_balanced_round_trip_option,
    explain_recommendation,
    filter_and_rank_by_time_preference,
    format_price,
    normalize_airport,
    parse_date_range_text,
    parse_flexible_date,
    parse_time_preference_args,
    pretty_date,
    recommendation_line,
    round_trip_balance_recommendation,
    time_preference_recommendation,
)


def build_dates(start_date, end_date):
    days = []
    current = start_date
    while current <= end_date:
        days.append(current)
        current += timedelta(days=1)
    return days


def _normalize(item):
    if is_dataclass(item):
        return asdict(item)
    if hasattr(item, "__dict__"):
        return dict(item.__dict__)
    return {"value": str(item)}


def _empty_row(dep, ret, price=0, airline=""):
    return {
        "departure_date": dep,
        "return_date": ret,
        "price": price,
        "airline": airline,
        "departure_time": "",
        "return_departure_time": "",
        "preferred_option": None,
        "time_recommendation": None,
    }


def _choose_refine_dates(dates, broad_rows):
    available = [row for row in broad_rows if row.get("price", 0) and row.get("price", 0) > 0]
    if not available:
        return []
    available.sort(key=lambda x: x["price"])
    index_by_date = {pretty_date(d): idx for idx, d in enumerate(dates)}
    refine_count = min(len(available), max(7, min(14, math.ceil(len(dates) * 0.7))))
    chosen_indexes = set()
    for row in available[:refine_count]:
        idx = index_by_date.get(row["departure_date"])
        if idx is None:
            continue
        for neighbor in (idx - 1, idx, idx + 1):
            if 0 <= neighbor < len(dates):
                chosen_indexes.add(neighbor)
    if len(chosen_indexes) < min(len(dates), 5):
        spread = {0, len(dates) - 1, len(dates) // 2}
        chosen_indexes.update(idx for idx in spread if 0 <= idx < len(dates))
    return [dates[idx] for idx in sorted(chosen_indexes)]


def main():
    parser = argparse.ArgumentParser(description="Search Korean domestic flights across date ranges")
    parser.add_argument("--origin", required=True, help="예: GMP 또는 김포")
    parser.add_argument("--destination", required=True, help="예: CJU 또는 제주")
    parser.add_argument("--start-date", help="예: 2026-03-25, 내일")
    parser.add_argument("--end-date", help="예: 2026-03-30")
    parser.add_argument("--date-range", help="예: 내일부터 3일, 이번주말, 2026-03-25~2026-03-30")
    parser.add_argument("--return-offset", type=int, default=0)
    parser.add_argument("--adults", type=int, default=1)
    parser.add_argument("--cabin", default="ECONOMY", choices=["ECONOMY", "BUSINESS", "FIRST"])
    parser.add_argument("--time-pref")
    parser.add_argument("--depart-after")
    parser.add_argument("--return-after")
    parser.add_argument("--exclude-early-before")
    parser.add_argument("--prefer", choices=["late", "morning", "afternoon", "evening"])
    parser.add_argument("--human", action="store_true")
    args = parser.parse_args()

    try:
        origin = normalize_airport(args.origin)
        destination = normalize_airport(args.destination)
        if args.date_range:
            start_dt, end_dt = parse_date_range_text(args.date_range)
        elif args.start_date and args.end_date:
            start_dt = parse_flexible_date(args.start_date)
            end_dt = parse_flexible_date(args.end_date)
        else:
            raise ValueError("start/end-date 또는 --date-range 중 하나를 제공해야 합니다.")
    except ValueError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2))
        sys.exit(1)

    if end_dt < start_dt:
        print(json.dumps({"status": "error", "message": "end-date must be after or equal to start-date"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    dates = build_dates(start_dt, end_dt)
    if len(dates) > 30:
        print(json.dumps({"status": "error", "message": "date range must be 30 days or less"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    workspace = Path(__file__).resolve().parents[3]
    repo_path = workspace / "tmp" / "Scraping-flight-information"
    if not repo_path.exists():
        print(json.dumps({"status": "error", "message": "Source repository clone not found.", "expected": str(repo_path)}, ensure_ascii=False, indent=2))
        sys.exit(1)

    sys.path.insert(0, str(repo_path))

    time_pref = parse_time_preference_args(args)

    logs = []
    normalized = []
    search_metadata = {
        "strategy": "parallel",
        "time_preference_active": time_pref.active(),
        "broad_scan_dates": len(dates),
        "refined_dates": 0,
        "refined_candidates": [],
        "broad_scan_available": 0,
    }

    if time_pref.active():
        try:
            from scraping.parallel import ParallelSearcher
            from scraping.searcher import FlightSearcher
        except Exception as exc:
            print(json.dumps({"status": "error", "message": "Failed to import hybrid search components.", "details": str(exc)}, ensure_ascii=False, indent=2))
            sys.exit(1)

        search_metadata["strategy"] = "hybrid_parallel_then_detailed"
        parallel_searcher = ParallelSearcher()
        logs.append("hybrid mode: broad parallel scan started")
        broad_raw = parallel_searcher.search_date_range(
            origin=origin,
            destination=destination,
            dates=[d.strftime("%Y%m%d") for d in dates],
            return_offset=args.return_offset,
            adults=args.adults,
            cabin_class=args.cabin,
            progress_callback=lambda msg: logs.append(f"[broad] {msg}"),
        )
        broad_rows = []
        for d in dates:
            dep = pretty_date(d)
            ret = pretty_date(d + timedelta(days=args.return_offset)) if args.return_offset > 0 else None
            price, airline = broad_raw.get(d.strftime("%Y%m%d"), (0, "N/A"))
            broad_rows.append(_empty_row(dep, ret, price=price, airline=airline))
        refine_dates = _choose_refine_dates(dates, broad_rows)
        search_metadata["broad_scan_available"] = len([row for row in broad_rows if row["price"] and row["price"] > 0])
        search_metadata["refined_dates"] = len(refine_dates)
        search_metadata["refined_candidates"] = [pretty_date(d) for d in refine_dates]
        logs.append(
            f"hybrid mode: broad scan complete, available={search_metadata['broad_scan_available']}, refining={search_metadata['refined_dates']}"
        )

        detailed_by_date = {}
        searcher = FlightSearcher()
        try:
            for d in refine_dates:
                dep = pretty_date(d)
                ret = pretty_date(d + timedelta(days=args.return_offset)) if args.return_offset > 0 else None
                results = searcher.search(
                    origin=origin,
                    destination=destination,
                    departure_date=dep,
                    return_date=ret,
                    adults=args.adults,
                    cabin_class=args.cabin,
                    max_results=20,
                    progress_callback=lambda msg, dep=dep: logs.append(f"[refine {dep}] {msg}"),
                    background_mode=False,
                )
                raw_results = [_normalize(item) for item in results]
                filtered, preferred_ranked = filter_and_rank_by_time_preference(raw_results, time_pref)
                cheapest = filtered[0] if filtered else None
                preferred = preferred_ranked[0] if preferred_ranked else None
                detailed_by_date[dep] = {
                    "departure_date": dep,
                    "return_date": ret,
                    "price": cheapest.get("price", 0) if cheapest else 0,
                    "airline": cheapest.get("airline", "") if cheapest else "",
                    "departure_time": cheapest.get("departure_time", "") if cheapest else "",
                    "return_departure_time": cheapest.get("return_departure_time", "") if cheapest else "",
                    "preferred_option": preferred,
                    "time_recommendation": time_preference_recommendation(preferred, cheapest, time_pref),
                }
        finally:
            try:
                searcher.close()
            except Exception:
                pass

        for broad in broad_rows:
            normalized.append(detailed_by_date.get(broad["departure_date"], broad))
    else:
        try:
            from scraping.parallel import ParallelSearcher
        except Exception as exc:
            print(json.dumps({"status": "error", "message": "Failed to import parallel searcher.", "details": str(exc)}, ensure_ascii=False, indent=2))
            sys.exit(1)
        searcher = ParallelSearcher()
        raw = searcher.search_date_range(
            origin=origin,
            destination=destination,
            dates=[d.strftime("%Y%m%d") for d in dates],
            return_offset=args.return_offset,
            adults=args.adults,
            cabin_class=args.cabin,
            progress_callback=lambda msg: logs.append(str(msg)),
        )
        for d in dates:
            key = d.strftime("%Y%m%d")
            price, airline = raw.get(key, (0, "N/A"))
            normalized.append({
                "departure_date": pretty_date(d),
                "return_date": pretty_date(d + timedelta(days=args.return_offset)) if args.return_offset > 0 else None,
                "price": price,
                "airline": airline,
                "departure_time": "",
                "return_departure_time": "",
                "preferred_option": None,
                "time_recommendation": None,
            })
        search_metadata["broad_scan_available"] = len([item for item in normalized if item["price"] and item["price"] > 0])

    available = [item for item in normalized if item["price"] and item["price"] > 0]
    available.sort(key=lambda x: x["price"])
    cheapest = available[0] if available else None
    second_price = available[1]["price"] if len(available) > 1 else None

    price_calendar = build_price_calendar(normalized, date_key="departure_date", price_key="price")
    balanced_option = choose_balanced_round_trip_option(available, time_pref) if args.return_offset > 0 else None

    summary = {
        "headline": (
            f"{airport_label(origin)} → {airport_label(destination)} 날짜범위 최저가 {format_price(cheapest['price'])}"
            if cheapest else
            f"{airport_label(origin)} → {airport_label(destination)} 날짜범위 검색 결과가 없습니다."
        ),
        "range": f"{pretty_date(start_dt)} ~ {pretty_date(end_dt)}",
        "trip_type": "왕복 범위검색" if args.return_offset > 0 else "편도 범위검색",
        "search_strategy": search_metadata["strategy"],
        "search_metadata": search_metadata,
        "best_date": cheapest,
        "top_dates": available[:5],
        "price_calendar": price_calendar,
        "balanced_round_trip": balanced_option,
        "recommendation": recommendation_line(
            f"{cheapest['departure_date']}{f'~{cheapest['return_date']}' if cheapest and cheapest['return_date'] else ''}",
            cheapest["price"],
            second_price,
        ) if cheapest else None,
        "recommendation_explained": explain_recommendation(
            f"{cheapest['departure_date']}{f'~{cheapest['return_date']}' if cheapest and cheapest['return_date'] else ''}",
            int(cheapest["price"] or 0),
            second_price,
            build_best_option_reasons(cheapest, second_price, time_pref),
        ) if cheapest else None,
        "time_recommendation": next((item.get("time_recommendation") for item in available if item.get("time_recommendation")), None),
        "balanced_recommendation": round_trip_balance_recommendation(balanced_option, cheapest, time_pref) if balanced_option else None,
        "balanced_recommendation_explained": explain_recommendation(
            f"{balanced_option['departure_date']}~{balanced_option['return_date']}",
            int(balanced_option["price"] or 0),
            int(cheapest["price"] or 0) if cheapest else None,
            build_balanced_option_reasons(balanced_option, cheapest, time_pref),
        ) if balanced_option else None,
    }

    if args.human:
        lines = [summary["headline"]]
        lines.append(f"범위: {summary['range']}")
        lines.append(f"조건: 성인 {args.adults}명 · {cabin_label(args.cabin)}")
        if args.return_offset > 0:
            lines.append(f"왕복 기준: 출발일 + {args.return_offset}일 귀국")
        if time_pref.describe():
            lines.append(f"시간 조건: {time_pref.describe()}")
        if search_metadata["strategy"].startswith("hybrid"):
            lines.append(
                f"검색 방식: 하이브리드(빠른 전체 스캔 {search_metadata['broad_scan_dates']}일 → 상세 재검증 {search_metadata['refined_dates']}일)"
            )
        if cheapest:
            if cheapest["return_date"]:
                time_text = f" · 가는편 {cheapest['departure_time']}" if cheapest.get("departure_time") else ""
                ret_time_text = f" · 오는편 {cheapest['return_departure_time']}" if cheapest.get("return_departure_time") else ""
                lines.append(f"최저가 날짜: {cheapest['departure_date']} ~ {cheapest['return_date']} · {format_price(cheapest['price'])} · {cheapest['airline']}{time_text}{ret_time_text}")
            else:
                time_text = f" · {cheapest['departure_time']}" if cheapest.get("departure_time") else ""
                lines.append(f"최저가 날짜: {cheapest['departure_date']} · {format_price(cheapest['price'])} · {cheapest['airline']}{time_text}")
        if summary.get("recommendation"):
            lines.append(summary["recommendation"])
        if summary.get("recommendation_explained"):
            lines.append(summary["recommendation_explained"])
        if summary.get("time_recommendation"):
            lines.append(summary["time_recommendation"])
        if summary.get("balanced_recommendation"):
            lines.append(summary["balanced_recommendation"])
        if summary.get("balanced_recommendation_explained"):
            lines.append(summary["balanced_recommendation_explained"])
        if summary["top_dates"]:
            lines.append("상위 날짜:")
            for idx, item in enumerate(summary["top_dates"], start=1):
                if item["return_date"]:
                    time_text = f" · 가는편 {item['departure_time']}" if item.get("departure_time") else ""
                    ret_time_text = f" · 오는편 {item['return_departure_time']}" if item.get("return_departure_time") else ""
                    lines.append(f"{idx}. {item['departure_date']} ~ {item['return_date']} · {format_price(item['price'])} · {item['airline']}{time_text}{ret_time_text}")
                else:
                    time_text = f" · {item['departure_time']}" if item.get("departure_time") else ""
                    lines.append(f"{idx}. {item['departure_date']} · {format_price(item['price'])} · {item['airline']}{time_text}")
        if summary["price_calendar"]:
            lines.append("가격 캘린더:")
            calendar_rows = summary["price_calendar"]
            preview = calendar_rows[:10]
            lines.extend(item["label"] for item in preview)
            if len(calendar_rows) > len(preview):
                lines.append(f"… 외 {len(calendar_rows) - len(preview)}일")
        print("\n".join(lines))
        return

    print(json.dumps({
        "status": "success",
        "query": {
            "origin": origin,
            "destination": destination,
            "start_date": pretty_date(start_dt),
            "end_date": pretty_date(end_dt),
            "return_offset": args.return_offset,
            "adults": args.adults,
            "cabin": args.cabin,
            "time_preference": time_pref.describe(),
        },
        "summary": summary,
        "results": normalized,
        "logs": logs,
        "search_metadata": search_metadata,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
