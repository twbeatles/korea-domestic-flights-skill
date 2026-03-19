#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

AIRPORT_NAMES = {
    "GMP": "김포",
    "CJU": "제주",
    "PUS": "부산",
    "TAE": "대구",
    "CJJ": "청주",
    "KWJ": "광주",
    "RSU": "여수",
    "USN": "울산",
    "HIN": "사천",
    "KPO": "포항경주",
    "YNY": "양양",
    "MWX": "무안",
    "SEL": "서울",
}


def airport_label(code):
    code = (code or "").upper()
    return f"{AIRPORT_NAMES.get(code, code)}({code})" if code else ""


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d")


def ymd(value):
    return value.strftime("%Y%m%d")


def pretty(value):
    return value.strftime("%Y-%m-%d")


def build_dates(start_date, end_date):
    days = []
    current = start_date
    while current <= end_date:
        days.append(current)
        current += timedelta(days=1)
    return days


def main():
    parser = argparse.ArgumentParser(description="Search Korean domestic flights across date ranges")
    parser.add_argument("--origin", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--return-offset", type=int, default=0)
    parser.add_argument("--adults", type=int, default=1)
    parser.add_argument("--cabin", default="ECONOMY", choices=["ECONOMY", "BUSINESS", "FIRST"])
    parser.add_argument("--human", action="store_true")
    args = parser.parse_args()

    start_dt = parse_date(args.start_date)
    end_dt = parse_date(args.end_date)
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

    try:
        from scraping.parallel import ParallelSearcher
    except Exception as exc:
        print(json.dumps({"status": "error", "message": "Failed to import parallel searcher.", "details": str(exc)}, ensure_ascii=False, indent=2))
        sys.exit(1)

    logs = []

    def progress(msg):
        logs.append(str(msg))

    searcher = ParallelSearcher()
    raw = searcher.search_date_range(
        origin=args.origin.upper(),
        destination=args.destination.upper(),
        dates=[ymd(d) for d in dates],
        return_offset=args.return_offset,
        adults=args.adults,
        cabin_class=args.cabin,
        progress_callback=progress,
    )

    normalized = []
    for d in dates:
        key = ymd(d)
        price, airline = raw.get(key, (0, "N/A"))
        normalized.append({
            "departure_date": pretty(d),
            "return_date": pretty(d + timedelta(days=args.return_offset)) if args.return_offset > 0 else None,
            "price": price,
            "airline": airline,
        })

    available = [item for item in normalized if item["price"] and item["price"] > 0]
    available.sort(key=lambda x: x["price"])
    cheapest = available[0] if available else None

    summary = {
        "headline": (
            f"{airport_label(args.origin)} → {airport_label(args.destination)} 날짜범위 최저가 {cheapest['price']:,}원"
            if cheapest else
            f"{airport_label(args.origin)} → {airport_label(args.destination)} 날짜범위 검색 결과가 없습니다."
        ),
        "range": f"{args.start_date} ~ {args.end_date}",
        "trip_type": "왕복 범위검색" if args.return_offset > 0 else "편도 범위검색",
        "best_date": cheapest,
        "top_dates": available[:5],
    }

    if args.human:
        lines = [summary["headline"]]
        lines.append(f"범위: {summary['range']}")
        lines.append(f"조건: 성인 {args.adults}명 · {args.cabin}")
        if args.return_offset > 0:
            lines.append(f"왕복 기준: 출발일 + {args.return_offset}일 귀국")
        if cheapest:
            if cheapest["return_date"]:
                lines.append(f"최저가 날짜: {cheapest['departure_date']} ~ {cheapest['return_date']} · {cheapest['price']:,}원 · {cheapest['airline']}")
            else:
                lines.append(f"최저가 날짜: {cheapest['departure_date']} · {cheapest['price']:,}원 · {cheapest['airline']}")
        if summary["top_dates"]:
            lines.append("상위 날짜:")
            for idx, item in enumerate(summary["top_dates"], start=1):
                if item["return_date"]:
                    lines.append(f"{idx}. {item['departure_date']} ~ {item['return_date']} · {item['price']:,}원 · {item['airline']}")
                else:
                    lines.append(f"{idx}. {item['departure_date']} · {item['price']:,}원 · {item['airline']}")
        print("\n".join(lines))
        return

    print(json.dumps({
        "status": "success",
        "query": {
            "origin": args.origin.upper(),
            "destination": args.destination.upper(),
            "start_date": args.start_date,
            "end_date": args.end_date,
            "return_offset": args.return_offset,
            "adults": args.adults,
            "cabin": args.cabin,
        },
        "summary": summary,
        "results": normalized,
        "logs": logs,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
