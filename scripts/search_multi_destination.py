#!/usr/bin/env python3
import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common_cli import (
    add_section,
    airport_label,
    build_best_option_reasons,
    cabin_label,
    bullet_rank_lines,
    close_safely,
    emit_json,
    explain_recommendation,
    filter_and_rank_by_time_preference,
    format_price,
    format_time_or_fallback,
    join_nonempty,
    normalize_airport,
    parse_flexible_date,
    parse_time_preference_args,
    pretty_date,
    recommendation_line,
    resolve_source_repo,
    time_preference_recommendation,
    unique_codes,
    verify_date_order,
)


def normalize_result(item):
    if is_dataclass(item):
        return asdict(item)
    if hasattr(item, "__dict__"):
        return dict(item.__dict__)
    return {"value": str(item)}


def main():
    parser = argparse.ArgumentParser(description="Compare Korean domestic flight fares across multiple destinations")
    parser.add_argument("--origin", required=True)
    parser.add_argument("--destinations", required=True, help="Comma-separated destinations, e.g. CJU,PUS,RSU or 제주,부산,여수")
    parser.add_argument("--departure", required=True)
    parser.add_argument("--return-date")
    parser.add_argument("--adults", type=int, default=1)
    parser.add_argument("--cabin", default="ECONOMY", choices=["ECONOMY", "BUSINESS", "FIRST"])
    parser.add_argument("--time-pref")
    parser.add_argument("--depart-after")
    parser.add_argument("--return-after")
    parser.add_argument("--exclude-early-before")
    parser.add_argument("--prefer", choices=["late", "morning", "afternoon", "evening"])
    parser.add_argument("--human", action="store_true")
    parser.add_argument("--repo-path", help="upstream Scraping-flight-information 저장소 경로")
    args = parser.parse_args()

    try:
        repo_path = resolve_source_repo(script_path=__file__, repo_path=args.repo_path)
    except FileNotFoundError as exc:
        emit_json({"status": "error", "message": "Source repository clone not found.", "details": str(exc)})
        sys.exit(1)

    sys.path.insert(0, str(repo_path))

    try:
        from scraping.parallel import ParallelSearcher
    except Exception as exc:
        emit_json({"status": "error", "message": "Failed to import parallel searcher.", "details": str(exc)})
        sys.exit(1)

    try:
        origin = normalize_airport(args.origin)
        destinations = unique_codes([normalize_airport(x.strip()) for x in args.destinations.split(",") if x.strip()])
        departure = pretty_date(parse_flexible_date(args.departure))
        return_date = pretty_date(parse_flexible_date(args.return_date)) if args.return_date else None
        verify_date_order(departure, return_date)
    except ValueError as exc:
        emit_json({"status": "error", "message": str(exc)})
        sys.exit(1)

    time_pref = parse_time_preference_args(args)

    logs = []

    def progress(msg):
        logs.append(str(msg))

    searcher = ParallelSearcher()
    try:
        raw = searcher.search_multiple_destinations(
            origin=origin,
            destinations=destinations,
            departure_date=departure.replace("-", ""),
            return_date=return_date.replace("-", "") if return_date else None,
            adults=args.adults,
            cabin_class=args.cabin,
            progress_callback=progress,
        )
    finally:
        close_safely(searcher)

    normalized = []
    for dest in destinations:
        raw_results = [normalize_result(item) for item in (raw.get(dest, []) or [])]
        filtered, preferred_ranked = filter_and_rank_by_time_preference(raw_results, time_pref)
        cheapest = filtered[0] if filtered else None
        preferred = preferred_ranked[0] if preferred_ranked else None
        normalized.append({
            "destination": dest,
            "destination_label": airport_label(dest),
            "departure_date": departure,
            "return_date": return_date,
            "count": len(filtered),
            "raw_count": len(raw_results),
            "cheapest_price": cheapest.get("price", 0) if cheapest else 0,
            "price": cheapest.get("price", 0) if cheapest else 0,
            "airline": cheapest.get("airline", "") if cheapest else "",
            "departure_time": cheapest.get("departure_time", "") if cheapest else "",
            "arrival_time": cheapest.get("arrival_time", "") if cheapest else "",
            "return_airline": cheapest.get("return_airline", "") if cheapest else "",
            "return_departure_time": cheapest.get("return_departure_time", "") if cheapest else "",
            "return_arrival_time": cheapest.get("return_arrival_time", "") if cheapest else "",
            "preferred_price": preferred.get("price", 0) if preferred else 0,
            "preferred_airline": preferred.get("airline", "") if preferred else "",
            "preferred_departure_time": preferred.get("departure_time", "") if preferred else "",
            "preferred_return_departure_time": preferred.get("return_departure_time", "") if preferred else "",
            "preferred_option": preferred,
            "time_recommendation": time_preference_recommendation(preferred, cheapest, time_pref),
        })

    ranked = sorted(normalized, key=lambda x: x["cheapest_price"] if x["cheapest_price"] > 0 else 10**12)
    best = ranked[0] if ranked and ranked[0]["cheapest_price"] > 0 else None
    second_price = ranked[1]["cheapest_price"] if len(ranked) > 1 and ranked[1]["cheapest_price"] > 0 else None

    summary = {
        "headline": (
            f"{airport_label(origin)} 출발 다중 목적지 최저가 {format_price(best['cheapest_price'])}"
            if best else
            f"{airport_label(origin)} 출발 다중 목적지 검색 결과가 없습니다."
        ),
        "best_option": best,
        "ranked_destinations": ranked,
        "recommendation": recommendation_line(best["destination_label"], best["cheapest_price"], second_price) if best else None,
        "recommendation_explained": explain_recommendation(
            best["destination_label"],
            int(best["cheapest_price"] or 0),
            second_price,
            build_best_option_reasons(best, second_price, time_pref),
        ) if best else None,
    }

    if args.human:
        def destination_detail(item):
            time_bits = [
                join_nonempty([
                    format_time_or_fallback(item.get('departure_time')) if item.get('departure_time') else None,
                    item.get('arrival_time') or None,
                ], '→'),
            ]
            if item.get("return_date"):
                time_bits.append(join_nonempty([
                    format_time_or_fallback(item.get('return_departure_time')) if item.get('return_departure_time') else None,
                    item.get('return_arrival_time') or None,
                ], '→'))
            return join_nonempty([
                item.get('airline') or None,
                join_nonempty([bit for bit in time_bits if bit], " / "),
            ])

        lines = [summary["headline"]]
        lines.append(f"조건: 출발 {airport_label(origin)} · 출발일 {departure} · 성인 {args.adults}명 · {cabin_label(args.cabin)}")
        if return_date:
            lines.append(f"왕복 일정: {departure} ~ {return_date}")
        if time_pref.describe():
            lines.append(f"시간 조건: {time_pref.describe()}")

        add_section(lines, "최저가", [
            join_nonempty([
                f"최적 목적지: {best['destination_label']}" if best else None,
                format_price(best['cheapest_price']) if best else None,
                destination_detail(best) if best else None,
            ]),
            summary.get("recommendation"),
            summary.get("recommendation_explained"),
        ])
        late_pref = next((item["time_recommendation"] for item in ranked if item.get("time_recommendation")), None)
        add_section(lines, "시간대 추천", [late_pref])
        add_section(lines, "목적지 비교", bullet_rank_lines(ranked, "destination_label", "cheapest_price", destination_detail, limit=5))
        print("\n".join(lines))
        return

    emit_json({
        "status": "success",
        "query": {
            "origin": origin,
            "destinations": destinations,
            "departure": departure,
            "return_date": return_date,
            "adults": args.adults,
            "cabin": args.cabin,
            "time_preference": time_pref.describe(),
        },
        "summary": summary,
        "results": ranked,
        "logs": logs,
    })


if __name__ == "__main__":
    main()
