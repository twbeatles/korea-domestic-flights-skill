#!/usr/bin/env python3
import argparse
import json
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
    unique_codes,
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


def _broad_row(destination, dep, ret, price=0, airline=""):
    return {
        "destination": destination,
        "destination_label": airport_label(destination),
        "departure_date": dep,
        "return_date": ret,
        "price": price,
        "airline": airline,
        "departure_time": "",
        "return_departure_time": "",
        "preferred_option": None,
    }


def _choose_refine_combos(destinations, broad_rows):
    available = [row for row in broad_rows if row.get("price", 0) and row.get("price", 0) > 0]
    if not available:
        return []

    chosen = []
    seen = set()
    rows_by_destination = {destination: [row for row in available if row["destination"] == destination] for destination in destinations}

    for destination in destinations:
        rows = sorted(rows_by_destination[destination], key=lambda x: x["price"])[:3]
        ordered_dates = [row["departure_date"] for row in sorted(rows_by_destination[destination], key=lambda x: x["departure_date"])]
        for row in rows:
            key = (row["destination"], row["departure_date"])
            if key not in seen:
                chosen.append(row)
                seen.add(key)
            if row["departure_date"] in ordered_dates:
                idx = ordered_dates.index(row["departure_date"])
                for neighbor in (idx - 1, idx + 1):
                    if 0 <= neighbor < len(ordered_dates):
                        neighbor_key = (destination, ordered_dates[neighbor])
                        if neighbor_key not in seen:
                            neighbor_row = next((item for item in rows_by_destination[destination] if item["departure_date"] == ordered_dates[neighbor]), None)
                            if neighbor_row:
                                chosen.append(neighbor_row)
                                seen.add(neighbor_key)

    for row in sorted(available, key=lambda x: x["price"])[:15]:
        key = (row["destination"], row["departure_date"])
        if key not in seen:
            chosen.append(row)
            seen.add(key)

    return chosen


def main():
    parser = argparse.ArgumentParser(description="Search combined destination/date ranges for Korean domestic flights")
    parser.add_argument("--origin", required=True)
    parser.add_argument("--destinations", required=True, help="쉼표 구분 목적지 목록")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--date-range", help="예: 내일부터 5일, 2026-03-25~2026-03-30")
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
        destinations = unique_codes([normalize_airport(x.strip()) for x in args.destinations.split(",") if x.strip()])
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
    if len(dates) * len(destinations) > 90:
        print(json.dumps({"status": "error", "message": "검색 조합 수는 90개 이하로 제한됩니다."}, ensure_ascii=False, indent=2))
        sys.exit(1)

    workspace = Path(__file__).resolve().parents[3]
    repo_path = workspace / "tmp" / "Scraping-flight-information"
    if not repo_path.exists():
        print(json.dumps({"status": "error", "message": "Source repository clone not found.", "expected": str(repo_path)}, ensure_ascii=False, indent=2))
        sys.exit(1)

    sys.path.insert(0, str(repo_path))

    time_pref = parse_time_preference_args(args)

    logs = []
    destination_rows = []
    combos = []
    search_metadata = {
        "strategy": "parallel",
        "time_preference_active": time_pref.active(),
        "broad_scan_destinations": len(destinations),
        "broad_scan_dates": len(dates),
        "broad_scan_combos": len(destinations) * len(dates),
        "broad_scan_available": 0,
        "refined_combos": 0,
        "refined_candidates": [],
    }

    if time_pref.active():
        try:
            from scraping.parallel import ParallelSearcher
            from scraping.searcher import FlightSearcher
        except Exception as exc:
            print(json.dumps({"status": "error", "message": "Failed to import hybrid search components.", "details": str(exc)}, ensure_ascii=False, indent=2))
            sys.exit(1)

        search_metadata["strategy"] = "hybrid_parallel_then_detailed"
        broad_rows = []
        parallel_searcher = ParallelSearcher()
        for destination in destinations:
            logs.append(f"[broad] matrix search start: {destination}")
            raw = parallel_searcher.search_date_range(
                origin=origin,
                destination=destination,
                dates=[d.strftime("%Y%m%d") for d in dates],
                return_offset=args.return_offset,
                adults=args.adults,
                cabin_class=args.cabin,
                progress_callback=lambda msg, dest=destination: logs.append(f"[broad {dest}] {msg}"),
            )
            for d in dates:
                key = d.strftime("%Y%m%d")
                price, airline = raw.get(key, (0, "N/A"))
                broad_rows.append(_broad_row(
                    destination=destination,
                    dep=pretty_date(d),
                    ret=pretty_date(d + timedelta(days=args.return_offset)) if args.return_offset > 0 else None,
                    price=price,
                    airline=airline,
                ))

        search_metadata["broad_scan_available"] = len([row for row in broad_rows if row["price"] and row["price"] > 0])
        refine_rows = _choose_refine_combos(destinations, broad_rows)
        search_metadata["refined_combos"] = len(refine_rows)
        search_metadata["refined_candidates"] = [
            {
                "destination": row["destination"],
                "departure_date": row["departure_date"],
                "price": row["price"],
            }
            for row in refine_rows
        ]
        logs.append(
            f"hybrid mode: broad scan complete, available={search_metadata['broad_scan_available']}, refining={search_metadata['refined_combos']}"
        )

        detailed_map = {}
        searcher = FlightSearcher()
        try:
            for row in refine_rows:
                destination = row["destination"]
                dep = row["departure_date"]
                ret = row["return_date"]
                results = searcher.search(
                    origin=origin,
                    destination=destination,
                    departure_date=dep,
                    return_date=ret,
                    adults=args.adults,
                    cabin_class=args.cabin,
                    max_results=20,
                    progress_callback=lambda msg, dest=destination, dep=dep: logs.append(f"[refine {dest} {dep}] {msg}"),
                    background_mode=False,
                )
                raw_results = [_normalize(item) for item in results]
                filtered, preferred_ranked = filter_and_rank_by_time_preference(raw_results, time_pref)
                cheapest = filtered[0] if filtered else None
                detailed_map[(destination, dep)] = {
                    "destination": destination,
                    "destination_label": airport_label(destination),
                    "departure_date": dep,
                    "return_date": ret,
                    "price": cheapest.get("price", 0) if cheapest else 0,
                    "airline": cheapest.get("airline", "") if cheapest else "",
                    "departure_time": cheapest.get("departure_time", "") if cheapest else "",
                    "return_departure_time": cheapest.get("return_departure_time", "") if cheapest else "",
                    "preferred_option": preferred_ranked[0] if preferred_ranked else None,
                }
        finally:
            try:
                searcher.close()
            except Exception:
                pass

        all_rows = []
        for row in broad_rows:
            key = (row["destination"], row["departure_date"])
            all_rows.append(detailed_map.get(key, row))

        for destination in destinations:
            rows = [row for row in all_rows if row["destination"] == destination]
            combos.extend(rows)
            available_rows = [row for row in rows if row["price"] and row["price"] > 0]
            available_rows.sort(key=lambda x: x["price"])
            destination_rows.append({
                "destination": destination,
                "destination_label": airport_label(destination),
                "search_strategy": search_metadata["strategy"],
                "best_option": available_rows[0] if available_rows else None,
                "top_dates": available_rows[:3],
                "price_calendar": build_price_calendar(rows, date_key="departure_date", price_key="price"),
            })
    else:
        try:
            from scraping.parallel import ParallelSearcher
        except Exception as exc:
            print(json.dumps({"status": "error", "message": "Failed to import parallel searcher.", "details": str(exc)}, ensure_ascii=False, indent=2))
            sys.exit(1)
        searcher = ParallelSearcher()
        for destination in destinations:
            logs.append(f"matrix search start: {destination}")
            raw = searcher.search_date_range(
                origin=origin,
                destination=destination,
                dates=[d.strftime("%Y%m%d") for d in dates],
                return_offset=args.return_offset,
                adults=args.adults,
                cabin_class=args.cabin,
                progress_callback=lambda msg, dest=destination: logs.append(f"[{dest}] {msg}"),
            )
            rows = []
            for d in dates:
                key = d.strftime("%Y%m%d")
                price, airline = raw.get(key, (0, "N/A"))
                row = {
                    "destination": destination,
                    "destination_label": airport_label(destination),
                    "departure_date": pretty_date(d),
                    "return_date": pretty_date(d + timedelta(days=args.return_offset)) if args.return_offset > 0 else None,
                    "price": price,
                    "airline": airline,
                    "departure_time": "",
                    "return_departure_time": "",
                    "preferred_option": None,
                }
                rows.append(row)
                combos.append(row)
            available_rows = [row for row in rows if row["price"] and row["price"] > 0]
            available_rows.sort(key=lambda x: x["price"])
            destination_rows.append({
                "destination": destination,
                "destination_label": airport_label(destination),
                "search_strategy": search_metadata["strategy"],
                "best_option": available_rows[0] if available_rows else None,
                "top_dates": available_rows[:3],
                "price_calendar": build_price_calendar(rows, date_key="departure_date", price_key="price"),
            })
        search_metadata["broad_scan_available"] = len([row for row in combos if row["price"] and row["price"] > 0])

    ranked_combos = sorted([row for row in combos if row["price"] and row["price"] > 0], key=lambda x: x["price"])
    best = ranked_combos[0] if ranked_combos else None
    balanced_combo = choose_balanced_round_trip_option(ranked_combos, time_pref) if args.return_offset > 0 else None
    second_price = ranked_combos[1]["price"] if len(ranked_combos) > 1 else None

    destination_rows.sort(key=lambda x: x["best_option"]["price"] if x["best_option"] else 10**12)
    summary = {
        "headline": (
            f"{airport_label(origin)} 출발 최적 조합은 {best['destination_label']} {best['departure_date']} {format_price(best['price'])}"
            if best else
            f"{airport_label(origin)} 출발 목적지+날짜 범위 검색 결과가 없습니다."
        ),
        "range": f"{pretty_date(start_dt)} ~ {pretty_date(end_dt)}",
        "search_strategy": search_metadata["strategy"],
        "search_metadata": search_metadata,
        "best_combo": best,
        "balanced_round_trip": balanced_combo,
        "top_combos": ranked_combos[:7],
        "by_destination": destination_rows,
        "recommendation": recommendation_line(
            f"{best['destination_label']} / {best['departure_date']}{f'~{best['return_date']}' if best and best['return_date'] else ''}",
            best["price"],
            second_price,
        ) if best else None,
        "recommendation_explained": explain_recommendation(
            f"{best['destination_label']} / {best['departure_date']}{f'~{best['return_date']}' if best and best['return_date'] else ''}",
            int(best["price"] or 0),
            second_price,
            build_best_option_reasons(best, second_price, time_pref),
        ) if best else None,
        "balanced_recommendation": round_trip_balance_recommendation(balanced_combo, best, time_pref) if balanced_combo else None,
        "balanced_recommendation_explained": explain_recommendation(
            f"{balanced_combo['destination_label']} / {balanced_combo['departure_date']}{f'~{balanced_combo['return_date']}' if balanced_combo and balanced_combo['return_date'] else ''}",
            int(balanced_combo["price"] or 0),
            int(best["price"] or 0) if best else None,
            build_balanced_option_reasons(balanced_combo, best, time_pref),
        ) if balanced_combo else None,
    }

    if args.human:
        lines = [summary["headline"]]
        lines.append(f"범위: {summary['range']}")
        lines.append(f"조건: 출발 {airport_label(origin)} · 목적지 {len(destinations)}곳 · 성인 {args.adults}명 · {cabin_label(args.cabin)}")
        if args.return_offset > 0:
            lines.append(f"왕복 기준: 출발일 + {args.return_offset}일 귀국")
        if time_pref.describe():
            lines.append(f"시간 조건: {time_pref.describe()}")
        if search_metadata["strategy"].startswith("hybrid"):
            lines.append(
                f"검색 방식: 하이브리드(빠른 전체 스캔 {search_metadata['broad_scan_combos']}조합 → 상세 재검증 {search_metadata['refined_combos']}조합)"
            )
        if best:
            date_text = f"{best['departure_date']} ~ {best['return_date']}" if best["return_date"] else best["departure_date"]
            time_text = f" · 가는편 {best['departure_time']}" if best.get("departure_time") else ""
            ret_time = f" · 오는편 {best['return_departure_time']}" if best.get("return_departure_time") else ""
            lines.append(f"최적 조합: {best['destination_label']} · {date_text} · {format_price(best['price'])} · {best['airline']}{time_text}{ret_time}")
        if summary.get("recommendation"):
            lines.append(summary["recommendation"])
        if summary.get("recommendation_explained"):
            lines.append(summary["recommendation_explained"])
        if summary.get("balanced_recommendation"):
            lines.append(summary["balanced_recommendation"])
        if summary.get("balanced_recommendation_explained"):
            lines.append(summary["balanced_recommendation_explained"])
        if destination_rows:
            lines.append("목적지별 베스트:")
            for idx, item in enumerate(destination_rows[:5], start=1):
                best_option = item["best_option"]
                if best_option:
                    date_text = f"{best_option['departure_date']} ~ {best_option['return_date']}" if best_option["return_date"] else best_option["departure_date"]
                    time_text = f" · 가는편 {best_option['departure_time']}" if best_option.get("departure_time") else ""
                    ret_time = f" · 오는편 {best_option['return_departure_time']}" if best_option.get("return_departure_time") else ""
                    lines.append(f"{idx}. {item['destination_label']} · {date_text} · {format_price(best_option['price'])} · {best_option['airline']}{time_text}{ret_time}")
                else:
                    lines.append(f"{idx}. {item['destination_label']} · 결과 없음")
            lines.append("목적지별 가격 캘린더:")
            for item in destination_rows[:5]:
                lines.append(f"- {item['destination_label']}")
                calendar_rows = item.get("price_calendar", [])
                preview = calendar_rows[:7]
                lines.extend(f"  {entry['label']}" for entry in preview)
                if len(calendar_rows) > len(preview):
                    lines.append(f"  … 외 {len(calendar_rows) - len(preview)}일")
        if ranked_combos:
            lines.append("전체 상위 조합:")
            for idx, item in enumerate(ranked_combos[:7], start=1):
                date_text = f"{item['departure_date']} ~ {item['return_date']}" if item["return_date"] else item["departure_date"]
                time_text = f" · 가는편 {item['departure_time']}" if item.get("departure_time") else ""
                ret_time = f" · 오는편 {item['return_departure_time']}" if item.get("return_departure_time") else ""
                lines.append(f"{idx}. {item['destination_label']} · {date_text} · {format_price(item['price'])} · {item['airline']}{time_text}{ret_time}")
        print("\n".join(lines))
        return

    print(json.dumps({
        "status": "success",
        "query": {
            "origin": origin,
            "destinations": destinations,
            "start_date": pretty_date(start_dt),
            "end_date": pretty_date(end_dt),
            "return_offset": args.return_offset,
            "adults": args.adults,
            "cabin": args.cabin,
            "time_preference": time_pref.describe(),
        },
        "summary": summary,
        "results": ranked_combos,
        "matrix": destination_rows,
        "logs": logs,
        "search_metadata": search_metadata,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
