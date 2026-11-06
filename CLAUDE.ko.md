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
- `[해석]` 동점 판정: 화면에 표시하는 값으로 반올림해 비교한다(마일은 1마일, 평균 위험도는 소수 둘째 자리, 이동 시간은 분). 반올림 없이 실수로 비교하면 3번 기준에서 거의 항상 승부가 나서 4번(이동 시간)이 쓰이지 않고, PDF의 "balancing weather risk and travel time"과 어긋난다. 반올림은 파이썬의 `round`(짝수 쪽으로)가 아니라 **반올림(half up)**이다(24.5마일은 25로 표시). 딱 절반인 값 때문에 화면에서는 동점인데 비교에서는 차이가 나는 일이 없게 하려는 것이다. 네 기준이 모두 같으면 라우팅 API가 먼저 준 경로가 이긴다(`decided_by: duration`으로 보고).
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
    - **예보 끝을 넘는 두 가지 경우(2026-11-06 측정):** (a) HTTP 400 `Parameter 'start_hour'(또는 'end_hour') is out of allowed range from 2026-08-05 to 2026-11-21`(예보 마지막 *날짜*만 알려주고 시각은 없음), (b) HTTP 200이지만 마지막 날 19:00 UTC부터 `null`. 둘 다 `FORECAST_OUT_OF_RANGE`로 처리한다. (a)는 마지막 정상 시각을 알기 위해 1개 지점짜리 호출을 한 번 더 한다(오류 경로에서만). 이 호출이 실패해도 `forecast_end` 없이 오류는 그대로 보낸다.
    - **응답 사실:** 지점 1개는 객체, 여러 개는 리스트로 온다. 풍속 단위 표기는 `mph`가 아니라 `mp/h`이므로, 코드는 받은 단위 표기를 확인하고 다른 단위면 거부한다. 강우·강설 값은 소수 셋째 자리까지 온다.
    - **출발 일시 검증:** PDF에 출발 일시 범위 제한이 없으므로 **임의의 상한(예: +7일)을 두지 않는다.** 거부 조건은 둘뿐이다. (1) 출발 시각이 과거(TomTom은 과거 `departAt`을 오류 없이 받으므로 앱이 직접 막는다). (2) 필요한 시간(마지막 checkpoint ETA, 출발 +48시간)이 예보 끝을 넘음 → 응답의 `null`/범위 초과로 판정한다.
    - **heatmap 격자 `[결정]`:** 간격 0.5°(약 34마일), 경로 3개 합집합 기준 양쪽 40마일 버퍼. 시카고→덴버(경로 1,004 / 1,163 / 1,336마일)에서 **278개 지점**. 0.25° 격자는 570~1,116개라 한도에 맞지 않아 쓰지 않는다. 10단계에서 구현(`backend/trip/grid.py`): 그 여행은 280개 지점(2026-11-06 실측). 격자는 간격의 배수 위에 있으면서 어느 경로에서든 40마일 이내인 모든 점이다. 600개를 넘게 필요한 여행(전국을 가로지르는 멀리 떨어진 경로 3개)은 1.0° 또는 2.0° 격자를 쓰며, 이렇게 해서 heatmap 한 번의 비용을 날씨 호출 600건으로 묶고, 응답이 어떤 간격을 썼는지 알려준다. 변수는 `wind_speed_10m`, `rain`, `showers`, `snowfall`, 시간 창은 출발 시각부터 +48시간(0~48시간, 49개 값).
    - **checkpoint 날씨:** heatmap과 별도로 checkpoint 좌표(소수 둘째 자리 반올림)에서 직접 조회한다. 체크포인트 수(경로 3개, 중복 제거): 10마일 351개 / 25마일 141개 / 50마일 71개.
    - `[해석]` **어느 시각을 쓰나:** checkpoint는 ETA에 **가장 가까운 정시**의 예보를 쓴다(정확히 :30이면 늦은 쪽 시각). 예보는 정시 단위이고 heatmap 슬라이더도 정시 단위라서, checkpoint와 heatmap이 같은 예보를 보여준다. 풍속은 그 정시의 순간값이고, 강우·강설은 *직전 1시간* 합계(in/hr)다.
    - `[해석]` `rain + showers`는 소수 넷째 자리로 반올림한다. 0.09 + 0.01 = 0.09999999999999999 같은 실수 덧셈 오차가 0.10 경계 아래로 떨어지기 때문이다.
    - **1회 분석 비용(시카고→덴버):** 25마일 간격 141 + 278 = **419건**(하루 약 23회), 10마일 간격 351 + 278 = **629건**(하루 약 15회). 캐시 키는 (반올림 좌표, 시간 창 시작)이며 TTL 약 1시간이다. 적재 중량은 날씨에 영향이 없으므로 중량만 바꿔 다시 분석할 때는 날씨를 다시 부르지 않는다.
  - TomTom 호출 규격 `[결정]` (2026-11-06 실제 호출로 확인):
    - 경로: `GET /routing/1/calculateRoute/{lat,lon}:{lat,lon}/json` + `travelMode=truck`, `vehicleCommercial=true`, `vehicleWeight=<kg>`, `maxAlternatives=2`, `departAt=<출발 일시>`, `instructionsType=coded`
    - 주소 변환: `GET /search/2/geocode/{주소}.json` + `countrySet=US`, `limit=1`
    - 적재 중량은 앱 입력이 lb이므로 TomTom에는 kg으로 변환해서(×0.45359237) 전달한다. 위험·적재 규칙 판정은 입력 lb 값으로 한다.
    - 응답의 경로선은 `routes[].legs[].points[]`(위도·경도만, 시간 없음)이다. 시카고→덴버 한 경로가 약 1만 점이다.
    - `[해석]` ETA: `guidance.instructions[]`의 (`pointIndex`, `routeOffsetInMeters`, `travelTimeInSeconds`)를 기준점으로 쓰고, 기준점 사이는 경로선 거리 비율로 시간을 보간한다. 4단계에서 검증했다: 중앙값 오차 0.1분, 14시간 여정에서 최대 3.7분(4단계 체크리스트 참고).
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

- [x] 풍속·강우·강설 분류 함수 (3절): `backend/trip/risk.py`의 `classify_wind`, `classify_rain`, `classify_snow`
- [x] checkpoint 등급 = 세 등급 중 최고 등급: `assess_checkpoint()`가 `level_by`, `base_level`, `level`, `load_escalated`(계약의 checkpoint 필드)를 반환
- [x] 적재 규칙 상향 (4절): `apply_load_rules()`는 등급을 올리기만 한다. `load_escalated`는 최종 등급이 기본 등급보다 높을 때만 true(날씨가 이미 그 등급에 도달했으면 false)
- [x] 테스트: 풍속 경계값 25, 35, 45, 55 mph와 34.5 같은 사이 값 (`backend/trip/tests/test_risk.py`)
- [x] 테스트: 강우 0.10·0.25·0.50·1.00, 강설 0.5·1.0·2.0·3.0 (각각 바로 아래 값과 바로 위 값 포함)
- [x] 테스트: 적재 규칙 3종 (30,000 lb, 40,000 lb 정확히인 경우 포함), 그리고 격자 전수로 "적재 규칙은 등급을 낮추지 않는다", "등급은 세 조건 중 최고"를 확인
- [x] 테스트가 실수를 잡아내는지 검증 (2026-11-06): `risk.py`를 일부러 틀리게 바꾼 20가지(`>=`/`>` 뒤집기, 임계값 이동, 등급을 낮추는 적재 규칙, 입력 검사 제거 등)를 모두 잡아냈다. 427개 테스트 통과
- [x] 잘못된 측정값은 0으로 취급하지 않고 `ValueError`를 낸다: `None`, NaN, 무한대, 음수, 불리언, 문자열. 날씨 값이 없다고 해서 구간이 안전해 보이면 안 되므로, 5단계는 누락/`null` 예보 값을 `WEATHER_UNAVAILABLE` 오류로 바꿔야 하며 0을 대신 넘기면 안 된다
- [x] `.env` 없이도(새로 받은 저장소, CI) 테스트가 돈다: pytest는 `config/settings_test.py`를 쓰고, 이 설정은 `DJANGO_SECRET_KEY`가 없을 때만 임시 값을 채운다. 앱 자체는 여전히 키가 없으면 시작하지 않는다

### 4단계. 경로 샘플링과 ETA

- [x] checkpoint 생성: 출발지(0마일), 간격(10/25/50마일)마다, 도착지: `backend/trip/sampling.py`의 `checkpoint_miles()`, `build_checkpoints()`(순수 함수). 목적지가 간격과 정확히 겹치면 두 번 나오지 않는다(부동소수점 오차는 1e-6마일 허용치로 흡수)
- [x] ETA = 출발 일시 + 해당 지점까지의 누적 이동 시간: 시간은 TomTom 안내 지점에서만 알 수 있으므로 지점 사이는 거리 비율로 보간한다. 시카고→덴버 실제 경로 3개에서 안내 지점 하나를 빼고 이웃으로 추정해 측정: 중앙값 0.1분, 14시간 여정에서 최대 3.7분(경로 전체 평균 속도 하나로는 최대 43분 틀림)
- [x] 시간대(timezone) 명시적 처리: `departure`는 timezone 정보가 있어야 하고(없으면 `ValueError`), ETA는 UTC로 초 단위 반올림해 반환한다. CST/MST/서울 오프셋, 자정 넘김, 2026-11-01 미국 서머타임 해제일에서 테스트
- [x] 각 checkpoint가 대표하는 마일 계산 (앞뒤 checkpoint와의 중간 지점까지): `represented_miles()`. 첫 checkpoint는 0마일에서 시작하고 마지막은 도착지에서 끝난다
- [x] 경로 거리 계산: 경로선에는 좌표만 있고, haversine 길이는 TomTom 길이보다 약 0.2% 짧다(1,000마일 경로에서 최대 3.3km). 그래서 안내 지점 사이를 구간별로 늘려 각 안내 지점의 TomTom 거리와 정확히 일치시킨다. 안내 지점의 거리에 둔 checkpoint는 그 안내 지점의 위치에 정확히 놓인다
- [x] 테스트: 대표 마일의 합계 = 경로 전체 거리 (균일·속도 변화·실제·무작위 경로 25개)
- [x] 테스트: 간격보다 짧은 경로, 간격으로 나누어떨어지지 않는 경로 (8마일, 25마일, 25.5마일, 101마일 등, 10/25/50 간격)
- [x] 실제 데이터 테스트: `backend/trip/tests/fixtures/tomtom_route_prefix.json`은 기록한 TomTom 경로의 처음 156.6마일(점 2,909개, 안내 지점 26개, 그중 둘은 `pointIndex` 1080을 공유)
- [x] 예외 규칙: `pointIndex`가 같은 안내 지점은 첫 번째만 쓴다. 첫·마지막 안내 지점은 항상 (0m, 0초)와 (총 길이, 총 시간)으로 고정한다. 거리나 시간이 거꾸로 가는 안내 지점은 거부한다. 안내 지점이 없으면 시간은 거리에 비례한다. 정차(같은 거리, 더 늦은 시간)에서는 checkpoint가 트럭이 **처음 도착하는** 시각을 받는다
- [x] 변형 검증 (2026-11-06): `sampling.py`를 일부러 틀리게 바꾼 26가지 중 23가지를 잡았다. 나머지 3가지는 동작이 같은 변형이다(정확히 같을 때만 달라지는 `<`/`<=`, 다른 검사가 이미 막는 입력 검사 2개). **실제 결함**도 찾았다: `checkpoint_miles`가 무한대 길이나 아주 작은 간격에서 끝나지 않는 루프에 빠졌다. 지금은 유한하지 않은 값과 `MAX_CHECKPOINTS`(10,000)개 초과를 거부한다. 635개 테스트 통과
- [x] 7단계에서 처리: 출발지 = 도착지는 `destination`에 대한 `INVALID_INPUT`으로 거부한다(약 1 m 이내의 같은 장소, 또는 길이 0인 경로)
- [x] 7단계에서 처리: `mile`, `represents_miles`, 좌표, 시각은 응답을 만들 때만 반올림한다

### 5단계. ETA 기준 날씨 조회

- [x] 각 checkpoint의 ETA 시각 예보 조회 (현재 날씨가 아님): `backend/trip/weather_client.py`의 `WeatherClient.get_weather_at()`이 (위도, 경도, ETA)를 받아 풍속·강우·강설을 같은 순서로 돌려준다. ETA는 가장 가까운 정시 예보에 대응시킨다(`weather.py`의 `nearest_hour()`)
- [x] 단위 변환: Open-Meteo에 `mph`·`inch`로 직접 요청하고, 응답의 단위 표기를 확인한다(`km/h` 등 다르면 거부). rain = `rain + showers`, snow = `snowfall`. mph의 표기는 `mp/h`다
- [x] 일괄 조회와 캐싱: 요청당 최대 200개 지점(최대 4개 병렬), 각 요청은 필요한 시각만 요청, 같은 (위치, 시각)은 한 번만 조회, 응답의 정상 시각은 모두 1시간 캐시(Django 캐시, 50,000건). 실측: 230개 지점 = 요청 2번 1.4초, 반복 호출 = 요청 0번. 같은 출발 일시에 적재 중량만 바꾸면 날씨 호출이 없다. (heatmap용 48시간 격자 조회는 10단계)
- [x] ETA가 예보 범위를 벗어나면 오류: `ForecastOutOfRange`(HTTP 400 또는 예보 끝의 `null` 시간, 찾을 수 있으면 `forecast_end` 포함) → `FORECAST_OUT_OF_RANGE`. 그 밖의 실패(시간 초과, 429/5xx 3회 시도 후, 이상한 데이터, 중간의 `null`)는 `WeatherUnavailable` → `WEATHER_UNAVAILABLE`. 없는 값은 0으로 채우지 않고, 지점 하나가 나빠도 호출 전체가 실패한다
- [x] 테스트: 단위 변환, ETA 시각과 예보 시각 매칭(`backend/trip/tests/test_weather.py`, `test_weather_client.py`): :29/:30 반올림, 다른 시간대, 자정과 미국 시간 되돌림 날짜, 요청 파라미터, 결과 순서, 중복 제거, 200/201개 분할, 캐시 적중/미적중, 재시도, 두 가지 예보 범위 초과, 단위, 이상한 값
- [x] 테스트가 실수를 잡는지 검증(2026-11-06): `weather.py`와 `weather_client.py`에 의도적 변형 59개. 첫 실행에서 진짜 공백 3건을 찾았고(요청보다 *많은* 지점이 돌아와도 받아들임, 위도나 경도가 빠진 캐시 키는 다른 장소의 날씨를 돌려줌) 지금은 막았다. 살아남은 4건은 원본과 동작이 같다. 테스트 784개 통과
- [x] 실제 API로 확인(2026-11-06): 기록해 둔 시카고 경로(체크포인트 8개)를 샘플링 → 날씨 → 위험 등급까지 통과시켰다. 같은 시각을 API에 직접 요청한 값과 일치한다. 예보를 넘는 출발 일시는 두 경우 모두 `forecast_end` 2026-11-21 18:00Z와 함께 `FORECAST_OUT_OF_RANGE`가 된다

### 6단계. 경로 요약과 추천

- [x] 경로 요약 계산: `backend/trip/summary.py`의 `summarize_route()`가 체크포인트의 등급과 각각이 대표하는 마일을 받아, 계약의 요약 필드를 표시용으로 반올림해 돌려준다(등급별 마일, `severe_miles`, `high_miles`, 구간 길이로 가중한 `avg_risk`, `duration_minutes`, `arrival`, `has_no_travel`). Severe 마일은 Severe 등급만(No Travel 제외), High 마일은 High 등급만이다
- [x] 4개 기준 순서대로 비교 (가중치 점수 금지, 반올림한 값으로 동점 판정): `backend/trip/recommend.py`의 `recommend()`가 반올림한 값의 튜플(Severe 마일, High 마일, 평균 위험도, 분)로 정렬한다. 정렬은 안정(stable)이라 네 기준이 모두 같으면 라우팅 API가 준 순서가 유지된다. `decided_by`는 승자가 **차점 경로**(꼴찌가 아님)와 처음 달라지는 기준이다
- [x] No Travel 경로 제외, 3개 모두 No Travel이면 추천 없음: 제외된 경로는 `excluded_route_ids`에 담고, 남은 경로가 없으면 `route_id`는 `null`(오류 아님), 하나 남으면 `only_candidate`, 경로가 3개 미만이어도 같은 방식으로 동작한다
- [x] 추천 이유 한 줄: 계약대로 백엔드는 구조화된 값(`decided_by`, `versus_route_id`, `duration_delta_minutes`)만 보낸다. 영어 문장은 8단계("추천 경로와 이유 한 줄 표시")에서 프론트엔드가 만든다
- [x] 테스트: 1·2·3·4번 기준 각각에서 승부가 갈리는 경우(`backend/trip/tests/test_recommend.py`), "점수로 섞지 않음" 사례(심각 0마일이 어떤 속도보다 우선 등), 반올림한 값의 동점(심각 24.6 vs 25.4마일, 평균 위험도 0.331 vs 0.334, 분 단위 30초 차이)을 `summarize_route`부터 끝까지 이어서 검증
- [x] 테스트: No Travel 경로가 일부인 경우와 전부인 경우, 하나만 남는 경우, 경로가 하나만 주어진 경우, 없는 경우; 동점이 많은 무작위 3,000건을 네 값의 단순 `min()`과 대조
- [x] 테스트가 실수를 잡는지 검증(2026-11-06): `summary.py`와 `recommend.py`에 의도적 변형 42개(기준 빼기·바꾸기, 짝수 반올림, 가중하지 않은 평균, 잘못된 등급 필드, 뒤집힌 차이 부호, 잘못된 차점 경로 등)를 넣었고 모두 잡았다. 테스트 883개 통과
- [x] 실제 경로로 확인(2026-11-06): 기록해 둔 시카고 경로에 실제 날씨와 가상의 폭풍 변형 두 개를 더해 샘플링 → 날씨 → 위험 → 요약 → 추천까지 이었다. 손으로 계산하면 25마일짜리 체크포인트 3개의 40 mph 바람은 High 75마일, 평균 위험도 75×2/157 = 0.96이다. 적재 45,000 lb에서는 같은 바람이 Severe가 되고 50 mph 체크포인트는 No Travel이 되어 그 경로가 제외된다

### 7단계. 백엔드 통합과 수동 검증

- [x] `POST /api/analyze`(`backend/trip/`) 뒤에 3~6단계 통합: `validation.py`(요청) → `analysis.py`(양쪽 끝 지오코딩을 병렬로 → TomTom 경로 → 체크포인트 → 모든 경로의 모든 체크포인트를 **한 번의** 날씨 호출로 → 위험 → 요약 → 추천 → 응답). 보조 모듈: `tomtom.py`(지오코딩·트럭 경로, 캐시), `geometry.py`(위험 색상 구간, 약 33 m 허용오차의 Douglas-Peucker 단순화: 89마일 경로가 점 2,000개 → 약 117개), `errors.py`(오류 형식 하나), `views.py`. 재시도 로직은 `http.py`에서 공유한다. `/api/heatmap`은 10단계
- [x] 오류 처리, 실제 서버로 확인: 없는 주소(422 `GEOCODE_NOT_FOUND`와 필드), 경로 없음(시카고 → 호놀룰루, 422), 같은 장소(400), 과거 출발(400), 예보를 넘는 출발(422, `forecast_end` 포함), 잘못된 간격·시간대 없는 시각·음수 중량·필드 누락·잘못된 JSON·배열 본문·GET(400, 405), TomTom 또는 Open-Meteo 장애(502, 메시지에 URL이나 키 없음). 경로가 3개 미만이면 받은 그대로 보여준다. 경로는 15분 캐시해서, 같은 요청을 다시 보내면(예: 간격만 변경) 4초 대신 25 ms가 걸렸다
- [x] 실제 경로 하나를 손으로 계산한 값과 비교(2026-11-06): 노스캐롤라이나 롤리 → 버지니아 노퍽, 14:00Z 출발, 42,000 lb, 10마일 체크포인트, 실제 폭우 중. 독립 스크립트(`trip/`을 전혀 import하지 않음)가 TomTom과 Open-Meteo를 직접 호출해 모두 다시 계산했다: 체크포인트 70개의 위치(경로선에서 5 m 이내), ETA(1초 이내), 날씨 값, 등급, 등급별 마일, 평균 위험도, 순위, 제외, `decided_by`. **모든 숫자가 일치했다.** 경로 C에는 실제 No Travel 체크포인트(250마일, 18:00Z, 강우 1.02 in/hr)가 있어 제외됐고, A와 B는 Severe·High 마일이 둘 다 0으로 같아서 평균 위험도로 B가 이겼다(Moderate 20마일 ÷ 206.9마일 = 0.097 → 0.10, A는 20 ÷ 184.6 = 0.108 → 0.11). B가 26분 더 느린데도 그렇다
- [x] 테스트가 실수를 잡는지 검증(2026-11-06): 새 모듈에 의도적 변형 107개. 첫 실행에서 진짜 공백 12건을 찾았고(경로 캐시가 도착지를 무시, 경도를 위도로 보정하지 않음, 절단 위치를 검증하지 않음 등) 지금은 막았다. 살아남은 것은 원본과 동작이 같다. 테스트 1,148개 통과

### 8단계. 화면 기본 구성

- [x] 레이아웃: 왼쪽 패널(폼, 결과, 경로 카드, 출처 표기) + 오른쪽 지도(`frontend/src/App.tsx`, `index.css`). 너비 820 px 미만에서는 지도가 위, 패널이 아래다. 실제 브라우저에서 확인(개발 서버와 프로덕션 빌드)
- [x] 입력 폼(`components/AnalysisForm.tsx`): 출발지, 도착지, 출발 일시(`datetime-local`), 적재 중량(lb), 체크포인트 간격 10 / 25 / 50 mi(기본 25). 기본값은 Chicago, IL → Denver, CO, 42,000 lb, 다음 15분 단위 시각이라 검토자가 바로 버튼을 누를 수 있다. 비었거나 잘못된 값은 보내기 전에 잡고, 서버가 특정 필드의 오류로 알려준 것(없는 주소, 과거 출발 등)은 그 필드 아래에, 나머지 오류는 상자에 보여준다. 마지막 요청만 유효하고(이전 요청은 중단), 버튼은 "Analyzing…"으로 바뀌며 최대 10초 걸릴 수 있다고 안내한다
- [x] 지도의 경로(`components/MapView.tsx`): 선택 경로는 흰 테두리가 있는 굵은 파란색, 나머지는 가는 회색. 지도의 회색 경로나 해당 카드를 누르면 선택된다. 출발지는 초록, 도착지는 빨강 점. 결과가 도착하면 경로 전체로 확대한다(선택만 바뀔 때는 확대하지 않음). 선은 베이스맵 위에 그린다: 라벨 레이어 아래에 두면 베이스맵 도로가 선을 덮었다
- [x] 경로 카드(`components/RouteCard.tsx`)에 숫자 4개 `Severe mi` / `High mi` / `Avg risk` / `Duration`. 머리줄에는 경로 거리(4개 숫자가 아니라 이름표)와 `Recommended`·`No Travel` 배지도 보이고, 막힌 경로는 점선 테두리다
- [x] 추천 경로와 이유 한 줄: `lib/reason.ts`가 구조화된 값으로 문장을 만든다. 예: "Lowest average risk (0.10 vs 0.11 on Route A), 26 min slower than Route A." 모든 분기를 단위 테스트했다(심각, 높음, 평균, 시간, 완전 동점, 유일 후보, 추천 없음). 서버가 찾은 장소 이름을 카드 위에 보여주므로 잘못 찾은 주소를 알아볼 수 있다
- [x] No Travel 경고 배너(`components/NoTravelBanner.tsx`): 막힌 경로 이름과 각 경로의 첫 No Travel 지점(마일과 현지 시각, 적재 규칙 때문이면 "heavy load in strong wind")을 보여주는 큰 빨간 배너. 경로가 3개 미만이면 안내("Only 2 routes available for this trip.")도 보여주고, Open-Meteo CC BY 4.0 출처 표기는 항상 화면에 있다
- [x] 프론트엔드 테스트(`npm test`, vitest): 시간 변환(현지 시각 → UTC, 시간 되돌림 날짜, 자정), 추천 문장, 경고, API 클라이언트의 오류 처리(네트워크 실패, HTML 오류 페이지, 중단)를 다루는 65개. 이 모듈들에 의도적 변형 36개를 넣어 동작이 같은 1개를 빼고 모두 잡았다(첫 실행에서 진짜 공백 1건, 마일 반올림을 찾아 막았다)
- [x] 실측(2026-11-06): 출발 시각이 지금과 가까우면 TomTom이 **실시간 교통**을 반영한다. 시카고 → 덴버가 1,184 / 1,212 / 1,338마일로 나왔고(교통 지연 때문에 1,006마일 I-80 경로가 빠짐), 4일 뒤 출발은 1단계와 같은 1,006 / 1,164 / 1,338마일, `traffic=false`는 다시 1단계와 같은 조합이다. 즉 언제 출발하느냐에 따라 경로 구성과 시간이 달라진다. 요청이 잘못된 것이 아니라 TomTom의 실시간 데이터다

### 9단계. 위험도 표시

- [x] 경로선을 위험도 색상 구간으로 표시: 선택한 경로는 API의 `segments`로 등급마다 색을 달리해 그리고(`map/layers.ts`, `map/geo.ts`), 나머지 경로는 회색으로 둔다. 하나의 팔레트(`lib/risk.ts`: 초록, 노랑, 주황, 빨강, 짙은 보라)를 선, 점, 범례, 그리고 10단계의 heatmap이 함께 쓴다. 단계마다 색상뿐 아니라 밝기도 달라서 빨강과 초록을 구분하지 못하는 사람도 순서를 알 수 있고, 색이 서로 다른지와 Moderate부터 점점 어두워지는지를 단위 테스트로 확인한다. 선 끝은 butt로 해서 한 등급이 끝나는 곳에서 다음 등급이 정확히 시작한다
- [x] 항상 보이는 범례(`components/Legend.tsx`): PDF의 이름을 쓴 다섯 등급과 "Other routes"를, 경로가 있든 없든 지도 왼쪽 아래에 보여준다
- [x] checkpoint 마커: 선택한 경로의 모든 checkpoint에 등급 색의 점을 찍는다. 점을 누르면 팝업이 열려 도착 시각, 풍속·강우·강설과 각각이 주는 등급, 최종 등급, 그리고 적재 규칙이 등급을 올렸다면 어느 규칙인지를 보여준다(`map/popup.ts`, `lib/checkpoint.ts`: "Load over 30,000 lb with wind of 45-54 mph" 또는 "Load over 40,000 lb with wind of 35-44 mph", 최종 등급으로 구분). 강우·강설은 소수 셋째 자리까지 보여줘서 Low인 0.095가 0.10으로 읽히지 않는다. 점을 누른 것이 그 아래 경로를 누른 것으로 처리되지 않는다
- [x] checkpoint 리스트(타임라인)(`components/CheckpointTimeline.tsx`): 선택한 경로의 checkpoint를 운행 순서대로 마일, 등급, 도착 시각(사용자 시간대, 목록 위에 명시), 날씨 한 줄로 보여주고 Severe와 No Travel은 빨간색이다. 지도와 양방향으로 연결된다: 목록 항목을 고르면 지도가 그곳으로 이동해 팝업이 열리고, 점을 누르면 해당 목록 항목이 강조되며 스크롤된다. 팝업을 닫으면 강조가 풀리고, 다른 경로를 고르면 초기화된다
- [x] 실제 브라우저에서 확인(2026-11-06, 실제 폭우 중인 롤리 → 노퍽, 개발 서버와 프로덕션 빌드): 경로 B는 초록 선에 노란 Moderate 구간, 경로 C는 짙은 보라색 No Travel 구간이고 팝업에 강우 1.02 in/hr가 표시된다. checkpoint 문구·팔레트·지도 데이터의 단위 테스트(35개 추가, 총 100개)와 의도적 변형 28개(모두 잡음)

### 10단계. heatmap과 0–48시간 슬라이더

- [x] 경로 주변(trip corridor) 격자의 48시간 예보를 한 번에 수신: `POST /api/heatmap`(`backend/trip/heatmap.py`, `grid.py`, `views.py`)이 `/api/analyze`와 같은 본문을 받아 캐시된 경로를 재사용하고, 격자를 만들고, 모든 지점의 모든 시각을 한 번의 묶음 날씨 호출(280개 지점 × 49시간, 요청 2번)로 조회해 checkpoint와 같은 위험·적재 규칙으로 49시간 전체의 등급을 돌려준다. 실측: 경로 캐시가 비었을 때 첫 호출 8.8초, 반복 호출 0.15초, 31 KB. 날씨 캐시에 시간대별 값이 남으므로 적재 중량만 바꿔 다시 불러도 Open-Meteo를 부르지 않는다.
- [x] heatmap을 WebGL 레이어로 표시: 경로선 아래의 MapLibre `circle` 레이어 하나. 원은 부드럽고(blur 1) 격자 간격의 약 0.9배 크기라 면으로 이어진다. 반지름은 확대 단계마다 두 배가 되어 지상에서의 크기가 유지되고, 색은 경로와 같은 팔레트다. 평온한 날씨는 연하고 위험은 진하다(불투명도 0.16~0.66). 반지름이 더 작았던 첫 버전은 격자 행 사이에 가로 줄무늬가 보였다: 행은 남북으로 간격 전체만큼 떨어져 있지만 동서로는 더 가깝기 때문이다
- [x] 슬라이더 0시간 = 출발 일시 `[결정]`, 슬라이더 옆에 절대 날짜·시각 표시(`components/ForecastSlider.tsx`): "Departure hour · Fri, Nov 6, 10:00 PM GMT+8", 이후 "+5 h · ...". 0시간은 출발 시각을 **가장 가까운 정시로 맞춘 값**이다(계약서는 "내림"이었다. 반올림은 checkpoint와 같은 규칙이라 checkpoint와 heatmap이 같은 예보를 보여주고, 실제 출발과 최대 30분 차이다). heatmap을 만들 수 없으면(예: 예보가 출발 + 48시간보다 먼저 끝남) 경로는 그대로 보이고 슬라이더 영역에 이유가 나온다
- [x] 슬라이더 이동 시 API 재호출 없이 레이어만 교체: 격자 전체를 시간대별 등급(`h0`~`h48` 속성)과 함께 지도에 한 번만 올리고, 슬라이더는 색을 읽는 속성만 바꾼다(`setPaintProperty`). 브라우저에서 슬라이더 97단계를 측정: **API 호출 0건**, 평균 프레임 16.6 ms, 가장 느린 프레임은 개발 서버 19.2 ms, 프로덕션 빌드 23.6 ms, 50 ms를 넘는 프레임 없음. 슬라이더를 움직여도 무거운 부분은 다시 그려지지 않는다
- [x] 슬라이더와 트럭 예상 위치 동기화: 선택한 경로 위에 그 시각의 트럭 위치를 검은 점으로 표시한다(`lib/heatmap.ts`: checkpoint의 ETA로 마일을 보간하고, 그 비율만큼 경로선을 길이로 따라간 위치). "Route A: truck at mile 407 of 1028", 출발 전에는 "leaves Fri 2:15 PM", 도착 후에는 "arrived Fri 5:25 PM"
- [x] 테스트: 백엔드 73개 추가(무차별 대입과 대조한 격자, heatmap 유스케이스, 엔드포인트. 총 1,221개), 프론트엔드 40개 추가(총 140개). 변형 테스트: 격자와 heatmap에서 진짜 결함을 찾았다. 위도로 여러 도에 걸친 긴 직선 구간이 먼 쪽 끝을 잘못된 축척으로 재서 40마일 이내의 점을 빠뜨렸다(변형이 아니라 새로 쓴 테스트가 찾았다). 구간을 0.25° 조각으로 자르도록 고쳤다. 프론트엔드에서는 공백 2건과 죽은 코드 1건(제거)을 더 찾았다. 살아남은 몇 개는 원본과 동작이 같다

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
│   ├── config/                 # settings(.env 로드), settings_test(pytest용), urls
│   └── trip/                   # API 앱: 위험 규칙·추천 등 순수 로직 + 뷰, tests/
└── frontend/                   # Vite + React + TypeScript + maplibre-gl
    └── src/{components, lib, types}   # lib: API 클라이언트, 포맷, 추천 문장(테스트 있음)
```

| 용도 | 명령 (디렉터리) |
|---|---|
| 백엔드 실행 | `uv run python manage.py runserver` (`backend/`, 포트 8000, `POST /api/analyze`) |
| 백엔드 테스트 | `uv run pytest` (`backend/`, `.env` 불필요) |
| 백엔드 점검 | `uv run python manage.py check` (`backend/`) |
| 프론트 실행 | `npm run dev` (`frontend/`, 포트 5173, `/api`는 8000으로 프록시). **백엔드도 함께 실행해야 한다**(터미널 하나 더). 없으면 폼에 "The server is not responding (HTTP 502)"가 표시되고 개발 서버에 `ECONNREFUSED`가 출력된다 |
| 프론트 점검 | `npm run lint`, `npm test`, `npm run build` (`frontend/`) |

- 환경변수: 루트 `.env`(서버용 `TOMTOM_API_KEY`, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`), 프론트용 `frontend/.env.local`(`VITE_TOMTOM_MAP_KEY`, 지도 전용 키). 둘 다 커밋하지 않는다.
- `VITE_TOMTOM_MAP_KEY`가 빌드 시점에 없으면 지도 코드가 번들에서 빠진다(키가 있을 때 JS 약 1.28MB, gzip 357KB). 배포 빌드에서 반드시 설정한다. 번들 크기는 11단계에서 점검한다(지도 코드 분할 로딩 검토).
- 변형 검증을 할 때는 `__pycache__`를 지우고 Python을 `-B`로 실행한다: 이전 변형과 파일 크기·수정 초가 같으면 낡은 `.pyc`가 쓰여, 잡지 못한 변형이 "잡힘"으로 보인 적이 있다.
- 시스템에 깨진 `black`이 있어 `django-admin startproject` 실행 시 `Bad CPU type` 오류가 출력되지만 파일은 정상 생성된다(무시).

### MapLibre 6 + Vite 알려진 함정 (2026-11-06, 모두 해결됨 — 되돌리지 말 것)

지도 코드를 건드린 뒤에는 개발 서버만 보지 말고 **프로덕션 빌드도 실제로 열어 확인한다**(`npm run build` → `npx vite preview` → 브라우저). 개발 서버는 정상이어도 빌드는 깨졌던 적이 있다.

1. **개발 서버: `Worker failed to load`** — Vite가 maplibre-gl을 사전 번들해 워커 파일을 `.vite/deps/`에서 찾다 404가 난다. → `vite.config.ts`의 `optimizeDeps.exclude: ['maplibre-gl']`.
2. **프로덕션 빌드: 같은 오류** — 워커 주소가 `new URL('./maplibre-gl-worker.mjs', import.meta.url)`인데 빌드가 이 파일을 만들지 않는다. → `MapView.tsx`에서 `maplibre-gl/dist/maplibre-gl-worker.mjs?url`을 import해 `setWorkerUrl()`로 지정. (1번의 exclude만으로는 개발 서버만 고쳐지고, `setWorkerUrl`만으로는 개발 서버가 안 고쳐진다. 둘 다 필요하다.)
3. **지도 높이 0** — `maplibre-gl.css`가 컨테이너를 `position: relative`로 덮어써 `.map { position: absolute; inset: 0 }`이 무효가 된다. → `index.css`에서 `.map-area .map`으로 선택자 우선순위를 높인다.
