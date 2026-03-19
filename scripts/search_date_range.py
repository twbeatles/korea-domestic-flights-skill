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
    cabin_label,
    filter_and_rank_by_time_preference,
    format_price,
    normalize_airport,
    parse_date_range_text,
    parse_flexible_date,
    parse_time_preference_text,
    pretty_date,
    recommendation_line,
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

    time_pref = parse_time_preference_text(args.time_pref)
    if args.depart_after:
        time_pref.depart_min = parse_time_preference_text(f"출발 {args.depart_after}시 이후").depart_min
    if args.return_after:
        time_pref.return_min = parse_time_preference_text(f"복귀 {args.return_after}시 이후").return_min
    if args.exclude_early_before:
        time_pref.exclude_before_depart = parse_time_preference_text(f"{args.exclude_early_before}시 이전 비행 제외").exclude_before_depart
    if args.prefer:
        time_pref.prefer = args.prefer

    logs = []
    normalized = []

    if time_pref.active():
        try:
            from scraping.searcher import FlightSearcher
        except Exception as exc:
            print(json.dumps({"status": "error", "message": "Failed to import flight searcher.", "details": str(exc)}, ensure_ascii=False, indent=2))
            sys.exit(1)
        searcher = FlightSearcher()
        try:
            for d in dates:
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
                    progress_callback=lambda msg, dep=dep: logs.append(f"[{dep}] {msg}"),
                    background_mode=False,
                )
                raw_results = [_normalize(item) for item in results]
                filtered, preferred_ranked = filter_and_rank_by_time_preference(raw_results, time_pref)
                cheapest = filtered[0] if filtered else None
                preferred = preferred_ranked[0] if preferred_ranked else None
                normalized.append({
                    "departure_date": dep,
                    "return_date": ret,
                    "price": cheapest.get("price", 0) if cheapest else 0,
                    "airline": cheapest.get("airline", "") if cheapest else "",
                    "departure_time": cheapest.get("departure_time", "") if cheapest else "",
                    "return_departure_time": cheapest.get("return_departure_time", "") if cheapest else "",
                    "preferred_option": preferred,
                    "time_recommendation": time_preference_recommendation(preferred, cheapest, time_pref),
                })
        finally:
            try:
                searcher.close()
            except Exception:
                pass
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

    available = [item for item in normalized if item["price"] and item["price"] > 0]
    available.sort(key=lambda x: x["price"])
    cheapest = available[0] if available else None
    second_price = available[1]["price"] if len(available) > 1 else None

    summary = {
        "headline": (
            f"{airport_label(origin)} → {airport_label(destination)} 날짜범위 최저가 {format_price(cheapest['price'])}"
            if cheapest else
            f"{airport_label(origin)} → {airport_label(destination)} 날짜범위 검색 결과가 없습니다."
        ),
        "range": f"{pretty_date(start_dt)} ~ {pretty_date(end_dt)}",
        "trip_type": "왕복 범위검색" if args.return_offset > 0 else "편도 범위검색",
        "best_date": cheapest,
        "top_dates": available[:5],
        "recommendation": recommendation_line(
            f"{cheapest['departure_date']}{f'~{cheapest['return_date']}' if cheapest and cheapest['return_date'] else ''}",
            cheapest["price"],
            second_price,
        ) if cheapest else None,
        "time_recommendation": next((item.get("time_recommendation") for item in available if item.get("time_recommendation")), None),
    }

    if args.human:
        lines = [summary["headline"]]
        lines.append(f"범위: {summary['range']}")
        lines.append(f"조건: 성인 {args.adults}명 · {cabin_label(args.cabin)}")
        if args.return_offset > 0:
            lines.append(f"왕복 기준: 출발일 + {args.return_offset}일 귀국")
        if time_pref.describe():
            lines.append(f"시간 조건: {time_pref.describe()}")
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
        if summary.get("time_recommendation"):
            lines.append(summary["time_recommendation"])
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
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
