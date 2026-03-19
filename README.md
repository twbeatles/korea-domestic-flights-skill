# korea-domestic-flights-skill

대한민국 **국내선 항공권 검색 전용** OpenClaw 스킬입니다.

Playwright 기반 로컬 항공권 검색 저장소([`Scraping-flight-information`](https://github.com/twbeatles/Scraping-flight-information))의 검색 로직을 얇게 감싸서, **김포-제주 / 부산-제주 / 청주-제주** 같은 국내선 노선의 편도/왕복 최저가를 빠르게 조회할 수 있게 만든 최소 기능 버전입니다.

> 핵심 원칙: 이 스킬은 **대한민국 국내선 전용**입니다. 국제선 검색용으로 설계하지 않았습니다.

---

## 지원 범위

현재 버전에서 지원하는 기능:

- 대한민국 **국내선 편도 검색**
- 대한민국 **국내선 왕복 검색**
- 최저가 및 상위 옵션 요약
- JSON 출력
- 사람이 읽기 좋은 요약 출력 (`--human`)

현재 버전에서 **아직 미지원**:

- 국제선 검색
- 날짜 범위 최저가 탐색
- 다중 목적지 비교
- 가격 알림
- 예약 자동화

---

## 전제 조건

이 스킬은 아래 로컬 저장소를 재사용합니다.

- 소스 저장소 clone 위치:
  - `tmp/Scraping-flight-information`

즉, 이 저장소는 **독립 실행형 완전체**가 아니라, 기존 항공권 검색 프로젝트의 핵심 로직을 재사용하는 **스킬 래퍼(wrapper)** 입니다.

### 필요 환경

- Python 3.10+
- Playwright 사용 가능 환경
- 기존 항공권 검색 저장소의 의존성 설치 완료
- Chromium/Chrome/Edge 중 하나 사용 가능

예시:

```bash
pip install -r requirements.txt
playwright install chromium
```

---

## 저장소 구조

```text
korea-domestic-flights-skill/
├── README.md
├── SKILL.md
└── scripts/
    └── search_domestic.py
```

- `SKILL.md`: OpenClaw가 스킬로 인식할 때 읽는 메타/사용 지침
- `scripts/search_domestic.py`: 국내선 항공권 검색 래퍼 스크립트
- `README.md`: GitHub 저장소용 문서

---

## 사용 방법

### 1) 편도 검색

```bash
python scripts/search_domestic.py --origin GMP --destination CJU --departure 2026-03-25
```

예시 의미:
- 출발지: 김포 (`GMP`)
- 도착지: 제주 (`CJU`)
- 출발일: 2026-03-25

### 2) 왕복 검색

```bash
python scripts/search_domestic.py --origin GMP --destination CJU --departure 2026-03-25 --return-date 2026-03-28
```

### 3) 사람이 읽기 좋은 요약 출력

```bash
python scripts/search_domestic.py --origin GMP --destination CJU --departure 2026-03-25 --human
```

또는 왕복:

```bash
python scripts/search_domestic.py --origin GMP --destination CJU --departure 2026-03-25 --return-date 2026-03-28 --human
```

---

## 옵션

| 옵션 | 설명 |
|---|---|
| `--origin` | 출발 공항 코드 (`GMP`, `CJU`, `PUS`, `TAE`, `CJJ` 등) |
| `--destination` | 도착 공항 코드 |
| `--departure` | 출발일 (`YYYY-MM-DD`) |
| `--return-date` | 귀국일 (`YYYY-MM-DD`, 왕복 시 사용) |
| `--adults` | 성인 수, 기본값 `1` |
| `--cabin` | `ECONOMY`, `BUSINESS`, `FIRST` |
| `--max-results` | 최대 결과 수, 기본값 `20` |
| `--human` | JSON 대신 사람이 읽기 좋은 요약 출력 |

---

## 출력 예시

### 편도 `--human`

```text
김포(GMP) → 제주(CJU) 편도 최저가 33,500원
조건: 성인 1명 · ECONOMY · 결과 3건
일정: 2026-03-25
최저가: 에어서울 · 33,500원 · 18:40→19:55
상위 옵션:
1. 에어서울 · 33,500원 · 18:40→19:55
2. 아시아나 · 33,600원 · 18:35→19:50
3. 아시아나 · 33,600원 · 20:20→21:35
```

### 왕복 `--human`

```text
김포(GMP) → 제주(CJU) 왕복 최저가 95,100원
조건: 성인 1명 · ECONOMY · 결과 3건
일정: 2026-03-25 ~ 2026-03-28
최저가: 에어서울/아시아나 · 총 95,100원 · 가는편 18:40→19:55 · 오는편 06:05→07:20
상위 옵션:
1. 에어서울/아시아나 · 총 95,100원 · 가는편 18:40→19:55 · 오는편 06:05→07:20
2. 에어서울/아시아나 · 총 95,100원 · 가는편 18:40→19:55 · 오는편 06:10→07:25
3. 에어서울/아시아나 · 총 95,100원 · 가는편 18:40→19:55 · 오는편 06:15→07:30
```

### JSON 출력 예시 구조

```json
{
  "status": "success",
  "query": {
    "origin": "GMP",
    "destination": "CJU",
    "departure": "2026-03-25",
    "return_date": "2026-03-28",
    "adults": 1,
    "cabin": "ECONOMY",
    "max_results": 3
  },
  "count": 3,
  "summary": {
    "headline": "김포(GMP) → 제주(CJU) 왕복 최저가 95,100원"
  },
  "cheapest": {
    "airline": "에어서울",
    "price": 95100
  },
  "results": []
}
```

---

## 대한민국 국내선 전용 범위

이 스킬은 아래 같은 질의에 맞춰 설계했습니다.

- `김포에서 제주 가는 내일 최저가 찾아줘`
- `부산 제주 왕복 항공권 최저가 보여줘`
- `청주 제주 편도 가격 비교해줘`
- `국내선 중에서 김포-제주 상위 5개만 정리해줘`

반대로 아래는 현재 범위 밖입니다.

- `인천-도쿄 국제선 검색`
- `해외 다구간 여정 검색`
- `항공권 자동 예약`
- `호텔/렌터카 결합 검색`

---

## 한계와 주의점

- 검색 대상 사이트의 DOM 구조가 바뀌면 유지보수가 필요할 수 있습니다.
- Playwright 브라우저 초기화가 실패하면 브라우저 설치 상태를 점검해야 합니다.
- 대상 사이트의 정책, 차단, 로딩 상태에 따라 결과가 달라질 수 있습니다.
- 이 저장소는 **국내선 검색에만 초점을 맞춘 최소 기능 버전**입니다.

---

## 개발 메모

현재 래퍼는 다음 엔트리 포인트를 재사용합니다.

- `scraping.searcher.FlightSearcher`

즉, GUI 중심 원본 프로젝트 전체를 옮긴 것이 아니라, **검색 로직만 OpenClaw 스킬 형태로 노출**한 구조입니다.

---

## 다음 계획

향후 추가 후보:

- 날짜 범위 최저가 검색
- 다중 목적지 비교
- 더 자연스러운 한국어 요약
- 아침 브리핑/리마인더와 연결
- ClawHub 배포 정식화

---

## 라이선스 / 출처

이 저장소는 태완의 기존 프로젝트 `Scraping-flight-information`을 기반으로 스킬화한 파생 작업입니다.
