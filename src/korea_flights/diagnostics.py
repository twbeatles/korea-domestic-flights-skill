from __future__ import annotations

from collections.abc import Callable, Iterable

REASON_LABELS = {
    "not_attempted": "미시도",
    "broad_only": "빠른 스캔 전용",
    "detailed_match": "상세 검색 일치",
    "detailed_match_with_time_pref": "시간 조건 일치",
    "broad_candidate_time_rejected": "시간 조건 탈락",
    "detailed_no_usable_time_filter_match": "usable match 없음",
    "detail_empty_after_broad_hit": "빠른 스캔 가격 있었지만 상세 결과 비어 있음",
    "detail_empty_no_broad_signal": "상세 결과 비어 있음",
    "detail_missing_departure_times": "출발 시간 정보 부족",
    "detail_partial_departure_times": "출발 시간 정보 부분 누락",
    "detail_missing_return_times": "복귀 시간 정보 부족",
    "detail_partial_return_times": "복귀 시간 정보 부분 누락",
    "detail_missing_price_data": "가격 정보 부족",
    "detail_sparse_price_data": "가격 정보 일부 누락",
}

REASON_CODES = {
    "not_attempted": "diagnostic.not_attempted",
    "broad_only": "diagnostic.broad_only",
    "detailed_match": "success.detail_match",
    "detailed_match_with_time_pref": "success.time_pref_match",
    "broad_candidate_time_rejected": "filter.time_pref_rejected",
    "detailed_no_usable_time_filter_match": "filter.no_usable_match",
    "detail_empty_after_broad_hit": "extraction.detail_empty_after_broad_hit",
    "detail_empty_no_broad_signal": "extraction.detail_empty_no_broad_signal",
    "detail_missing_departure_times": "extraction.missing_departure_times",
    "detail_partial_departure_times": "extraction.partial_departure_times",
    "detail_missing_return_times": "extraction.missing_return_times",
    "detail_partial_return_times": "extraction.partial_return_times",
    "detail_missing_price_data": "extraction.missing_price_data",
    "detail_sparse_price_data": "extraction.sparse_price_data",
}

REASON_CATEGORIES = {
    "not_attempted": "diagnostic",
    "broad_only": "diagnostic",
    "detailed_match": "success",
    "detailed_match_with_time_pref": "success",
    "broad_candidate_time_rejected": "time_filter",
    "detailed_no_usable_time_filter_match": "time_filter",
    "detail_empty_after_broad_hit": "extraction",
    "detail_empty_no_broad_signal": "extraction",
    "detail_missing_departure_times": "extraction",
    "detail_partial_departure_times": "extraction",
    "detail_missing_return_times": "extraction",
    "detail_partial_return_times": "extraction",
    "detail_missing_price_data": "extraction",
    "detail_sparse_price_data": "extraction",
}

REASON_PRIORITY = {
    "detail_empty_after_broad_hit": 100,
    "detail_missing_return_times": 95,
    "detail_missing_departure_times": 94,
    "detail_missing_price_data": 93,
    "detail_partial_return_times": 92,
    "detail_partial_departure_times": 91,
    "detail_sparse_price_data": 90,
    "broad_candidate_time_rejected": 70,
    "detailed_no_usable_time_filter_match": 69,
    "detailed_match_with_time_pref": 10,
    "detailed_match": 9,
    "broad_only": 2,
    "not_attempted": 1,
}


def reason_code(reason: str | None) -> str | None:
    if not reason:
        return None
    return REASON_CODES.get(reason, f"unknown.{reason}")


def reason_category(reason: str | None) -> str | None:
    if not reason:
        return None
    return REASON_CATEGORIES.get(reason, "unknown")


def classify_refine_row(row: dict | None) -> str:
    if not row:
        return "not_attempted"
    explicit = str(row.get("diagnostic_reason") or "").strip()
    if explicit:
        return explicit
    if row.get("search_stage") == "broad_only":
        return "broad_only"
    raw_count = int(row.get("raw_option_count") or 0)
    valid_count = int(row.get("time_pref_valid_count") or 0)
    broad_price = int(row.get("broad_price") or 0)
    if valid_count > 0:
        return "detailed_match_with_time_pref" if row.get("time_pref_match") else "detailed_match"
    if raw_count <= 0:
        return "detail_empty_after_broad_hit" if broad_price > 0 else "detail_empty_no_broad_signal"
    if broad_price > 0:
        return "broad_candidate_time_rejected"
    return "detailed_no_usable_time_filter_match"


def _rank_reasons(counts: dict[str, int]) -> list[dict]:
    rows = []
    for reason, count in counts.items():
        rows.append(
            {
                "reason": reason,
                "reason_code": reason_code(reason),
                "label": REASON_LABELS.get(reason, reason),
                "category": reason_category(reason),
                "count": count,
                "priority": REASON_PRIORITY.get(reason, 0),
            }
        )
    rows.sort(key=lambda item: (-item["priority"], -item["count"], item["reason"]))
    return rows


def build_refine_diagnostics(
    broad_rows: Iterable[dict],
    detailed_rows: Iterable[dict],
    *,
    key_fn: Callable[[dict], object],
    label_fn: Callable[[dict], str],
    sample_limit: int = 5,
) -> dict:
    broad_rows = list(broad_rows)
    detailed_rows = list(detailed_rows)
    detailed_map = {key_fn(row): row for row in detailed_rows}
    counts: dict[str, int] = {}
    samples: dict[str, list[str]] = {}
    extraction_totals = {
        "rows": 0,
        "raw_options": 0,
        "priced_options": 0,
        "departure_time_options": 0,
        "return_time_options": 0,
        "missing_price_rows": 0,
        "sparse_price_rows": 0,
        "missing_departure_time_rows": 0,
        "partial_departure_time_rows": 0,
        "missing_return_time_rows": 0,
        "partial_return_time_rows": 0,
    }

    for broad in broad_rows:
        key = key_fn(broad)
        merged = dict(broad)
        detailed = detailed_map.get(key)
        if detailed is not None:
            merged.update(detailed)
        reason = classify_refine_row(merged)
        counts[reason] = counts.get(reason, 0) + 1
        samples.setdefault(reason, [])
        label = label_fn(merged)
        hint = str((merged.get("diagnostic_detail") or {}).get("hint") or "").strip()
        if hint:
            label = f"{label} ({hint})"
        if len(samples[reason]) < sample_limit:
            samples[reason].append(label)

        if detailed is not None:
            raw_count = int(merged.get("raw_option_count") or 0)
            priced_count = int(merged.get("priced_option_count") or 0)
            depart_count = int(merged.get("departure_time_count") or 0)
            ret_count = int(merged.get("return_time_count") or 0)
            extraction_totals["rows"] += 1
            extraction_totals["raw_options"] += raw_count
            extraction_totals["priced_options"] += priced_count
            extraction_totals["departure_time_options"] += depart_count
            extraction_totals["return_time_options"] += ret_count
            if raw_count > 0:
                if priced_count <= 0:
                    extraction_totals["missing_price_rows"] += 1
                elif priced_count < raw_count:
                    extraction_totals["sparse_price_rows"] += 1
                if depart_count <= 0:
                    extraction_totals["missing_departure_time_rows"] += 1
                elif depart_count < raw_count:
                    extraction_totals["partial_departure_time_rows"] += 1
                if bool(merged.get("has_return_time_constraint")):
                    if ret_count <= 0:
                        extraction_totals["missing_return_time_rows"] += 1
                    elif ret_count < raw_count:
                        extraction_totals["partial_return_time_rows"] += 1

    attempted = len(detailed_map)
    broad_available = sum(1 for row in broad_rows if int(row.get("price", 0) or 0) > 0)
    success = counts.get("detailed_match_with_time_pref", 0) + counts.get("detailed_match", 0)
    rejected = counts.get("broad_candidate_time_rejected", 0) + counts.get("detailed_no_usable_time_filter_match", 0)
    extraction_reasons = [
        "detail_empty_after_broad_hit",
        "detail_empty_no_broad_signal",
        "detail_missing_departure_times",
        "detail_partial_departure_times",
        "detail_missing_return_times",
        "detail_partial_return_times",
        "detail_missing_price_data",
        "detail_sparse_price_data",
    ]
    extraction_incomplete = sum(counts.get(reason, 0) for reason in extraction_reasons)
    empty_like = counts.get("detail_empty_after_broad_hit", 0) + counts.get("detail_empty_no_broad_signal", 0)
    attempted_with_broad = max(1, sum(1 for row in detailed_rows if int(row.get("broad_price", 0) or 0) > 0))
    ranked_reasons = _rank_reasons(counts)
    dominant_reason = ranked_reasons[0]["reason"] if ranked_reasons else None

    summary_bits = []
    if success:
        summary_bits.append(f"상세 성공 {success}건")
    if rejected:
        summary_bits.append(f"시간 조건/usable 탈락 {rejected}건")
    if extraction_incomplete:
        summary_bits.append(f"추출 불완전 {extraction_incomplete}건")
    if not summary_bits:
        summary_bits.append("상세 진단 데이터 없음")

    developer_hint = None
    human_hint = None
    if counts.get("detail_empty_after_broad_hit"):
        human_hint = "일부 후보는 빠른 스캔 가격이 있었지만 상세 단계에서 빈결과가 나와 추가 후보를 다시 확인했습니다."
        developer_hint = "broad/detail 불일치 빈도가 있어 upstream DOM/API 변화나 상세 추출 불안정을 점검하세요."
    elif counts.get("detail_missing_return_times") or counts.get("detail_partial_return_times"):
        human_hint = "일부 왕복 후보는 복귀 시간 정보가 부족해 시간 조건 판단 신뢰도가 낮았습니다."
        developer_hint = "return_departure_time 추출 커버리지를 점검하세요."
    elif rejected:
        human_hint = "빠른 스캔 저가 후보 중 일부는 요청한 시간 조건과 맞지 않아 제외됐습니다."

    return {
        "counts": counts,
        "reason_codes": {reason: reason_code(reason) for reason in counts},
        "reason_categories": {reason: reason_category(reason) for reason in counts},
        "ranked_reasons": ranked_reasons,
        "samples": samples,
        "summary_text": ", ".join(summary_bits),
        "broad_available": broad_available,
        "attempted": attempted,
        "success": success,
        "rejected": rejected,
        "extraction_incomplete": extraction_incomplete,
        "empty_like": empty_like,
        "remaining_available": max(0, broad_available - attempted),
        "rejection_ratio": rejected / attempted_with_broad,
        "empty_like_ratio": empty_like / max(1, attempted),
        "extraction_incomplete_ratio": extraction_incomplete / max(1, attempted),
        "dominant_reason": dominant_reason,
        "dominant_reason_code": reason_code(dominant_reason),
        "dominant_reason_category": reason_category(dominant_reason),
        "dominant_reason_label": REASON_LABELS.get(dominant_reason, dominant_reason) if dominant_reason else None,
        "primary_interpretation": (
            "extraction_incomplete"
            if reason_category(dominant_reason) == "extraction"
            else ("time_filter_rejection" if reason_category(dominant_reason) == "time_filter" else reason_category(dominant_reason))
        ),
        "human_hint": human_hint,
        "user_hint": human_hint,
        "developer_hint": developer_hint,
        "extraction_summary": {
            **extraction_totals,
            "price_coverage_ratio": extraction_totals["priced_options"] / max(1, extraction_totals["raw_options"]),
            "departure_time_coverage_ratio": extraction_totals["departure_time_options"] / max(1, extraction_totals["raw_options"]),
            "return_time_coverage_ratio": extraction_totals["return_time_options"] / max(1, extraction_totals["raw_options"]),
        },
    }


def choose_fallback_plan(diag: dict, *, minimum_target: int, hard_cap: int, pad: int) -> dict:
    broad_available = int(diag.get("broad_available") or 0)
    success = int(diag.get("success") or 0)
    remaining_available = int(diag.get("remaining_available") or 0)
    rejected = int(diag.get("rejected") or 0)
    extraction_incomplete = int(diag.get("extraction_incomplete") or 0)
    empty_like = int(diag.get("empty_like") or 0)
    rejection_ratio = float(diag.get("rejection_ratio") or 0.0)
    empty_like_ratio = float(diag.get("empty_like_ratio") or 0.0)
    extraction_ratio = float(diag.get("extraction_incomplete_ratio") or 0.0)
    dominant_reason = str(diag.get("dominant_reason") or "")
    dominant_category = str(diag.get("dominant_reason_category") or "")
    target = min(max(1, minimum_target), broad_available) if broad_available else 0
    shortfall = max(0, target - success)

    reasons: list[str] = []
    if shortfall > 0:
        reasons.append("coverage.time_pref_shortfall")
    if success == 0 and rejected > 0:
        reasons.append("coverage.zero_success_with_rejections")
    if remaining_available > 0 and rejection_ratio >= 0.5:
        reasons.append("signal.high_time_filter_rejection_ratio")
    if remaining_available > 0 and extraction_incomplete > 0 and extraction_ratio >= 0.35:
        reasons.append("signal.high_extraction_incomplete_ratio")
    if remaining_available > 0 and empty_like > 0 and empty_like_ratio >= 0.35:
        reasons.append("signal.high_empty_like_ratio")
    if remaining_available > 0 and dominant_reason == "detail_empty_after_broad_hit":
        reasons.append("signal.broad_detail_disagreement")
    if remaining_available > 0 and dominant_category == "extraction":
        reasons.append(f"signal.extraction_dominant:{reason_code(dominant_reason)}")
    if remaining_available > 0 and dominant_category == "time_filter":
        reasons.append(f"signal.time_filter_dominant:{reason_code(dominant_reason)}")

    triggered = bool(reasons) and remaining_available > 0
    limit = 0
    if triggered:
        extra_pad = pad + (1 if dominant_category == "extraction" else 0)
        limit = min(remaining_available, max(shortfall + extra_pad, min(hard_cap, remaining_available)))
    return {
        "triggered": triggered,
        "target": target,
        "shortfall": shortfall,
        "limit": limit,
        "reasons": reasons,
        "primary_reason": reasons[0] if reasons else None,
        "dominant_reason": dominant_reason or None,
        "dominant_reason_code": reason_code(dominant_reason),
        "dominant_reason_category": dominant_category or None,
    }
