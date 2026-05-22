from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

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


@dataclass
class TimePreference:
    depart_min: int | None = None
    depart_max: int | None = None
    return_min: int | None = None
    return_max: int | None = None
    exclude_before_depart: int | None = None
    prefer: str | None = None
    raw: str = ""

    def active(self) -> bool:
        return any(
            value is not None
            for value in [self.depart_min, self.depart_max, self.return_min, self.return_max, self.exclude_before_depart]
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
            parts.append(
                {
                    "late": "늦은 시간대 선호",
                    "morning": "오전 선호",
                    "afternoon": "오후 선호",
                    "evening": "저녁 선호",
                }.get(self.prefer, self.prefer)
            )
        return " · ".join(parts) if parts else None


def parse_time_to_minutes(value: str | None) -> int | None:
    if not value:
        return None
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?", str(value).strip())
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour * 60 + minute
    return None


def format_minutes(value: int | None) -> str:
    if value is None:
        return ""
    return f"{value // 60:02d}:{value % 60:02d}"


def _set_min(current: int | None, value: int) -> int:
    return value if current is None else max(current, value)


def _set_max(current: int | None, value: int) -> int:
    return value if current is None else min(current, value)


def _split_time_segments(text: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\s*(?:,|/|\||;| 그리고 | and )\s*", text) if part.strip()]
    return parts or [text.strip()]


def _segment_scope(segment: str) -> str:
    if any(keyword in segment for keyword in ["복귀", "귀환", "오는편", "오는 편", "리턴"]):
        return "return"
    return "depart"


def _apply_bucket(pref: TimePreference, scope: str, start_hour: int, end_hour: int) -> None:
    start = start_hour * 60
    end = end_hour * 60 + 59
    if scope == "return":
        pref.return_min = _set_min(pref.return_min, start)
        pref.return_max = _set_max(pref.return_max, end)
    else:
        pref.depart_min = _set_min(pref.depart_min, start)
        pref.depart_max = _set_max(pref.depart_max, end)


def _normalize_ranges(pref: TimePreference, raw: str) -> None:
    if pref.depart_min is not None and pref.depart_max is not None and pref.depart_min > pref.depart_max:
        pref.depart_max = None if "이후" in raw else pref.depart_max
        pref.depart_min = None if "이전" in raw else pref.depart_min
    if pref.return_min is not None and pref.return_max is not None and pref.return_min > pref.return_max:
        pref.return_max = None if "이후" in raw else pref.return_max
        pref.return_min = None if "이전" in raw else pref.return_min


def parse_time_preference_text(text: str | None) -> TimePreference:
    pref = TimePreference(raw=text or "")
    if not text:
        return pref
    normalized = str(text).strip().lower()
    normalized = normalized.replace("시 이후", "시이후").replace("시 이전", "시이전").replace("시 전", "시이전")
    for segment in _split_time_segments(normalized):
        scope = _segment_scope(segment)
        for key, (start_hour, end_hour) in TIME_BUCKETS.items():
            if key in segment and f"{key} 선호" not in segment:
                _apply_bucket(pref, scope, start_hour, end_hour)
        if "늦은 시간" in segment or "늦게" in segment:
            pref.prefer = pref.prefer or "late"
        elif "오전 선호" in segment:
            pref.prefer = pref.prefer or "morning"
        elif "오후 선호" in segment:
            pref.prefer = pref.prefer or "afternoon"
        elif "저녁 선호" in segment:
            pref.prefer = pref.prefer or "evening"

        patterns = [
            (r"출발\s*(\d{1,2})(?::(\d{2}))?\s*시?이후", "depart_min"),
            (r"출발\s*(\d{1,2})(?::(\d{2}))?\s*시?이전", "depart_max"),
            (r"(?:복귀|귀환|오는편|오는 편)\s*(\d{1,2})(?::(\d{2}))?\s*시?이후", "return_min"),
            (r"(?:복귀|귀환|오는편|오는 편)\s*(\d{1,2})(?::(\d{2}))?\s*시?이전", "return_max"),
            (r"너무\s*이른\s*비행\s*제외.*?(\d{1,2})(?::(\d{2}))?\s*시", "exclude_before_depart"),
            (r"(\d{1,2})(?::(\d{2}))?\s*시\s*이전\s*비행\s*제외", "exclude_before_depart"),
        ]
        for pattern, target in patterns:
            match = re.search(pattern, segment)
            if not match:
                continue
            minutes = int(match.group(1)) * 60 + int(match.group(2) or 0)
            current = getattr(pref, target)
            if target.endswith("_max"):
                setattr(pref, target, _set_max(current, minutes) if current is not None else minutes)
            elif target == "exclude_before_depart":
                setattr(pref, target, _set_min(current, minutes) if current is not None else minutes)
            else:
                setattr(pref, target, _set_min(current, minutes) if current is not None else minutes)
        _normalize_ranges(pref, segment)
    return pref


def apply_time_overrides(
    pref: TimePreference,
    *,
    depart_after: str | None = None,
    return_after: str | None = None,
    exclude_early_before: str | None = None,
    prefer: str | None = None,
) -> TimePreference:
    if depart_after:
        minutes = parse_time_to_minutes(depart_after)
        if minutes is None:
            raise ValueError(f"지원하지 않는 출발 시간 형식입니다: {depart_after}")
        pref.depart_min = _set_min(pref.depart_min, minutes)
    if return_after:
        minutes = parse_time_to_minutes(return_after)
        if minutes is None:
            raise ValueError(f"지원하지 않는 복귀 시간 형식입니다: {return_after}")
        pref.return_min = _set_min(pref.return_min, minutes)
    if exclude_early_before:
        minutes = parse_time_to_minutes(exclude_early_before)
        if minutes is None:
            raise ValueError(f"지원하지 않는 제외 시간 형식입니다: {exclude_early_before}")
        pref.exclude_before_depart = _set_min(pref.exclude_before_depart, minutes)
    if prefer:
        pref.prefer = prefer
    return pref


def build_time_preference(
    *,
    time_pref: str | None = None,
    depart_after: str | None = None,
    return_after: str | None = None,
    exclude_early_before: str | None = None,
    prefer: str | None = None,
) -> TimePreference:
    return apply_time_overrides(
        parse_time_preference_text(time_pref),
        depart_after=depart_after,
        return_after=return_after,
        exclude_early_before=exclude_early_before,
        prefer=prefer,
    )


def time_preference_cli_args(time_pref: dict | None) -> list[str]:
    payload = time_pref or {}
    args: list[str] = []
    if payload.get("time_pref"):
        args.extend(["--time-pref", str(payload["time_pref"])])
    if payload.get("depart_after"):
        args.extend(["--depart-after", str(payload["depart_after"])])
    if payload.get("return_after"):
        args.extend(["--return-after", str(payload["return_after"])])
    if payload.get("exclude_early_before"):
        args.extend(["--exclude-early-before", str(payload["exclude_early_before"])])
    if payload.get("prefer"):
        args.extend(["--prefer", str(payload["prefer"])])
    return args


def describe_time_preference_payload(time_pref: dict | None) -> str | None:
    payload = time_pref or {}
    return build_time_preference(
        time_pref=payload.get("time_pref"),
        depart_after=payload.get("depart_after"),
        return_after=payload.get("return_after"),
        exclude_early_before=payload.get("exclude_early_before"),
        prefer=payload.get("prefer"),
    ).describe()


def _within_range(value_minutes: int | None, min_minutes: int | None, max_minutes: int | None) -> bool:
    if value_minutes is None:
        return False
    if min_minutes is not None and value_minutes < min_minutes:
        return False
    if max_minutes is not None and value_minutes > max_minutes:
        return False
    return True


def score_time_preference(item: dict, pref: TimePreference) -> int:
    depart = parse_time_to_minutes(item.get("departure_time"))
    ret = parse_time_to_minutes(item.get("return_departure_time"))
    if pref.prefer == "late":
        return (depart or 0) + (ret or 0) // 2
    if pref.prefer == "morning":
        return -abs((depart or 12 * 60) - 9 * 60)
    if pref.prefer == "afternoon":
        return -abs((depart or 12 * 60) - 15 * 60)
    if pref.prefer == "evening":
        return -abs((depart or 12 * 60) - 19 * 60)
    return 0


def filter_and_rank_by_time_preference(items: Sequence[dict], pref: TimePreference) -> tuple[list[dict], list[dict]]:
    if not pref.active():
        rows = list(items)
        rows.sort(key=lambda item: int(item.get("price", 0) or 10**12))
        return rows, rows
    filtered: list[dict] = []
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
    filtered.sort(key=lambda item: int(item.get("price", 0) or 10**12))
    ranked = sorted(filtered, key=lambda item: (-score_time_preference(item, pref), int(item.get("price", 0) or 10**12)))
    return filtered, ranked
