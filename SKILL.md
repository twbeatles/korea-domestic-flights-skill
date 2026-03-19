---
name: korea-domestic-flights
description: Search 대한민국 domestic flights using a Playwright-backed local scraper. Use when the user asks for 한국 국내선 항공권 검색, 김포-제주/부산-제주 같은 국내 노선 최저가 확인, 편도/왕복 조회, 날짜별 최저가 비교, 국내선 운임 요약, or route/date fare checks. Prefer this skill for Korean domestic airfare tasks; do not use it for international flights.
---

# Korea Domestic Flights

Use this skill for **대한민국 국내선 전용 항공권 검색**.

Current scope:
- 국내선 편도 검색
- 국내선 왕복 검색
- 날짜 범위 최저가 탐색
- JSON 출력
- 사람이 읽기 좋은 요약 출력

Do not use it for 국제선.

## Source dependency

This skill wraps the local project clone at:

- `tmp/Scraping-flight-information`

Main reused entry points:
- `scraping.searcher.FlightSearcher`
- `scraping.parallel.ParallelSearcher`

If the clone or its dependencies are missing, searches will fail.

## Scripts

### 1) Single-route domestic search

```bash
python skills/korea-domestic-flights/scripts/search_domestic.py --origin GMP --destination CJU --departure 2026-03-25 --human
```

Round trip:

```bash
python skills/korea-domestic-flights/scripts/search_domestic.py --origin GMP --destination CJU --departure 2026-03-25 --return-date 2026-03-28 --human
```

### 2) Date-range cheapest-day search

```bash
python skills/korea-domestic-flights/scripts/search_date_range.py --origin GMP --destination CJU --start-date 2026-03-25 --end-date 2026-03-30 --human
```

Round-trip-style date scan with fixed return offset:

```bash
python skills/korea-domestic-flights/scripts/search_date_range.py --origin GMP --destination CJU --start-date 2026-03-25 --end-date 2026-03-30 --return-offset 3 --human
```

## Parameters

`search_domestic.py`
- `--origin`: 출발 공항 코드
- `--destination`: 도착 공항 코드
- `--departure`: 출발일 `YYYY-MM-DD`
- `--return-date`: 귀국일 `YYYY-MM-DD` (선택)
- `--adults`: 성인 수, 기본값 `1`
- `--cabin`: `ECONOMY|BUSINESS|FIRST`
- `--max-results`: 최대 결과 수
- `--human`: 짧은 한국어 요약 출력

`search_date_range.py`
- `--origin`: 출발 공항 코드
- `--destination`: 도착 공항 코드
- `--start-date`: 범위 시작일 `YYYY-MM-DD`
- `--end-date`: 범위 종료일 `YYYY-MM-DD`
- `--return-offset`: 왕복 탐색용 귀국 오프셋 일수
- `--adults`: 성인 수
- `--cabin`: `ECONOMY|BUSINESS|FIRST`
- `--human`: 짧은 한국어 요약 출력

## Airport codes

For common Korean airport codes, read:
- `references/domestic-airports.md`

## Operational notes

- This skill depends on a working Playwright browser environment.
- If browser init fails, install or repair Chromium/Chrome/Edge in the source repo environment.
- The provider site DOM may change; if results suddenly disappear, the upstream scraper may need maintenance.
- For stable chat use, prefer `--human` summaries unless structured JSON is explicitly needed.
