from __future__ import annotations

import re
from collections.abc import Sequence

AIRPORT_NAMES = {
    "ICN": "인천",
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
    "NRT": "도쿄 나리타",
    "HND": "도쿄 하네다",
    "TYO": "도쿄",
    "KIX": "오사카 간사이",
    "OSA": "오사카",
    "FUK": "후쿠오카",
    "BKK": "방콕",
    "SIN": "싱가포르",
    "HKG": "홍콩",
    "SGN": "호치민",
    "DAD": "다낭",
    "DPS": "발리",
}

AIRPORT_ALIASES = {
    "인천": "ICN",
    "김포": "GMP",
    "제주": "CJU",
    "제주도": "CJU",
    "부산": "PUS",
    "김해": "PUS",
    "대구": "TAE",
    "청주": "CJJ",
    "광주": "KWJ",
    "여수": "RSU",
    "울산": "USN",
    "사천": "HIN",
    "진주": "HIN",
    "포항": "KPO",
    "포항경주": "KPO",
    "양양": "YNY",
    "무안": "MWX",
    "서울": "SEL",
    "나리타": "NRT",
    "도쿄 나리타": "NRT",
    "하네다": "HND",
    "도쿄 하네다": "HND",
    "도쿄": "TYO",
    "간사이": "KIX",
    "오사카 간사이": "KIX",
    "오사카": "OSA",
    "후쿠오카": "FUK",
    "방콕": "BKK",
    "싱가포르": "SIN",
    "홍콩": "HKG",
    "호치민": "SGN",
    "다낭": "DAD",
    "발리": "DPS",
    "incheon": "ICN",
    "gimpo": "GMP",
    "jeju": "CJU",
    "busan": "PUS",
    "daegu": "TAE",
    "cheongju": "CJJ",
    "gwangju": "KWJ",
    "yeosu": "RSU",
    "ulsan": "USN",
    "sacheon": "HIN",
    "pohang": "KPO",
    "yangyang": "YNY",
    "muan": "MWX",
    "seoul": "SEL",
    "narita": "NRT",
    "haneda": "HND",
    "tokyo": "TYO",
    "kansai": "KIX",
    "osaka": "OSA",
    "fukuoka": "FUK",
    "bangkok": "BKK",
    "singapore": "SIN",
    "hong kong": "HKG",
    "hongkong": "HKG",
    "ho chi minh": "SGN",
    "hochiminh": "SGN",
    "da nang": "DAD",
    "danang": "DAD",
    "bali": "DPS",
}

DOMESTIC_AIRPORT_CODES = {
    "ICN",
    "GMP",
    "CJU",
    "PUS",
    "TAE",
    "CJJ",
    "KWJ",
    "RSU",
    "USN",
    "HIN",
    "KPO",
    "YNY",
    "MWX",
    "SEL",
}

CITY_CODES_MAP = {
    "ICN": "SEL",
    "GMP": "SEL",
    "SEL": "SEL",
    "NRT": "TYO",
    "HND": "TYO",
    "TYO": "TYO",
    "KIX": "OSA",
    "OSA": "OSA",
}


def normalize_airport(value: str) -> str:
    if not value:
        raise ValueError("공항 값이 비어 있습니다.")
    raw = value.strip()
    upper = raw.upper()
    if upper in AIRPORT_NAMES:
        return upper
    lowered = raw.lower()
    if lowered in AIRPORT_ALIASES:
        return AIRPORT_ALIASES[lowered]
    if raw in AIRPORT_ALIASES:
        return AIRPORT_ALIASES[raw]
    if re.fullmatch(r"[A-Za-z]{3}", raw):
        return upper
    raise ValueError(f"지원하지 않는 공항 입력입니다: {value}")


def airport_label(code: str) -> str:
    normalized = (code or "").upper()
    return f"{AIRPORT_NAMES.get(normalized, normalized)}({normalized})" if normalized else ""


def _route_scope_code(code: str) -> str:
    normalized = (code or "").upper()
    return CITY_CODES_MAP.get(normalized, normalized)


def infer_route_scope(origin: str, destination: str) -> str:
    origin_code = (origin or "").upper()
    destination_code = (destination or "").upper()
    origin_domestic = origin_code in DOMESTIC_AIRPORT_CODES or _route_scope_code(origin_code) in DOMESTIC_AIRPORT_CODES
    destination_domestic = destination_code in DOMESTIC_AIRPORT_CODES or _route_scope_code(destination_code) in DOMESTIC_AIRPORT_CODES
    return "domestic" if origin_domestic and destination_domestic else "international"


def infer_routes_scope(origin: str, destinations: Sequence[str]) -> str:
    scopes = {infer_route_scope(origin, destination) for destination in destinations if destination}
    if not scopes:
        return "international"
    return next(iter(scopes)) if len(scopes) == 1 else "mixed"


def resolve_route_scope(origin: str, destinations: Sequence[str], requested_scope: str = "auto") -> str:
    route_scope = infer_routes_scope(origin, destinations)
    requested = (requested_scope or "auto").lower()
    if requested not in {"auto", "domestic", "international"}:
        raise ValueError(f"지원하지 않는 scope 입니다: {requested_scope}")
    if requested != "auto" and route_scope != requested:
        if requested == "domestic":
            raise ValueError("국내선 scope 로 강제했지만 국제선 노선이 포함되어 있습니다.")
        raise ValueError("국제선 scope 로 강제했지만 국내선 노선이 포함되어 있습니다.")
    return route_scope


def route_scope_label(scope: str) -> str:
    return {
        "auto": "자동",
        "domestic": "국내선",
        "international": "국제선",
        "mixed": "혼합",
    }.get((scope or "").lower(), scope or "")


def unique_codes(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output
