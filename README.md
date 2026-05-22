# Korea Flights

`openclaw-korea-domestic-flights` 저장소는 설치 호환성을 위해 기존 리포지토리 이름을 유지하지만, 현재 주 인터페이스는 **`korea-flights` Python 패키지형 OpenClaw 스킬**입니다.

- 배포명: `korea-flights`
- Python import: `korea_flights`
- 콘솔 명령: `korea-flights`
- legacy 저장소/설치 식별자: `openclaw-korea-domestic-flights`
- 런타임 스크래핑 코어: 로컬 `Scraping-flight-information` 저장소 adapter

이 저장소는 스크래핑 코어를 복사하지 않습니다. `D:\twbeatles-repos\Scraping-flight-information` 같은 로컬 Flight Bot 저장소를 찾아 `scraping.searcher.FlightSearcher`와 `scraping.parallel.ParallelSearcher`를 adapter로 감쌉니다.

## 주요 기능

- 단일 노선 검색: 국내선/국제선, 편도/왕복, 좌석등급, 성인 수
- 날짜 범위 검색: 기본 최대 45일, `--max-days`로 조정
- 목적지+날짜 매트릭스: 기본 최대 120조합, `--max-combos`로 조정
- 하이브리드 전략 엔진: `broad_scan -> candidate_scoring -> detailed_refine -> diagnostic_fallback -> final_ranking`
- 시간 조건: `저녁`, `출발 10시 이후`, `복귀 18시 이후`, `늦은 시간 선호`
- 안정 JSON 계약: `status`, `query`, `summary`, `results`, `strategy_metadata`, `diagnostics`, `logs`
- 가격 감시 저장소: 목표가, dedupe, custom message template, 다중 목적지/날짜 범위 지원
- 패키징: wheel/sdist와 `korea-flights` console script
- 배포 계약: PyInstaller `.spec` 파일 없이 `pyproject.toml` 기반 Python 패키지로 검증

## 설치

개발 모드:

```bash
python -m pip install -e .[dev]
```

빌드 산출물 설치:

```bash
python -m build
python -m pip install dist/korea_flights-0.1.0-py3-none-any.whl
```

참조 저장소는 아래 순서로 탐색합니다.

1. `--repo-path`
2. `KDF_SOURCE_REPO`
3. `SCRAPING_FLIGHT_INFORMATION_REPO`
4. 현재 작업 폴더/상위 폴더의 `tmp/Scraping-flight-information`
5. 현재 작업 폴더/상위 폴더의 `Scraping-flight-information`

## CLI 사용

상태 점검:

```bash
korea-flights doctor --repo-path D:\twbeatles-repos\Scraping-flight-information
```

단일 검색:

```bash
korea-flights search --origin 김포 --destination 제주 --departure 내일 --human
korea-flights search --origin ICN --destination NRT --departure 내일 --scope international --json
```

날짜 범위 검색:

```bash
korea-flights range --origin ICN --destination KIX --date-range "다음주말" --scope international --human
korea-flights range --origin 김포 --destination 제주 --start-date 2026-06-01 --end-date 2026-06-15 --time-pref "복귀 18시 이후" --return-offset 2 --refine-budget 10 --fallback-budget 6 --json
```

목적지+날짜 매트릭스:

```bash
korea-flights matrix --origin ICN --destinations NRT,KIX,FUK --date-range "내일부터 7일" --scope international --human
korea-flights matrix --origin 김포 --destinations 제주,부산,여수 --start-date 2026-06-01 --end-date 2026-06-10 --max-combos 120 --json
```

가격 알림:

```bash
korea-flights alert add --origin 김포 --destination 제주 --date-range "다음주말" --return-offset 2 --target-price 150000 --time-pref "복귀 18시 이후"
korea-flights alert list
korea-flights alert check --no-dedupe
```

얕은 live smoke:

```bash
korea-flights live-smoke --repo-path D:\twbeatles-repos\Scraping-flight-information --json
```

`live-smoke`는 가격 자체를 고정 검증하지 않고 국내선/국제선 검색이 비정상 종료되지 않는지와 결과 source 신호를 확인합니다.

## 전략 엔진

`HybridStrategyEngine`은 날짜 범위와 매트릭스 검색에서 같은 파이프라인을 사용합니다.

1. `broad_scan`: upstream `ParallelSearcher`로 전체 후보를 빠르게 훑습니다.
2. `candidate_scoring`: 가격 순위, 목적지별 커버리지, 범위 앵커, 저가 후보 인접일, 시간조건 필요성, confidence를 점수화합니다.
3. `detailed_refine`: 상위 후보를 upstream `FlightSearcher`로 상세 검증합니다.
4. `diagnostic_fallback`: 추출 불완전, 시간 조건 탈락, broad/detail 불일치가 강하면 후보를 추가 검증합니다.
5. `final_ranking`: 시간 조건이 있으면 상세 검증과 시간 조건을 통과한 결과만 추천에 반영합니다.

상세 결과는 upstream 필드를 최대한 보존합니다.

- `duration`, `return_duration`
- `stops`, `return_stops`
- `flight_number`
- `benefit_price`, `benefit_label`
- `source`, `extraction_source`, `confidence`

## Legacy 스크립트

기존 `scripts/search_flights.py`, `scripts/search_date_range.py`, `scripts/search_destination_date_matrix.py`, `scripts/search_multi_destination.py`, `scripts/chat_search.py`, `scripts/price_alerts.py`는 남아 있지만, 구현은 새 `korea_flights` 패키지 CLI로 넘기는 forwarder입니다. 새 문서와 자동화는 `korea-flights` 명령을 기준으로 작성하세요.

## 검증

권장 로컬 게이트:

```bash
python -m compileall src scripts tests
python -m pytest -q
python scripts/regression_smoke_check.py
python scripts/hybrid_smoke_check.py
python -m build
```

이 저장소에는 `.spec` 파일이 없으며, GUI/EXE 패키징 대신 wheel/sdist 빌드와 설치 후 CLI smoke를 기준으로 검증한다. wheel에는 `SKILL.md`와 `references/*.md`가 package data로 포함된다.

패키지 설치 smoke:

```bash
python -m venv .tmp-wheel-smoke
.tmp-wheel-smoke\Scripts\python -m pip install --no-deps dist\korea_flights-0.1.0-py3-none-any.whl
.tmp-wheel-smoke\Scripts\korea-flights --help
.tmp-wheel-smoke\Scripts\korea-flights doctor --repo-path D:\twbeatles-repos\Scraping-flight-information
```

## 주의

- 실제 검색은 외부 사이트와 Playwright/브라우저 환경에 영향을 받습니다.
- 참조 저장소의 Interpark API-first 동작이 깨지면 이 패키지의 adapter도 영향을 받습니다.
- 과도한 반복 검색은 차단이나 지연을 유발할 수 있습니다.
