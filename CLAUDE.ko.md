# CLAUDE.md

[English](./CLAUDE.md) · 이 문서는 영문 `CLAUDE.md`의 한국어판입니다. 영문이 기준이며, 내용이 다르면 영문을 따릅니다.

Spotter Full Stack Developer 과제(`fs-assessment-spotter.pdf`) — **Weather-Aware Truck Routing** 구현 스펙.

트럭 운전자가 **날씨, 적재 중량, 이동 시간**을 고려해 가장 안전한 경로를 고르도록 돕는 **React + Django** 웹 앱.

> 원칙: **정확성과 명확성을 추가 기능보다 우선한다.** (PDF 원문: *Prioritize correctness and clarity over extra features.*)
> 아래에서 `[PDF]`는 PDF에 명시된 내용, `[해석]`은 PDF가 침묵해서 정한 가정, `[결정]`은 사용자가 정한 제작 방향이다. 해석이나 결정을 바꿀 때는 이 문서와 README.md를 같이 고친다.

---

## 0. 문서 규칙

- **영어가 기본이다.** 모든 문서는 영문(`CLAUDE.md`, `README.md`, `docs/api-contract.md`)이 있고, 영문 파일 맨 위에서 한국어판(`*.ko.md`)으로 링크한다.
- 영문이 기준이다. 문서를 고칠 때는 같은 변경에서 한국어판도 함께 고친다.
- UI 문구는 영어다. 커밋 메시지도 영어다. 코드 주석도 영어다.

## 1. 사용자 입력 항목 `[PDF]`

| 입력 | 비고 |
|---|---|
| 출발지(Origin) & 도착지(Destination) | 주소 문자열 → geocoding API로 좌표 변환 |
| 출발 일시(Departure date/time) | 각 checkpoint의 ETA 계산 기준 |
| 적재 중량(Load weight) | lb 단위 (Load rules가 lb 기준) |

## 2. 앱이 해야 할 일 `[PDF]`

1. routing API로 **경로 3개**를 생성한다.
2. 각 경로를 **10 / 25 / 50 마일 간격**으로 샘플링하여 checkpoint를 만들고, 각 checkpoint에서 **트럭의 예상 도착 시각(ETA)** 기준으로 날씨를 조회한다. (현재 시각 날씨가 아님)
3. 제공된 위험 규칙/적재 규칙으로 날씨 위험도를 계산한다.
4. **날씨 위험도와 이동 시간**을 균형 있게 고려해 최적 경로를 추천한다.
5. 지도에 **모든 경로, checkpoint, 위험 수준, ETA, 경로 요약**을 표시한다.
6. 이동 경로 주변(trip corridor)에 **날씨 heatmap**을 표시하고 **0–48시간 forecast 슬라이더**를 제공한다.

- routing / geocoding / weather는 **third-party API 사용 가능**. routing 엔진을 직접 만들 필요 없다.
- `[결정]` heatmap 슬라이더의 0시간은 **출발 일시**다(슬라이더 값 h = 출발 후 h시간의 예보). PDF는 기준 시각을 명시하지 않는다(현재 시각 기준으로도 읽을 수 있음). 어느 시점의 예보인지 혼동이 없도록 슬라이더 옆에 절대 날짜·시각을 함께 표시한다.
- `[해석]` "10 / 25 / 50 마일"은 샘플링 간격 옵션으로 보고, 사용자가 UI에서 선택하게 한다(기본값 25). 간격이 작을수록 정밀하지만 날씨 API 호출이 늘어나므로 호출은 배치/캐시한다.

## 3. 위험 규칙 `[PDF]`

각 checkpoint에서 풍속·강우·강설을 아래 임계값으로 분류한다.

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind | < 25 mph | 25–34 | 35–44 | 45–54 | ≥ 55 mph |
| Rain | < 0.10 in/hr | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow | < 0.5 in/hr | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

- `[해석]` 경계값 처리 — 날씨 값은 연속값이므로 표를 빈틈·겹침 없는 구간으로 읽는다.
  - Wind: 표가 정수 구간이라 34.5 mph 같은 값이 비어 있다. `25 미만 / 25 이상 35 미만 / 35 이상 45 미만 / 45 이상 55 미만 / 55 이상`으로 읽는다. 적재 규칙의 풍속 구간도 동일하다.
  - Rain·Snow: 구간 끝이 겹치는 값(Rain 0.25·0.50, Snow 1.0·2.0)은 **더 높은 등급**으로 분류한다. 표의 "< 0.10 → Low"(0.10은 Moderate)와 같은 방식이다. 단 No Travel은 표기 그대로 초과(`>`)일 때만 적용한다: Rain 1.00과 Snow 3.0은 Severe.
- `[해석]` Wind는 지속 풍속(sustained wind speed)을 쓴다. PDF는 "Wind"라고만 하고 돌풍(gust)을 언급하지 않는다.
- 날씨 API 값은 표의 단위(mph, in/hr)로 변환한 뒤 분류한다.
- `[해석]` checkpoint의 최종 위험 등급 = **Wind / Rain / Snow 세 등급 중 가장 높은 것** (이후 적재 규칙으로 상향).
- 위험 등급 순서: `Low < Moderate < High < Severe < No Travel`

## 4. 적재 규칙 `[PDF]`

적재 규칙은 풍속 기준 등급을 **상향**시킨다.

| 조건 | 결과 |
|---|---|
| 풍속 ≥ 55 mph | **No Travel** (적재량 무관) |
| 풍속 45–54 mph + 적재 > 30,000 lb | **No Travel** |
| 풍속 35–44 mph + 적재 > 40,000 lb | **Severe** |

- 적재 규칙은 등급을 올리기만 하고 내리지 않는다. (예: 45–54 mph, 적재 ≤ 30,000 lb → 기본 Severe 유지)
- 적재 중량 비교는 엄격한 `>` 이다. (30,000 lb 정확히는 해당 안 됨)

## 5. 경로 추천 기준 `[PDF]`

아래 우선순위를 **사전식(lexicographic) 비교**로 적용한다. 앞 기준이 동점일 때만 다음 기준을 본다. 네 기준을 가중치 점수로 섞지 않는다.

1. **Severe 구간 마일 수가 가장 적은 경로**
2. **High 구간 마일 수가 가장 적은 경로**
3. **평균 위험도가 가장 낮은 경로**
4. **이동 시간이 가장 짧은 경로**

- `[해석]` 구간 마일 수: checkpoint는 출발지(0마일), 샘플링 간격마다, 도착지에 둔다. 각 checkpoint는 앞뒤 checkpoint와의 중간 지점까지를 대표하고(등급별 마일 합계 = 경로 전체 거리), 그 길이를 해당 checkpoint의 등급에 합산한다.
- `[해석]` 동점 판정: 화면에 표시하는 값으로 반올림해 비교한다(마일은 1마일, 평균 위험도는 소수 둘째 자리, 이동 시간은 분). 반올림 없이 실수로 비교하면 3번 기준에서 거의 항상 승부가 나서 4번(이동 시간)이 쓰이지 않고, PDF의 "balancing weather risk and travel time"과 어긋난다.
- `[해석]` 평균 위험도 = 등급을 수치(Low 0, Moderate 1, High 2, Severe 3, No Travel 4)로 바꿔 구간 길이로 가중평균한 값.
- `[해석]` **No Travel** checkpoint가 하나라도 있는 경로는 추천에서 제외하고 "통행 불가"로 표시한다. 3개 경로 모두 No Travel이면 추천 없이 사유를 보여준다. (PDF는 No Travel 경로 처리 방식을 명시하지 않음)
- 추천 결과에는 **왜 이 경로인지**(어느 기준에서 다른 경로를 이겼는지)를 한 줄로 설명한다. 예(UI는 영어): "0 severe miles, 20 min slower than Route B"

## 6. 평가 기준 `[PDF]`

| 비중 | 항목 |
|---|---|
| **40%** | Routes, Weather, risk & recommendation logic (경로·날씨·위험·추천 로직) |
| **40%** | UI, map & heatmap smoothness and performance (UI·지도·heatmap의 부드러움과 성능) |
| **15%** | Code quality (코드 품질) |
| **5%** | Documentation & walkthrough (문서·시연) |

**산출물(Deliverables):** GitHub repository / 배포된 호스팅 앱 / 5–10분 Loom walkthrough.

→ 작업 우선순위: 위험·추천 로직의 정확성 > 지도/heatmap 성능 > 코드 품질 > 문서.

## 7. 기술 스택

**PDF 명시:** React(프론트엔드) + Django(백엔드). routing/geocoding/weather는 third-party API 허용.

**`[해석]` 구체 선택 (PDF에 없음, 변경 가능):**

- Frontend: React + **TypeScript**(Vite) + WebGL 기반 지도(MapLibre) — heatmap을 WebGL 레이어로 그린다 `[결정]`. API 타입은 `frontend/src/types/api.ts`, 계약 문서는 `docs/api-contract.md`
- Backend: Django + Django REST Framework — API 키는 서버에서만 보관하고 프론트는 Django를 통해 호출
- 외부 API `[결정]` (1단계 조사 결과, 무료 티어):
  - routing: **TomTom Routing API — Calculate Route.** `travelMode=truck`, `vehicleWeight`(kg), `maxAlternatives`(0–5, "최대 N개"이며 보장되지 않음). 무료 월 20K건, 카드 불필요.
  - geocoding: **TomTom Geocoding API.** 무료 월 20K건. (입력 중 자동완성 Places Search Suggest는 쓰지 않는다.)
  - weather: **Open-Meteo Forecast API.** 키 불필요, 시간별 데이터, 단위 `wind_speed_unit=mph` / `precipitation_unit=inch`. 기본(best match) 모델만 쓰고 모델을 직접 지정하지 않는다(HRRR는 2026-11-30 종료).
  - 날씨 변수 `[해석]`: 풍속 = `wind_speed_10m`(순간 풍속, 돌풍 `wind_gusts_10m` 미사용), 강우 = `rain + showers`(직전 1시간 합계 inch = in/hr), 강설 = `snowfall`(적설 높이 inch, 액체 환산 아님).
  - Open-Meteo는 비상업 무료 조건(광고·구독 없는 비영리)이다. 화면에 CC BY 4.0 출처를 표기한다. 한도는 일 10,000건 / 시간 5,000건 / 분 600건이다.
  - Open-Meteo 호출 규격 `[결정]` (2026-11-06 실제 호출로 측정):
    - **비용 = 지점 수.** 응답 헤더 `X-RateLimit-Cost`가 지점 1개 = 1, 100개 = 100이다. 기간(48시간/7일)과 변수 개수(4개/6개)는 비용에 영향이 없다. 남은 횟수(`X-RateLimit-Remaining`)는 호출마다 어긋나므로 정확한 잔여량으로 믿지 않는다.
    - **요청당 지점 수:** 400개(URL 6.3K자)는 성공, 700개는 HTTP 414(URL 너무 김). 한 요청은 **200개 이하**(URL 약 3.2K자)로 나눈다. 분당 600건을 넘지 않게 간격을 두고, 429가 오면 재시도한다.
    - **시간 창:** `forecast_hours=48`은 "지금부터"라서 쓰지 않는다. 출발 시각 기준은 `start_hour` / `end_hour`(예: `start_hour=2026-11-09T12:00&end_hour=2026-11-11T12:00`)를 쓴다. `timezone=UTC`로 통일한다.
    - **예보 범위:** `start_date`는 오늘 기준 약 +15일(2026-11-06 기준 2026-11-21)까지이고 넘으면 HTTP 400이다. 측정(16일치 전체, 2개 지점): `null`은 **예보가 끝나는 마지막 날(+15일)의 마지막 5시간에만** 있었고 그 전 15일은 0개였다. 즉 `null`은 품질 저하가 아니라 예보 끝을 넘은 시간이다.
    - `null`·범위 초과 값은 0으로 취급하지 않고 오류로 처리한다. 오류 메시지에 "예보는 <마지막 가능 시각>까지 제공됩니다"를 보여준다.
    - **출발 일시 검증:** PDF에 출발 일시 범위 제한이 없으므로 **임의의 상한(예: +7일)을 두지 않는다.** 거부 조건은 둘뿐이다. (1) 출발 시각이 과거(TomTom은 과거 `departAt`을 오류 없이 받으므로 앱이 직접 막는다). (2) 필요한 시간(마지막 checkpoint ETA, 출발 +48시간)이 예보 끝을 넘음 → 응답의 `null`/범위 초과로 판정한다.
    - **heatmap 격자 `[결정]`:** 간격 0.5°(약 34마일), 경로 3개 합집합 기준 양쪽 40마일 버퍼. 시카고→덴버(경로 1,004 / 1,163 / 1,336마일)에서 **278개 지점**. 0.25° 격자는 570~1,116개라 한도에 맞지 않아 쓰지 않는다. 변수는 `wind_speed_10m`, `rain`, `showers`, `snowfall`, 시간 창은 출발 시각부터 +48시간(0~48시간, 49개 값).
    - **checkpoint 날씨:** heatmap과 별도로 checkpoint 좌표(소수 둘째 자리 반올림)에서 직접 조회한다. 체크포인트 수(경로 3개, 중복 제거): 10마일 351개 / 25마일 141개 / 50마일 71개.
    - **1회 분석 비용(시카고→덴버):** 25마일 간격 141 + 278 = **419건**(하루 약 23회), 10마일 간격 351 + 278 = **629건**(하루 약 15회). 캐시 키는 (반올림 좌표, 시간 창 시작)이며 TTL 약 1시간이다. 적재 중량은 날씨에 영향이 없으므로 중량만 바꿔 다시 분석할 때는 날씨를 다시 부르지 않는다.
  - TomTom 호출 규격 `[결정]` (2026-11-06 실제 호출로 확인):
    - 경로: `GET /routing/1/calculateRoute/{lat,lon}:{lat,lon}/json` + `travelMode=truck`, `vehicleCommercial=true`, `vehicleWeight=<kg>`, `maxAlternatives=2`, `departAt=<출발 일시>`, `instructionsType=coded`
    - 주소 변환: `GET /search/2/geocode/{주소}.json` + `countrySet=US`, `limit=1`
    - 적재 중량은 앱 입력이 lb이므로 TomTom에는 kg으로 변환해서(×0.45359237) 전달한다. 위험·적재 규칙 판정은 입력 lb 값으로 한다.
    - 응답의 경로선은 `routes[].legs[].points[]`(위도·경도만, 시간 없음)이다. 시카고→덴버 한 경로가 약 1만 점이다.
    - `[해석]` ETA: `guidance.instructions[]`의 (`pointIndex`, `routeOffsetInMeters`, `travelTimeInSeconds`)를 기준점으로 쓰고, 기준점 사이는 경로선 거리 비율로 시간을 보간한다. 이 방식의 오차는 4단계에서 검증한다.
    - 위험: 응답 크기 약 1.8MB, 응답 시간 6–10초(3개 경로, 장거리). 요청 단위 캐싱과 로딩 상태 표시가 필요하다.
  - TomTom 키: 대시보드에서 **키 하나로 Routing API와 Geocoding API가 함께 제공됨을 확인**했다(2026-11-06, Billing Type은 "Evaluation"). Evaluation이 기간 제한이 있는지는 확인하지 못했으므로 대시보드에서 만료 조건을 확인한다. 키는 서버(`.env`)에서만 쓰고 프론트에 노출하지 않는다.
  - 지도 배경 `[결정]`: **TomTom Vector Tiles + MapLibre.** 대시보드 한도(2026-11-06): Map Display Vector Tiles 200,000건, Raster Tiles 200,000건, Raster Non-tile 20,000건. 라우팅·지오코딩(각 20,000건)과 별도 한도이며, 기간 표시는 화면에 없다. 래스터는 쓰지 않는다.
    - 실제 호출로 확인(2026-11-06): 클래식 벡터 타일 `GET /map/1/tile/basic/main/{z}/{x}/{y}.pbf`, Orbis 벡터 타일 `GET /maps/orbis/display/vector/tile/{z}/{x}/{y}?apiVersion=2` 모두 200. MapLibre용 스타일 JSON도 받아진다. 타일 응답은 `cache-control: max-age=86400`이라 브라우저 캐시로 요청이 줄어든다.
    - 스타일 후보: 클래식 `GET /style/1/style/*?map=basic_main` (레이어 775개, 333KB) / Orbis `GET /maps/orbis/assets/styles/*/style.json?apiVersion=1&map=basic_street-light` (레이어 121개, 139KB, 밝은 배경). **`[결정]` 클래식 `basic_main`을 쓴다.** 대시보드 사용량 확인(2026-11-06): 클래식 벡터 타일 2건 호출 → Vector Tiles 2/200,000, 래스터 1건 호출 → Raster Tiles 1/200,000으로 정확히 일치했고, 스타일 JSON 요청은 계산되지 않았다. Orbis 타일 1건은 Vector Tiles에 합산되지 않아 어느 한도에 잡히는지 불명확하다. 한도가 확실한 쪽을 택한다. 지도 렌더링 성능은 2단계에서 측정했고 레이어 숨김은 필요 없었다.
    - **키 노출 `[결정]`:** 스타일 JSON과 타일 URL에 키가 들어 있어 브라우저에 노출된다. 라우팅·지오코딩 키는 서버(`.env`)에만 두고, **지도용 키를 별도로 발급해 프론트에서만 쓴다.** 개발용(`spotter-map-dev`)은 TomTom이 `localhost`를 화이트리스트에 받지 않아 제한 없이 로컬에서만 쓰고, 배포용(`spotter-map-prod`)은 배포 도메인만 화이트리스트에 등록한다. 화이트리스트가 타일 요청에 실제로 적용되는지는 확인하지 못했으므로 12단계에서 검증한다. 서버 키(`spotter-server`)에는 화이트리스트를 걸지 않는다(서버 호출은 브라우저 출처가 없어 막힐 수 있음).

## 8. 구현 원칙

- 위험/추천 로직은 백엔드(Django)에 둔다. 프론트는 결과 표시와 상호작용만 담당한다.
- 날씨는 checkpoint의 **ETA 시각**으로 조회한다. 시간대(timezone) 처리를 명시적으로 한다. ETA가 날씨 API의 예보 범위를 벗어나면 임의 값으로 채우지 않고 오류로 알린다.
- 외부 API 호출은 병렬/배치 처리 및 캐싱으로 응답 시간을 줄인다. 실패 시 사용자에게 명확한 오류를 보여준다.
- 요청받지 않은 기능은 추가하지 않는다.
- API 키 등 비밀값은 환경변수(`.env`)로 관리하고 커밋하지 않는다.

## 9. UI 레퍼런스 `[결정]`

**메인 (이것만 따라가도 충분)**

1. **WeatherRoute** — 전체 구조의 기준
   - 경로 3개를 날씨 안전도로 순위 매기는 컨셉이 과제와 거의 같다.
   - 슬라이더 ↔ 경로 카드 ↔ 지도 점이 함께 바뀌는 방식을 참고한다.
2. **Weather on the Way** — "도착 시간 기준 날씨" 표현 방식
   - 각 checkpoint에 ETA와 그 시각의 날씨를 같이 보여준다.
   - 과제의 핵심 로직(ETA 기준 샘플링)을 사용자에게 가장 명확하게 보여주는 방식이다.
3. **Google Maps** — 경로 3개 비교 UI
   - 선택 경로는 진하게, 나머지는 회색. 사용자가 이미 익숙해서 설명이 필요 없다.

**보조 (일부만 참고)**

4. **Windy** — heatmap 색상과 범례만 참고한다. 바람 애니메이션 같은 화려한 효과는 따라하지 않는다(성능 부담, 과제 범위 밖).
5. **Is it clear: Route Weather** — checkpoint 리스트(타임라인) 형태만 참고한다.

**제외**

6. **Drive Weather의 라이브 레이더** — 과제는 실시간이 아닌 예보 기준이라 불필요하다.
7. **Sofar Wayfinder** — 구조는 좋지만 너무 복잡하다. 슬라이더 + heatmap + 트럭 위치 동기화 정도로 단순화한다.

## 10. 제작 방향 `[결정]`

한 줄 요약: **WeatherRoute의 구조 + Weather on the Way의 ETA 표현 + Google Maps의 경로 비교**를 합치고, 화려한 효과보다 **로직 테스트와 추천 이유 설명**에 시간을 쓴다.

**로직 (40%) — 정확성**

- 위험 규칙과 적재 규칙을 **순수 함수로 분리**하고(입력: 날씨값·적재량 → 출력: 등급) 단위 테스트를 작성한다: 경계값(25, 35, 45, 55 mph 등), 적재 규칙 3종, 우선순위 비교.
- 추천은 과제의 4단계 우선순위를 그대로 순서대로 비교한다. 가중치 점수로 섞지 않는다. (→ 5절)
- checkpoint 간격 10/25/50마일을 사용자가 고를 수 있게 한다. (→ 2절)
- Severe/High 마일을 checkpoint 사이 구간 거리로 계산하는 방식(→ 5절 정의)을 README에 명시한다.

**UI (40%) — 명확성**

- 경로선을 위험도 색상 구간으로 표시하고, 범례는 항상 보이게 둔다.
- 경로 카드에는 숫자 4개만 둔다: 심각 마일 / 높음 마일 / 평균 위험 / 소요 시간. (UI 표기: `Severe mi` / `High mi` / `Avg risk` / `Duration`)
- 추천 경로에 이유를 한 줄로 표시한다. (→ 5절)
- No Travel(운행 금지) 구간이 있으면 경고 배너로 크게 표시한다.
- **UI 문구는 모두 영어** `[결정]`: 라벨, 버튼, 범례, 추천 이유, 오류 메시지 포함. 위험 등급 표기는 PDF 용어 그대로 `Low` / `Moderate` / `High` / `Severe` / `No Travel`. 저장소 문서는 영어가 기본이고 한국어판(`*.ko.md`)을 함께 둔다. **커밋 메시지는 영어**로 쓴다.

**성능 — 부드러움**

- 날씨 데이터는 백엔드에서 48시간치를 한 번에 받아 캐싱한다.
- 슬라이더를 움직일 때 API를 다시 호출하지 않고 프론트에서 레이어만 교체한다.
- heatmap은 WebGL 기반 지도(Mapbox GL / MapLibre)로 그린다.

**문서/영상 (5%)**

- README에 규칙 해석 방식과 가정을 정리한다.
- Loom은 "입력 → 3개 경로 → 추천 이유 → 슬라이더" 순서로 짧게 찍는다.

## 11. 단계별 진행 체크리스트

로직을 테스트로 먼저 고정한 뒤 화면을 붙이는 순서다. 항목을 끝내면 `[x]`로 바꾼다. 앞 단계가 끝나기 전에 다음 단계로 넘어가지 않는다.

### 1단계. 외부 API 확정과 검증

- [x] routing API 선정: TomTom Routing (선정 완료, 7절 기록)
- [x] TomTom 호출로 **경로 3개** 확인 (2026-11-06, 시카고→덴버, truck, `maxAlternatives=2`): 1,006mi/14.1h, 1,164mi/16.6h, 1,338mi/19.5h
- [x] 짧은/중간 경로에서도 3개 확인 (2026-11-06): 시카고→오헤어 17.8/27.6/38.5mi, →밀워키 89.5/94.6/194mi, →인디애나폴리스 191.9/222.6/218.7mi. 세 번째 경로가 최단의 2배 이상 돌아가는 경우가 있다(밀워키)
- [x] `vehicleWeight` 영향 확인: 5,000kg / 20,000kg / 36,000kg에서 시카고→덴버 1,004.4 / 1,006.3 / 1,006.3mi로 거의 같다. TomTom의 중량은 도로 제한용이며 경로를 크게 바꾸지 않는다. 날씨·적재 위험은 우리 규칙(4절)이 판정한다
- [x] checkpoint별 누적 거리·시간: `instructionsType=coded`의 `guidance.instructions[]`가 `routeOffsetInMeters`, `travelTimeInSeconds`, `pointIndex`를 준다. 마지막 지시의 값이 `summary` 총합(1,619,492m / 50,822s)과 정확히 일치함을 확인
- [x] `departAt` 지원 확인: 미래 시각을 주면 `departureTime`/`arrivalTime`이 그에 맞게 바뀐다. **과거 시각도 오류 없이 200으로 받아들이므로** 입력 검증은 앱이 직접 해야 한다
- [x] 경로가 3개 미만으로 돌아올 때의 처리 방침 `[해석]`: TomTom은 "최대 N개"만 보장하므로(시험한 4개 구간은 모두 3개) 받은 경로만 그대로 쓰고 "대안 경로가 N개만 있습니다"를 화면에 알린다. 경로를 인위로 만들어 채우지 않는다. 1개만 와도 위험 분석과 표시는 동일하게 동작해야 한다 (참고: OSRM·Valhalla 공개 서버는 시카고→덴버에서 2개만 반환함)
- [x] weather API 선정: Open-Meteo (키 없이 2개 지점 · 48시간 · mph/inch 호출 확인 완료)
- [x] geocoding API 선정: TomTom Geocoding (선정 완료)
- [x] TomTom API 키 발급: 키 하나로 Routing + Geocoding 제공 확인
- [x] TomTom 키의 "Evaluation" 한도 확인: API Usage 화면에서 Routing 20,000건, Geocoding 20,000건(2026-11-06 기준 사용 3건·2건). 데모 규모에 충분하다. 만료일은 화면에서 확인하지 못했다(배포·Loom 전에 키가 살아 있는지 다시 확인)
- [x] TomTom Geocoding 호출 확인: "Chicago, IL", "Denver, CO"가 `countrySet=US`로 각각 1건, 좌표 정상 반환
- [x] Open-Meteo 다중 지점 비용 측정: 지점 1개 = 1건 (`X-RateLimit-Cost`), 요청당 200개 이하로 분할
- [x] heatmap 격자 밀도 결정: 0.5° 격자 + 40마일 버퍼 = 278개 지점. 1회 분석 419~629건으로 일 10,000건 안에 들어옴 (상세 7절)
- [x] 선정한 API를 7절(기술 스택)에 기록
- [x] README.md 기술 스택에 선정한 API 기록

### 2단계. 프로젝트 뼈대와 API 계약

- [x] Django + DRF 백엔드 생성 (`backend/`, Python 3.12 + uv, Django 6.1, DRF 3.18, pytest). `manage.py check` 통과, 개발 서버 응답 확인
- [x] React 프론트엔드 생성 (`frontend/`, Vite 8 + React 19 + **TypeScript** `[결정]` + maplibre-gl 6). lint·build 통과, Vite 프록시(`/api` → Django) 확인. 지도 렌더링은 지도용 키 발급 후 확인
- [x] 지도 렌더링 확인 (2026-11-06): 개발 서버와 프로덕션 빌드(`vite preview`) 모두 북미 지도가 표시되고 콘솔 오류 없음. MapLibre 6 + Vite 함정 3건은 12절 참고
- [x] 지도용 개발 키 발급 (`spotter-map-dev`, 서버용 키와 분리). TomTom 입력창이 `localhost`를 도메인으로 받지 않으므로(`example.com` 형식만 허용) **개발 키는 화이트리스트를 비워 둔다.** `frontend/.env.local`의 `VITE_TOMTOM_MAP_KEY`에 넣는다
- [ ] (12단계 배포 때) 배포용 지도 키 발급(`spotter-map-prod`) + 배포 도메인 화이트리스트 등록, 배포 빌드에는 이 키만 넣는다. 개발용 지도 키는 제품 제한이 없어 **라우팅 API도 호출된다**(2026-11-06 확인, HTTP 200). 배포용 키는 Products를 Map Display로 제한할 수 있는지 확인하고, 제한이 안 되면 도메인 화이트리스트만으로 방어한다. 화이트리스트가 타일·스타일 요청에 실제로 적용되는지(허용되지 않은 도메인에서 거부되는지) 확인한다
- [x] 지도 스타일 확정: 클래식 `basic_main` (Orbis 타일은 Vector Tiles 한도에 합산되지 않아 제외)
- [x] 클래식 스타일(레이어 775개) 렌더링 성능 측정 (2026-11-06, 프로덕션 빌드, Apple M4 Pro, Chrome, 기본 지도만): 확대·이동·축소 22초 동안 1,285프레임, 평균 17.1ms(약 58fps), p95 17.5ms, p99 33.3ms. 100ms 넘는 프레임 2개(최대 217ms), 롱태스크 1건(229ms, 첫 확대 직후). 가만히 있을 때 기준선은 평균 20.5ms. 스타일 로딩 약 0.4초, JS 357KB(gzip) + 워커 145KB(gzip). **레이어 숨김은 하지 않는다**(문제 없음). 한계: 성능이 좋은 기기에서 경로·heatmap 없이 잰 값이므로 11단계에서 다시 잰다
- [x] `.env`로 API 키 관리, `.gitignore`에 추가 (`.env.example` 작성, Django 설정은 `.env`의 `DJANGO_SECRET_KEY`가 없으면 시작하지 않음)
- [x] 요청·응답 형식 확정 `[결정]` (2026-11-06, 사용자 확인 완료): `docs/api-contract.md`, `frontend/src/types/api.ts`. 경로·heatmap 엔드포인트 분리, 추천 이유는 구조화 값으로 전달(문장은 프론트가 영어로 조립), heatmap 등급에 적재 규칙 포함, 오류 코드 7종

### 3단계. 위험 규칙 순수 함수와 단위 테스트

- [ ] 풍속·강우·강설 분류 함수 (3절)
- [ ] checkpoint 등급 = 세 등급 중 최고 등급
- [ ] 적재 규칙 상향 (4절)
- [ ] 테스트: 풍속 경계값 25, 35, 45, 55 mph와 34.5 같은 사이 값
- [ ] 테스트: 강우 0.10·0.25·0.50·1.00, 강설 0.5·1.0·2.0·3.0
- [ ] 테스트: 적재 규칙 3종 (30,000 lb, 40,000 lb 정확히인 경우 포함)

### 4단계. 경로 샘플링과 ETA

- [ ] checkpoint 생성: 출발지(0마일), 간격(10/25/50마일)마다, 도착지
- [ ] ETA = 출발 일시 + 해당 지점까지의 누적 이동 시간
- [ ] 시간대(timezone) 명시적 처리
- [ ] 각 checkpoint가 대표하는 마일 계산 (앞뒤 checkpoint와의 중간 지점까지)
- [ ] 테스트: 대표 마일의 합계 = 경로 전체 거리
- [ ] 테스트: 간격보다 짧은 경로, 간격으로 나누어떨어지지 않는 경로

### 5단계. ETA 기준 날씨 조회

- [ ] 각 checkpoint의 ETA 시각 예보 조회 (현재 날씨가 아님)
- [ ] 단위 변환: mph, in/hr
- [ ] 48시간치 일괄 조회와 캐싱
- [ ] ETA가 예보 범위를 벗어나면 오류 반환
- [ ] 테스트: 단위 변환, ETA 시각과 예보 시각의 매칭

### 6단계. 경로 요약과 추천

- [ ] 경로 요약 계산: Severe 마일, High 마일, 평균 위험도, 이동 시간
- [ ] 4개 기준 순서대로 비교 (가중치 점수 금지, 반올림한 값으로 동점 판정)
- [ ] No Travel 경로 제외, 3개 모두 No Travel이면 추천 없음
- [ ] 추천 이유 한 줄 생성
- [ ] 테스트: 1·2·3·4번 기준 각각에서 승부가 갈리는 경우
- [ ] 테스트: No Travel 경로가 일부인 경우와 전부인 경우

### 7단계. 백엔드 통합과 수동 검증

- [ ] 엔드포인트 하나로 3~6단계 통합
- [ ] 오류 처리: geocoding 실패, 경로 부족, 외부 API 장애
- [ ] 실제 구간 하나를 골라 등급과 추천 결과를 손으로 계산한 값과 비교

### 8단계. 화면 기본 구성

- [ ] 레이아웃: 왼쪽 패널(입력 폼, 경로 카드) + 오른쪽 지도
- [ ] 입력 폼: 출발지, 도착지, 출발 일시, 적재 중량, 샘플링 간격
- [ ] 지도에 경로 3개 표시 (선택 경로는 진하게, 나머지는 회색)
- [ ] 경로 카드에 숫자 4개: 심각 마일 / 높음 마일 / 평균 위험 / 소요 시간
- [ ] 추천 경로 표시와 추천 이유 한 줄
- [ ] No Travel 경고 배너

### 9단계. 위험도 표시

- [ ] 경로선을 위험도 색상 구간으로 표시
- [ ] 항상 보이는 범례
- [ ] checkpoint 마커: ETA, 그 시각의 날씨, 위험 등급
- [ ] checkpoint 리스트(타임라인)

### 10단계. heatmap과 0–48시간 슬라이더

- [ ] 경로 주변(trip corridor) 격자의 48시간 예보를 한 번에 수신
- [ ] heatmap을 WebGL 레이어로 표시
- [ ] 슬라이더 0시간 = 출발 일시 `[결정]`, 슬라이더 옆에 절대 날짜·시각 함께 표시
- [ ] 슬라이더 이동 시 API 재호출 없이 레이어만 교체
- [ ] 슬라이더와 트럭 예상 위치 동기화

### 11단계. 성능과 마무리 점검

- [ ] 로딩 상태와 오류 상태 표시
- [ ] 슬라이더가 끊기지 않는지 확인
- [ ] 호출이 가장 많은 조건(10마일 간격 + 장거리 경로)에서 응답 시간 확인
- [ ] 지도 렌더링 성능 재측정: 경로 3개 + heatmap 레이어 + 슬라이더 조작 중 프레임 시간 (2단계 기준값: 평균 17.1ms, p95 17.5ms, 100ms 초과 프레임 2개). 가능하면 CPU 스로틀링(DevTools)으로 낮은 사양도 확인
- [ ] JS 번들(현재 gzip 357KB) 분할 로딩 검토
- [ ] 전체 단위 테스트 통과

### 12단계. 배포

- [ ] 호스팅 위치 결정
- [ ] 백엔드와 프론트엔드 배포, 환경변수 설정
- [ ] 배포본에서 7단계의 검증 구간 재실행

### 13단계. 문서와 Loom

- [ ] README에 실행 방법 추가
- [ ] README의 규칙 해석·가정이 구현과 일치하는지 확인
- [ ] GitHub repository 정리 (비밀값이 커밋되지 않았는지 확인)
- [ ] Loom 5–10분 녹화: 입력 → 3개 경로 → 추천 이유 → 슬라이더

## 12. 프로젝트 구조와 개발 명령

```
spotter/
├── CLAUDE.md, README.md, .env.example   # 각 문서에 한국어판이 있다: *.ko.md
├── docs/api-contract.md        # 백엔드 ↔ 프론트 API 계약 (기준 문서)
├── backend/                    # Django + DRF (Python 3.12, uv)
│   ├── config/                 # settings(.env 로드), urls
│   └── trip/                   # API 앱: 위험 규칙·추천 등 순수 로직 + 뷰, tests/
└── frontend/                   # Vite + React + TypeScript + maplibre-gl
    └── src/{components, types}
```

| 용도 | 명령 (디렉터리) |
|---|---|
| 백엔드 실행 | `uv run python manage.py runserver` (`backend/`, 포트 8000) |
| 백엔드 테스트 | `uv run pytest` (`backend/`) |
| 백엔드 점검 | `uv run python manage.py check` (`backend/`) |
| 프론트 실행 | `npm run dev` (`frontend/`, 포트 5173, `/api`는 8000으로 프록시) |
| 프론트 점검 | `npm run lint`, `npm run build` (`frontend/`) |

- 환경변수: 루트 `.env`(서버용 `TOMTOM_API_KEY`, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`), 프론트용 `frontend/.env.local`(`VITE_TOMTOM_MAP_KEY`, 지도 전용 키). 둘 다 커밋하지 않는다.
- `VITE_TOMTOM_MAP_KEY`가 빌드 시점에 없으면 지도 코드가 번들에서 빠진다(키가 있을 때 JS 약 1.28MB, gzip 357KB). 배포 빌드에서 반드시 설정한다. 번들 크기는 11단계에서 점검한다(지도 코드 분할 로딩 검토).
- 시스템에 깨진 `black`이 있어 `django-admin startproject` 실행 시 `Bad CPU type` 오류가 출력되지만 파일은 정상 생성된다(무시).

### MapLibre 6 + Vite 알려진 함정 (2026-11-06, 모두 해결됨 — 되돌리지 말 것)

지도 코드를 건드린 뒤에는 개발 서버만 보지 말고 **프로덕션 빌드도 실제로 열어 확인한다**(`npm run build` → `npx vite preview` → 브라우저). 개발 서버는 정상이어도 빌드는 깨졌던 적이 있다.

1. **개발 서버: `Worker failed to load`** — Vite가 maplibre-gl을 사전 번들해 워커 파일을 `.vite/deps/`에서 찾다 404가 난다. → `vite.config.ts`의 `optimizeDeps.exclude: ['maplibre-gl']`.
2. **프로덕션 빌드: 같은 오류** — 워커 주소가 `new URL('./maplibre-gl-worker.mjs', import.meta.url)`인데 빌드가 이 파일을 만들지 않는다. → `MapView.tsx`에서 `maplibre-gl/dist/maplibre-gl-worker.mjs?url`을 import해 `setWorkerUrl()`로 지정. (1번의 exclude만으로는 개발 서버만 고쳐지고, `setWorkerUrl`만으로는 개발 서버가 안 고쳐진다. 둘 다 필요하다.)
3. **지도 높이 0** — `maplibre-gl.css`가 컨테이너를 `position: relative`로 덮어써 `.map { position: absolute; inset: 0 }`이 무효가 된다. → `index.css`에서 `.map-area .map`으로 선택자 우선순위를 높인다.
