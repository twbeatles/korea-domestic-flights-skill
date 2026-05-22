from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Sequence

RESULT_FIELD_DEFAULTS = {
    "airline": "",
    "price": 0,
    "currency": "KRW",
    "departure_time": "",
    "arrival_time": "",
    "duration": "",
    "stops": 0,
    "flight_number": "",
    "source": "",
    "return_departure_time": "",
    "return_arrival_time": "",
    "return_duration": "",
    "return_stops": 0,
    "is_round_trip": False,
    "outbound_price": 0,
    "return_price": 0,
    "return_airline": "",
    "benefit_price": 0,
    "benefit_label": "",
    "confidence": 0,
    "extraction_source": "",
}


def normalize_result_payload(item) -> dict:
    if item is None:
        data = {}
    elif is_dataclass(item):
        data = asdict(item)
    elif hasattr(item, "__dict__"):
        data = dict(item.__dict__)
    elif isinstance(item, dict):
        data = dict(item)
    else:
        data = {"value": str(item)}
    normalized = {key: (data.get(key, default) if data.get(key, default) is not None else default) for key, default in RESULT_FIELD_DEFAULTS.items()}
    normalized.update({key: value for key, value in data.items() if key not in normalized})
    return normalized


def make_broad_row(
    *,
    departure_date: str,
    return_date: str | None,
    price: int = 0,
    airline: str = "",
    destination: str | None = None,
    destination_label: str | None = None,
) -> dict:
    row = normalize_result_payload({"price": price, "airline": airline})
    row.update(
        {
            "departure_date": departure_date,
            "return_date": return_date,
            "destination": destination,
            "destination_label": destination_label,
            "preferred_option": None,
            "search_stage": "broad_only",
            "time_pref_match": None,
            "raw_option_count": 0,
            "priced_option_count": 0,
            "departure_time_count": 0,
            "return_time_count": 0,
            "time_pref_valid_count": 0,
            "broad_price": price,
            "diagnostic_reason": "broad_only",
            "diagnostic_detail": {},
            "candidate_reason": "broad_rank",
            "strategy_score": 0.0,
            "strategy_reasons": [],
        }
    )
    return row


def priced_rows(items: Sequence[dict]) -> list[dict]:
    rows = [item for item in items if int(item.get("price", 0) or 0) > 0]
    rows.sort(key=lambda item: int(item.get("price", 0) or 0))
    return rows


def verified_priced_rows(items: Sequence[dict], *, time_pref_active: bool) -> list[dict]:
    if not time_pref_active:
        return priced_rows(items)
    rows = [item for item in items if int(item.get("price", 0) or 0) > 0 and item.get("time_pref_match") is True]
    rows.sort(key=lambda item: int(item.get("price", 0) or 0))
    return rows


def unverified_broad_rows(items: Sequence[dict]) -> list[dict]:
    rows = [
        item
        for item in items
        if int(item.get("price", 0) or 0) > 0 and str(item.get("search_stage") or "") == "broad_only"
    ]
    rows.sort(key=lambda item: int(item.get("price", 0) or 0))
    return rows


def benefit_text(item: dict | None) -> str | None:
    if not item:
        return None
    benefit_price = int(item.get("benefit_price", 0) or 0)
    price = int(item.get("price", 0) or 0)
    if benefit_price <= 0 or benefit_price == price:
        return None
    label = str(item.get("benefit_label") or "").strip()
    return " · ".join(part for part in [f"혜택가 {format_price(benefit_price)}", label] if part)


def format_price(value: int | float | None) -> str:
    return f"{int(value or 0):,}원"


def build_price_calendar(rows: Sequence[dict], date_key: str = "departure_date", price_key: str = "price") -> list[dict]:
    prices = [int(item.get(price_key, 0) or 0) for item in rows if int(item.get(price_key, 0) or 0) > 0]
    cheapest = min(prices) if prices else 0
    median = sorted(prices)[len(prices) // 2] if prices else 0
    calendar = []
    for item in rows:
        price = int(item.get(price_key, 0) or 0)
        if price <= 0:
            band, note = "unavailable", "결과 없음"
        elif cheapest and price == cheapest:
            band, note = "best", "최저가"
        elif median and price <= median:
            band, note = "good", "양호"
        else:
            band, note = "high", "상대적으로 높음"
        verified = item.get("time_pref_match") is True or str(item.get("search_stage") or "") != "broad_only"
        calendar.append(
            {
                "date": item.get(date_key),
                "price": price,
                "band": band,
                "verified": verified,
                "label": f"{item.get(date_key)} · {format_price(price) if price else '결과 없음'} · {note}{'' if verified else ' · 빠른 스캔(미검증)'}",
            }
        )
    return calendar
