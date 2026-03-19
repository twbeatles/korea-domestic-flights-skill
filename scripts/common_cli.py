from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Iterable, List, Sequence

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

AIRPORT_ALIASES = {
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
}

WEEKDAY_ALIASES = {
    "월": 0,
    "월요일": 0,
    "화": 1,
    "화요일": 1,
    "수": 2,
    "수요일": 2,
    "목": 3,
    "목요일": 3,
    "금": 4,
    "금요일": 4,
    "토": 5,
    "토요일": 5,
    "일": 6,
    "일요일": 6,
}

TIME_BUCKETS = {
    "새벽": (0, 5),
    "아침": (6, 10),
    "오전": (6, 11),
    "점심": (11, 13),
    "오후": (12, 17),
    "저녁": (18, 21),
    "밤": (20, 23),
    "야간": (20, 23),
    "늦은": (18, 23),
}


def airport_label(code: str) -> str:
    code = (code or "").upper()
    return f"{AIRPORT_NAMES.get(code, code)}({code})" if code else ""


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
    raise ValueError(f"지원하지 않는 공항 입력입니다: {value}")


def _base_today() -> datetime:
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_month_day(raw: str, today: datetime) -> datetime | None:
    match = re.fullmatch(r"(\d{1,2})[./\-월\s]+(\d{1,2})(?:일)?", raw)
    if not match:
        return None
    month = int(match.group(1))
    day = int(match.group(2))
    year = today.year
    candidate = datetime(year, month, day)
    if candidate < today:
        candidate = datetime(year + 1, month, day)
    return candidate


def _parse_relative_days(raw: str, today: datetime) -> datetime | None:
    match = re.fullmatch(r"(\d+)\s*(?:일 뒤|일후|days? later)", raw)
    if match:
        return today + timedelta(days=int(match.group(1)))
    match = re.fullmatch(r"(\d+)\s*(?:주 뒤|주후)", raw)
    if match:
        return today + timedelta(days=7 * int(match.group(1)))
    return None


def _next_weekday(today: datetime, weekday: int, week_offset: int = 0) -> datetime:
    days_ahead = (weekday - today.weekday()) % 7
    candidate = today + timedelta(days=days_ahead + week_offset * 7)
    if week_offset == 0 and candidate < today:
        candidate += timedelta(days=7)
    return candidate


def _parse_weekday(raw: str, today: datetime) -> datetime | None:
    raw = raw.strip()
    for prefix, offset in (("이번주 ", 0), ("이번 주 ", 0), ("다음주 ", 1), ("다음 주 ", 1), ("오는 ", 0)):
        if raw.startswith(prefix):
            tail = raw[len(prefix):].strip()
            if tail in WEEKDAY_ALIASES:
                return _next_weekday(today, WEEKDAY_ALIASES[tail], offset)
    if raw in WEEKDAY_ALIASES:
        return _next_weekday(today, WEEKDAY_ALIASES[raw], 0)
    if raw in ("주말", "이번주말", "이번 주말"):
        return _next_weekday(today, 5, 0)
    if raw in ("다음주말", "다음 주말"):
        return _next_weekday(today, 5, 1)
    return None


def parse_flexible_date(value: str) -> datetime:
    raw = value.strip().lower()
    today = _base_today()
    mapping = {
        "today": 0,
        "오늘": 0,
        "tomorrow": 1,
        "내일": 1,
        "day after tomorrow": 2,
        "모레": 2,
        "글피": 3,
    }
    if raw in mapping:
        return today + timedelta(days=mapping[raw])
    relative = _parse_relative_days(raw, today)
    if relative:
        return relative
    weekday = _parse_weekday(raw, today)
    if weekday:
        return weekday
    month_day = _parse_month_day(raw.replace("  ", " "), today)
    if month_day:
        return month_day
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError(f"지원하지 않는 날짜 형식입니다: {value}")


def parse_date_range_text(value: str) -> tuple[datetime, datetime]:
    raw = value.strip().lower()
    today = _base_today()
    m = re.fullmatch(r"(.+?)부터\s*(\d+)일", raw)
    if m:
        start = parse_flexible_date(m.group(1))
        days = int(m.group(2))
        return start, start + timedelta(days=max(days - 1, 0))
    if raw in ("이번주말", "이번 주말", "주말"):
        start = _next_weekday(today, 5, 0)
        return start, start + timedelta(days=1)
    if raw in ("다음주말", "다음 주말"):
        start = _next_weekday(today, 5, 1)
        return start, start + timedelta(days=1)
    parts = re.split(r"\s*(?:~|부터|to|-)\s*", value)
    if len(parts) == 2 and all(part.strip() for part in parts):
        start = parse_flexible_date(parts[0].strip())
        end = parse_flexible_date(parts[1].strip())
        return start, end
    single = parse_flexible_date(value)
    return single, single


def pretty_date(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def compact_date(value: datetime) -> str:
    return value.strftime("%Y%m%d")


def cabin_label(code: str) -> str:
    return {
        "ECONOMY": "이코노미",
        "BUSINESS": "비즈니스",
        "FIRST": "일등석",
    }.get((code or "").upper(), code or "")


def format_price(value: int | float | None) -> str:
    return f"{int(value or 0):,}원"


def summarize_price_gap(best_price: int, next_price: int | None) -> str | None:
    if not best_price or not next_price or next_price <= best_price:
        return None
    gap = next_price - best_price
    ratio = round((gap / best_price) * 100)
    return f"2위보다 {gap:,}원 저렴해 가성비가 좋습니다{f' (약 {ratio}% 차이)' if ratio >= 5 else ''}."


def recommendation_line(subject: str, best_price: int, next_price: int | None = None) -> str:
    gap_text = summarize_price_gap(best_price, next_price)
    if gap_text:
        return f"추천: 이번 조건에서는 {subject}이(가) 가장 유리합니다. {gap_text}"
    return f"추천: 이번 조건에서는 {subject}이(가) 가장 무난한 최저가 선택입니다."


def bullet_rank_lines(items: Sequence[dict], label_key: str, price_key: str, detail_builder=None, limit: int = 5) -> List[str]:
    lines: List[str] = []
    for idx, item in enumerate(items[:limit], start=1):
        label = item.get(label_key, "옵션")
        price = item.get(price_key, 0)
        if price and price > 0:
            detail = detail_builder(item) if detail_builder else ""
            suffix = f" · {detail}" if detail else ""
            lines.append(f"{idx}. {label} · {format_price(price)}{suffix}")
        else:
            lines.append(f"{idx}. {label} · 결과 없음")
    return lines


def unique_codes(values: Iterable[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def parse_time_to_minutes(value: str | None) -> int | None:
    if not value:
        return None
    raw = str(value).strip()
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?", raw)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour * 60 + minute
    return None


class TimePreference:
    def __init__(
        self,
        depart_min: int | None = None,
        depart_max: int | None = None,
        return_min: int | None = None,
        return_max: int | None = None,
        exclude_before_depart: int | None = None,
        prefer: str | None = None,
        raw: str | None = None,
    ):
        self.depart_min = depart_min
        self.depart_max = depart_max
        self.return_min = return_min
        self.return_max = return_max
        self.exclude_before_depart = exclude_before_depart
        self.prefer = prefer
        self.raw = raw or ""

    def active(self) -> bool:
        return any(
            value is not None for value in [self.depart_min, self.depart_max, self.return_min, self.return_max, self.exclude_before_depart]
        ) or bool(self.prefer)

    def describe(self) -> str | None:
        parts: list[str] = []
        if self.depart_min is not None:
            parts.append(f"출발 {format_minutes(self.depart_min)} 이후")
        if self.depart_max is not None:
            parts.append(f"출발 {format_minutes(self.depart_max)} 이전")
        if self.return_min is not None:
            parts.append(f"복귀 {format_minutes(self.return_min)} 이후")
        if self.return_max is not None:
            parts.append(f"복귀 {format_minutes(self.return_max)} 이전")
        if self.exclude_before_depart is not None:
            parts.append(f"너무 이른 비행 제외({format_minutes(self.exclude_before_depart)} 이전 제외)")
        if self.prefer:
            prefer_map = {
                "late": "늦은 시간대 선호",
                "morning": "오전 선호",
                "afternoon": "오후 선호",
                "evening": "저녁 선호",
            }
            parts.append(prefer_map.get(self.prefer, self.prefer))
        return " · ".join(parts) if parts else None


def format_minutes(value: int | None) -> str:
    if value is None:
        return ""
    hour = value // 60
    minute = value % 60
    return f"{hour:02d}:{minute:02d}"


def parse_time_preference_text(text: str | None) -> TimePreference:
    pref = TimePreference(raw=text or "")
    if not text:
        return pref
    raw = str(text).strip().lower()
    normalized = raw.replace("시 이후", "시이후").replace("시 이전", "시이전").replace("시 전", "시이전")

    for key, (start_hour, end_hour) in TIME_BUCKETS.items():
        if key in normalized:
            if "복귀" in normalized or "귀환" in normalized or "오는편" in normalized:
                pref.return_min = pref.return_min if pref.return_min is not None else start_hour * 60
                pref.return_max = pref.return_max if pref.return_max is not None else end_hour * 60 + 59
            else:
                pref.depart_min = pref.depart_min if pref.depart_min is not None else start_hour * 60
                pref.depart_max = pref.depart_max if pref.depart_max is not None else end_hour * 60 + 59

    if "늦은 시간" in normalized or "늦게" in normalized:
        pref.prefer = pref.prefer or "late"
    elif "오전 선호" in normalized:
        pref.prefer = pref.prefer or "morning"
    elif "오후 선호" in normalized:
        pref.prefer = pref.prefer or "afternoon"
    elif "저녁 선호" in normalized:
        pref.prefer = pref.prefer or "evening"

    for pattern, target in [
        (r"출발\s*(\d{1,2})(?::(\d{2}))?\s*시?이후", "depart_min"),
        (r"출발\s*(\d{1,2})(?::(\d{2}))?\s*시?이전", "depart_max"),
        (r"복귀\s*(\d{1,2})(?::(\d{2}))?\s*시?이후", "return_min"),
        (r"귀환\s*(\d{1,2})(?::(\d{2}))?\s*시?이후", "return_min"),
        (r"오는편\s*(\d{1,2})(?::(\d{2}))?\s*시?이후", "return_min"),
        (r"복귀\s*(\d{1,2})(?::(\d{2}))?\s*시?이전", "return_max"),
        (r"귀환\s*(\d{1,2})(?::(\d{2}))?\s*시?이전", "return_max"),
        (r"오는편\s*(\d{1,2})(?::(\d{2}))?\s*시?이전", "return_max"),
        (r"너무\s*이른\s*비행\s*제외.*?(\d{1,2})(?::(\d{2}))?\s*시", "exclude_before_depart"),
        (r"(\d{1,2})(?::(\d{2}))?\s*시\s*이전\s*비행\s*제외", "exclude_before_depart"),
    ]:
        match = re.search(pattern, normalized)
        if match:
            minutes = int(match.group(1)) * 60 + int(match.group(2) or 0)
            setattr(pref, target, minutes)

    return pref


def _within_range(value_minutes: int | None, min_minutes: int | None, max_minutes: int | None) -> bool:
    if value_minutes is None:
        return False
    if min_minutes is not None and value_minutes < min_minutes:
        return False
    if max_minutes is not None and value_minutes > max_minutes:
        return False
    return True


def _score_time_preference(item: dict, pref: TimePreference) -> int:
    depart = parse_time_to_minutes(item.get("departure_time"))
    ret = parse_time_to_minutes(item.get("return_departure_time"))
    score = 0
    if pref.prefer == "late":
        score += depart or 0
        score += (ret or 0) // 2
    elif pref.prefer == "morning":
        score -= abs((depart or 12 * 60) - 9 * 60)
    elif pref.prefer == "afternoon":
        score -= abs((depart or 12 * 60) - 15 * 60)
    elif pref.prefer == "evening":
        score -= abs((depart or 12 * 60) - 19 * 60)
    return score


def filter_and_rank_by_time_preference(items: Sequence[dict], pref: TimePreference) -> tuple[list[dict], list[dict]]:
    if not pref.active():
        return list(items), sorted(list(items), key=lambda x: x.get("price", 0) if x.get("price", 0) > 0 else 10**12)

    filtered = []
    for item in items:
        depart = parse_time_to_minutes(item.get("departure_time"))
        ret = parse_time_to_minutes(item.get("return_departure_time"))
        if pref.exclude_before_depart is not None and (depart is None or depart < pref.exclude_before_depart):
            continue
        if (pref.depart_min is not None or pref.depart_max is not None) and not _within_range(depart, pref.depart_min, pref.depart_max):
            continue
        if item.get("is_round_trip") and (pref.return_min is not None or pref.return_max is not None) and not _within_range(ret, pref.return_min, pref.return_max):
            continue
        filtered.append(item)

    ranked = sorted(
        filtered,
        key=lambda x: (
            -_score_time_preference(x, pref),
            x.get("price", 0) if x.get("price", 0) > 0 else 10**12,
        ),
    )
    filtered.sort(key=lambda x: x.get("price", 0) if x.get("price", 0) > 0 else 10**12)
    return filtered, ranked


def choose_preferred_option(items: Sequence[dict], pref: TimePreference) -> dict | None:
    _, ranked = filter_and_rank_by_time_preference(items, pref)
    return ranked[0] if ranked else None


def time_preference_recommendation(preferred: dict | None, cheapest: dict | None, pref: TimePreference) -> str | None:
    if not pref.active() or not preferred:
        return None
    subject = preferred.get("airline", "옵션")
    depart = preferred.get("departure_time") or "시간미상"
    price = preferred.get("price", 0)
    if cheapest and cheapest is not preferred and cheapest.get("price", 0) > 0 and price > 0:
        gap = price - cheapest.get("price", 0)
        gap_text = f"최저가 대비 {gap:,}원 추가" if gap > 0 else "최저가와 동일 가격"
    else:
        gap_text = "최저가와 같은 옵션"
    detail = pref.describe() or "시간 선호"
    if preferred.get("is_round_trip") and preferred.get("return_departure_time"):
        return f"시간대 추천: {detail} 기준으로는 {subject} 가는편 {depart}, 오는편 {preferred.get('return_departure_time')} 옵션이 적합합니다 ({gap_text})."
    return f"시간대 추천: {detail} 기준으로는 {subject} {depart} 출발 옵션이 적합합니다 ({gap_text})."
