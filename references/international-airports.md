# 주요 국제 공항 / 도시 코드 예시

이 목록은 자주 쓰는 국제선 예시만 담고 있다. 별칭 테이블에 없는 경우에도 raw 3자리 uppercase 공항/도시 코드는 그대로 입력할 수 있다.

- `ICN` — 인천
- `NRT` — 도쿄 나리타
- `HND` — 도쿄 하네다
- `TYO` — 도쿄(도시 코드)
- `KIX` — 오사카 간사이
- `OSA` — 오사카(도시 코드)
- `FUK` — 후쿠오카
- `BKK` — 방콕
- `SIN` — 싱가포르
- `HKG` — 홍콩
- `SGN` — 호치민
- `DAD` — 다낭
- `DPS` — 발리

## 한글/영문 별칭 예시

- `나리타`, `narita` → `NRT`
- `하네다`, `haneda` → `HND`
- `도쿄`, `tokyo` → `TYO`
- `간사이` → `KIX`
- `오사카`, `osaka` → `OSA`
- `후쿠오카`, `fukuoka` → `FUK`
- `방콕`, `bangkok` → `BKK`
- `싱가포르`, `singapore` → `SIN`
- `홍콩`, `hong kong` → `HKG`
- `호치민`, `ho chi minh` → `SGN`
- `다낭`, `danang` → `DAD`
- `발리`, `bali` → `DPS`

## CLI 예시

- `korea-flights search --origin ICN --destination NRT --departure 내일 --scope international --human`
- `korea-flights search --origin SEL --destination TYO --departure 내일 --human`
- `korea-flights search --origin ICN --destination KIX --departure 내일 --human`
- `korea-flights range --origin ICN --destination KIX --date-range "다음주말" --scope international --human`
- `korea-flights matrix --origin ICN --destinations NRT,KIX,FUK --date-range "내일부터 3일" --scope international --human`

기존 `scripts/search_flights.py`, `scripts/search_date_range.py`, `scripts/search_destination_date_matrix.py`는 호환용 forwarder로만 유지된다. 새 자동화와 문서는 `korea-flights` 패키지 CLI를 기준으로 작성한다.
