from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    SEOUL_TIMEZONE = ZoneInfo("Asia/Seoul")
except ZoneInfoNotFoundError:
    SEOUL_TIMEZONE = timezone(timedelta(hours=9), name="Asia/Seoul")

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


def seoul_now() -> datetime:
    return datetime.now(SEOUL_TIMEZONE)


def base_today() -> datetime:
    now = seoul_now()
    return datetime(now.year, now.month, now.day)


def _parse_month_day(raw: str, today: datetime) -> datetime | None:
    match = re.fullmatch(r"(\d{1,2})[./\-월\s]+(\d{1,2})(?:일)?", raw)
    if not match:
        return None
    month = int(match.group(1))
    day = int(match.group(2))
    candidate = datetime(today.year, month, day)
    return candidate if candidate >= today else datetime(today.year + 1, month, day)


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
    return today + timedelta(days=days_ahead + week_offset * 7)


def _parse_weekday(raw: str, today: datetime) -> datetime | None:
    for prefix, offset in (("이번주 ", 0), ("이번 주 ", 0), ("다음주 ", 1), ("다음 주 ", 1), ("오는 ", 0)):
        if raw.startswith(prefix):
            tail = raw[len(prefix):].strip()
            if tail in WEEKDAY_ALIASES:
                return _next_weekday(today, WEEKDAY_ALIASES[tail], offset)
    if raw in WEEKDAY_ALIASES:
        return _next_weekday(today, WEEKDAY_ALIASES[raw], 0)
    if raw in {"주말", "이번주말", "이번 주말"}:
        return _next_weekday(today, 5, 0)
    if raw in {"다음주말", "다음 주말"}:
        return _next_weekday(today, 5, 1)
    return None


def parse_flexible_date(value: str) -> datetime:
    raw = value.strip().lower()
    today = base_today()
    relative = {
        "today": 0,
        "오늘": 0,
        "tomorrow": 1,
        "내일": 1,
        "day after tomorrow": 2,
        "모레": 2,
        "글피": 3,
    }
    if raw in relative:
        return today + timedelta(days=relative[raw])
    parsed = _parse_relative_days(raw, today) or _parse_weekday(raw, today) or _parse_month_day(raw.replace("  ", " "), today)
    if parsed:
        return parsed
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError(f"지원하지 않는 날짜 형식입니다: {value}")


def parse_date_range_text(value: str) -> tuple[datetime, datetime]:
    raw = value.strip().lower()
    today = base_today()
    match = re.fullmatch(r"(.+?)부터\s*(\d+)일", raw)
    if match:
        start = parse_flexible_date(match.group(1))
        return start, start + timedelta(days=max(int(match.group(2)) - 1, 0))
    if raw in {"이번주말", "이번 주말", "주말"}:
        start = _next_weekday(today, 5, 0)
        return start, start + timedelta(days=1)
    if raw in {"다음주말", "다음 주말"}:
        start = _next_weekday(today, 5, 1)
        return start, start + timedelta(days=1)

    explicit_patterns = [
        r"^\s*(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{8})\s*~\s*(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{8})\s*$",
        r"^\s*(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{8})\s*to\s*(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{8})\s*$",
        r"^\s*(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{8})\s*부터\s*(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{8})\s*(?:까지)?\s*$",
    ]
    for pattern in explicit_patterns:
        matched = re.fullmatch(pattern, value, re.IGNORECASE)
        if matched:
            return parse_flexible_date(matched.group(1).strip()), parse_flexible_date(matched.group(2).strip())

    parts = re.split(r"\s*(?:~|부터|to)\s*", value, maxsplit=1)
    if len(parts) == 2 and all(part.strip() for part in parts):
        return parse_flexible_date(parts[0].strip()), parse_flexible_date(parts[1].strip())
    single = parse_flexible_date(value)
    return single, single


def build_dates(start_date: datetime, end_date: datetime) -> list[datetime]:
    if end_date < start_date:
        raise ValueError("end-date must be after or equal to start-date")
    days: list[datetime] = []
    current = start_date
    while current <= end_date:
        days.append(current)
        current += timedelta(days=1)
    return days


def pretty_date(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def compact_date(value: datetime) -> str:
    return value.strftime("%Y%m%d")


def verify_date_order(departure: str, return_date: str | None = None) -> None:
    if not return_date:
        return
    if datetime.strptime(return_date, "%Y-%m-%d") < datetime.strptime(departure, "%Y-%m-%d"):
        raise ValueError("return-date 는 departure 와 같거나 이후여야 합니다.")


def verify_return_offset(return_offset: int) -> None:
    if return_offset < 0:
        raise ValueError("--return-offset 는 0 이상이어야 합니다.")


def return_offset_from_dates(departure: str, return_date: str | None) -> int:
    if not return_date:
        return 0
    dep = datetime.strptime(departure, "%Y-%m-%d")
    ret = datetime.strptime(return_date, "%Y-%m-%d")
    if ret < dep:
        raise ValueError("return-date 는 departure 와 같거나 이후여야 합니다.")
    return (ret - dep).days
