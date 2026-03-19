# korea-domestic-flights-skill

대한민국 **국내선 항공권 검색 및 가격 감시 전용** OpenClaw 스킬입니다.

Playwright 기반 로컬 항공권 검색 저장소([`Scraping-flight-information`](https://github.com/twbeatles/Scraping-flight-information))의 검색 로직을 얇게 감싸서, **편도/왕복 검색**, **날짜 범위 최저가 탐색**, **다중 목적지 비교**, **목적지+날짜 범위 최적 조합 검색**, 그리고 **목표가 기반 가격 감시/알림**까지 지원합니다.

> 핵심 원칙: 이 스킬은 **대한민국 국내선 전용**입니다. 국제선 검색용으로 설계하지 않았습니다.

---

## 지원 범위

현재 버전에서 지원하는 기능:

- 국내선 편도 검색
- 국내선 왕복 검색
- 날짜 범위 최저가 탐색
- 다중 목적지 비교
- 목적지 + 날짜 범위 최적 조합 검색
- 더 자연스러운 한국어 브리핑
- 한글 공항명 입력
- 자연어 날짜 입력 (`오늘`, `내일`, `모레`, `글피`, `이번주말`, `다음주말`, `내일부터 3일` 등)
- 채팅 친화 래퍼 (`chat_search.py`)
- 목표가 기반 가격 감시 규칙 저장/목록/삭제/점검
- **중복 알림 방지(dedupe)**
- **다중 목적지 감시**
- **알림 메시지 포맷 커스터마이즈**
- cron/브리핑 연동을 위한 JSON 저장 포맷
- Windows 작업 스케줄러 등록 초안

---

## 저장소 구조

```text
korea-domestic-flights-skill/
├── README.md
├── SKILL.md
├── references/
│   ├── domestic-airports.md
│   └── price-alerts-schema.md
└── scripts/
    ├── chat_search.py
    ├── common_cli.py
    ├── price_alerts.py
    ├── register_price_alerts_task.ps1
    ├── search_date_range.py
    ├── search_destination_date_matrix.py
    ├── search_domestic.py
    └── search_multi_destination.py
```

---

## 가장 추천하는 사용 방식

### 1) 채팅 친화 검색

```bash
python scripts/chat_search.py --origin 김포 --destination 제주 --when 내일
```

### 2) 다중 목적지 비교

```bash
python scripts/chat_search.py --origin 김포 --destinations 제주,부산,여수 --when 다음주말
```

### 3) 날짜 범위 + 왕복 오프셋 비교

```bash
python scripts/chat_search.py --origin 김포 --destinations 제주,부산 --when "내일부터 2일" --return-offset 1
```

---

## 가격 감시 기능

### 단일 목적지 감시 등록

```bash
python scripts/price_alerts.py add --origin 김포 --destination 제주 --departure 내일 --target-price 70000 --label "김포-제주 내일 특가"
```

### 날짜 범위 감시 등록

```bash
python scripts/price_alerts.py add --origin 김포 --destination 제주 --date-range "내일부터 3일" --target-price 80000 --label "김포-제주 3일 범위 감시"
```

### 다중 목적지 감시 등록

```bash
python scripts/price_alerts.py add --origin 김포 --destinations 제주,부산,여수 --departure 내일 --target-price 90000 --label "김포 출발 내일 다중 목적지 감시"
```

### 커스텀 메시지 템플릿 등록

```bash
python scripts/price_alerts.py add --origin 김포 --destinations 제주,부산 --date-range "내일부터 3일" --target-price 85000 --message-template "[특가감시] {best_destination_label} {departure_date} {observed_price} / 기준 {target_price}"
```

### 저장된 규칙 확인

```bash
python scripts/price_alerts.py list
```

### 규칙 점검

```bash
python scripts/price_alerts.py check
```

### 마지막 결과를 현재 템플릿으로 미리보기

```bash
python scripts/price_alerts.py render --rule-id <RULE_ID>
```

### 규칙 삭제

```bash
python scripts/price_alerts.py remove --rule-id <RULE_ID>
```

---

## 중복 알림 방지

현재 버전에서는 두 단계의 dedupe가 들어가 있어.

### 1) 규칙 저장 dedupe
동일한 조건 + 동일 목표가 규칙은 fingerprint 기준으로 **중복 저장되지 않음**

### 2) 알림 발송 dedupe
같은 규칙에서
- 같은 최저가
- 같은 항공사
- 같은 시간/날짜/목적지 조합
이면 **재알림을 억제**함

강제로 다시 보고 싶으면:

```bash
python scripts/price_alerts.py check --no-dedupe
```

---

## 알림 템플릿 변수

커스텀 메시지에서 자주 쓸 수 있는 변수 예시:

- `{label}`
- `{route}`
- `{origin_label}`
- `{destinations_label}`
- `{best_destination_label}`
- `{target_price}`
- `{observed_price}`
- `{difference_krw}`
- `{departure_date}`
- `{return_date}`
- `{date_text}`
- `{airline}`
- `{departure_time}`
- `{arrival_time}`
- `{cabin_label}`
- `{status_line}`

---

## 실제 사용 예시

### 실제 질의 스타일 예시

```bash
python scripts/chat_search.py --origin 김포 --destinations 제주,부산,여수 --when 다음주말
```

예시 출력:

```text
김포(GMP) 출발 최적 조합은 제주(CJU) 2026-03-29 48,000원
범위: 2026-03-28 ~ 2026-03-29
조건: 출발 김포(GMP) · 목적지 3곳 · 성인 1명 · 이코노미
최적 조합: 제주(CJU) · 2026-03-29 · 48,000원 · 제주항공
추천: 이번 조건에서는 제주(CJU) / 2026-03-29이(가) 가장 유리합니다. 2위보다 1,000원 저렴해 가성비가 좋습니다.
목적지별 베스트:
1. 제주(CJU) · 2026-03-29 · 48,000원 · 제주항공
2. 부산(PUS) · 2026-03-28 · 49,000원 · 제주항공
3. 여수(RSU) · 결과 없음
```

---

## cron / 자동화 연결

가격 감시 규칙은 기본적으로 JSON 파일에 저장되고,
정기 점검은 아래처럼 단순 호출 가능:

```bash
python scripts/price_alerts.py check
```

즉 상위 OpenClaw cron/브리핑 시스템에서는
stdout을 그대로 전달하는 방식으로 연결하기 좋음.

Windows 환경에서는 작업 스케줄러 등록 초안:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/register_price_alerts_task.ps1 -IntervalMinutes 30
```

---

## 대한민국 국내선 전용 범위

이 스킬은 아래 같은 요청에 맞춰 설계했습니다.

- `김포에서 제주 가는 내일 최저가 찾아줘`
- `부산 제주 왕복 항공권 요약해줘`
- `김포 출발로 제주, 부산, 여수 중 어디가 제일 싼지 비교해줘`
- `김포 출발 제주/부산/여수 다음주말 비교해줘`
- `김포 제주가 7만원 이하로 떨어지면 알려줘`
- `김포 출발 제주/부산 중 9만원 이하 특가 감시해줘`

반대로 아래는 현재 범위 밖입니다.

- `인천-도쿄 국제선 검색`
- `해외 다구간 여정 검색`
- `항공권 자동 예약`
- `호텔/렌터카 결합 검색`

---

## 라이선스 / 출처

이 저장소는 `twbeatles/Scraping-flight-information`를 기반으로 OpenClaw 스킬 형태로 재구성한 파생 작업입니다.
