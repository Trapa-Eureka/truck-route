# API 계약 (v1, 2026-11-06 확정)

[English](./api-contract.md) · 영문 `api-contract.md`의 한국어판입니다. 영문이 기준입니다.

백엔드(Django)와 프론트엔드(React)가 주고받는 형식이다. 규칙의 근거는 `CLAUDE.md`(절 번호로 표기)이고, 타입은 `frontend/src/types/api.ts`에 같은 내용으로 둔다. 둘이 어긋나면 이 문서가 기준이다.

## 공통 규칙

- 모든 시각은 **ISO 8601 UTC**(`2026-11-09T14:00:00Z`). 표시용 변환은 프론트가 한다.
- 좌표 배열은 `[lon, lat]`(GeoJSON 순서), 객체는 `{ lat, lon }`.
- 거리는 **마일**, 시간은 **분**(정수), 풍속은 mph, 강우·강설은 in/hr.
- 위험 등급 문자열: `low` `moderate` `high` `severe` `no_travel`. heatmap의 정수 등급은 `0`~`4`가 같은 순서다.
- 화면에 표시하는 값과 추천 비교에 쓰는 값은 **같은 반올림 값**이다(CLAUDE.md 5절): 마일은 정수, `avg_risk`는 소수 둘째 자리, 시간은 분.
- 추천 이유 문장은 백엔드가 만들지 않는다. 구조화된 값만 주고 문장은 프론트가 **영어로** 만든다.
- UI 문구는 영어다. 오류 `message`도 영어이며 화면에 그대로 표시할 수 있는 문장으로 쓴다.

## 엔드포인트

경로·checkpoint 계산과 heatmap은 서로 독립이라 **둘로 나눈다.** 경로 결과를 먼저 보여 주고 heatmap은 뒤따라 채우기 위해서다(UI 체감 속도). 두 엔드포인트는 **같은 요청 본문**을 받고, TomTom 경로 응답은 요청 단위로 캐시해 두 번째 호출이 TomTom을 다시 부르지 않게 한다.

| 메서드 | 경로 | 용도 |
|---|---|---|
| `POST` | `/api/analyze` | 경로 3개, checkpoint, 위험 요약, 추천 |
| `POST` | `/api/heatmap` | 경로 주변 격자의 0~48시간 위험 등급 |

### 요청 본문 (공통)

```json
{
  "origin": "Chicago, IL",
  "destination": "Denver, CO",
  "departure": "2026-11-09T14:00:00Z",
  "load_weight_lb": 42000,
  "interval_miles": 25
}
```

| 필드 | 형식 | 규칙 |
|---|---|---|
| `origin`, `destination` | 문자열 | 서버가 지오코딩한다(`countrySet=US`, 첫 결과). 비어 있으면 안 되고 200자 이하. 둘이 같은 장소로 확인되면 거부한다(`INVALID_INPUT`, `field: destination`) |
| `departure` | ISO 8601 (**시간대 포함**) | **과거 불가**. 단 5분 전까지는 받는다(폼의 "지금"은 서버에 닿을 때 이미 몇 초 지나 있다). 2100년 이전 날짜(날짜 계산이 넘치지 않게 하는 용도일 뿐, 실제 한계는 예보다). 필요한 시간이 예보 끝을 넘으면 `FORECAST_OUT_OF_RANGE` (7절) |
| `load_weight_lb` | 숫자 | 0 이상 1,000,000 이하. lb 단위 그대로 규칙에 쓰고, TomTom에는 kg으로 변환해 전달 |
| `interval_miles` | `10` \| `25` \| `50` | 이 세 값만 허용 (기본값은 프론트가 25로 채움) |

### `POST /api/analyze` 응답 (200)

```json
{
  "origin":      { "query": "Chicago, IL", "label": "Chicago, IL", "lat": 41.883229, "lon": -87.632398 },
  "destination": { "query": "Denver, CO",  "label": "Denver, CO",  "lat": 39.738453, "lon": -104.984853 },
  "routes": [
    {
      "id": "A",
      "summary": {
        "distance_miles": 1006,
        "duration_minutes": 846,
        "arrival": "2026-11-10T04:06:00Z",
        "miles_by_level": { "low": 790, "moderate": 130, "high": 61, "severe": 25, "no_travel": 0 },
        "severe_miles": 25,
        "high_miles": 61,
        "avg_risk": 0.33,
        "has_no_travel": false
      },
      "geometry": [[-87.6324, 41.88323], [-87.63241, 41.8835]],
      "segments": [
        { "level": "low", "coordinates": [[-87.6324, 41.88323], [-87.63241, 41.8835]] }
      ],
      "checkpoints": [
        {
          "index": 0,
          "mile": 0,
          "lat": 41.88323,
          "lon": -87.6324,
          "eta": "2026-11-09T14:00:00Z",
          "represents_miles": 12.5,
          "weather": { "wind_mph": 12.3, "rain_in_hr": 0.0, "snow_in_hr": 0.0 },
          "level_by": { "wind": "low", "rain": "low", "snow": "low" },
          "level": "low",
          "load_escalated": false
        }
      ]
    }
  ],
  "recommendation": {
    "route_id": "A",
    "decided_by": "severe_miles",
    "versus_route_id": "B",
    "duration_delta_minutes": 20,
    "excluded_route_ids": [],
    "ranking": ["A", "B", "C"]
  }
}
```

- `routes`는 TomTom이 준 **N개(1~3)** 그대로다. 3개 미만이어도 오류가 아니다(CLAUDE.md 1단계 방침). 프론트는 개수가 줄었음을 알린다.
- `geometry`는 **화면 표시용으로 단순화**한 경로선이다. 거리·시간·마일 계산은 TomTom 원본 점으로 한다(원본은 경로당 약 1만 점, CLAUDE.md 7절).
- `segments`는 `geometry`를 위험 등급이 바뀌는 지점에서 잘라 색칠하기 위한 조각이다. 경계는 인접 checkpoint의 **중간 지점**(CLAUDE.md 5절의 구간 마일 정의와 같음)이다. 이웃한 같은 등급 구간은 하나의 조각이다. 이어 붙이면(공유하는 절단점은 한 번만) `geometry`가 된다.
- **반올림은 응답을 만들 때만 한다:** 좌표는 소수 5자리(약 1 m), `mile`과 `represents_miles`는 소수 2자리, 시각은 초 단위. `weather` 값은 예보가 준 그대로다. 요약 숫자는 추천이 비교하는 바로 그 반올림 값이다.
- `checkpoints[].mile`은 출발지부터의 누적 마일, `represents_miles`는 그 checkpoint가 대표하는 구간 길이. 한 경로의 `represents_miles` 합은 `distance_miles`와 같다.
- `level_by`는 풍속·강우·강설 각각의 기본 등급, `level`은 최고 등급에 적재 규칙을 적용한 최종 등급, `load_escalated`는 적재 규칙이 등급을 올렸는지.
- `miles_by_level`을 모두 더하면 `distance_miles`다(반올림 오차 범위 내).
- `has_no_travel`이 `true`인 경로는 추천에서 제외되고 `excluded_route_ids`에 들어간다.

**`recommendation` 필드**

| 필드 | 설명 |
|---|---|
| `route_id` | 추천 경로. **모든 경로가 No Travel이면 `null`** |
| `decided_by` | 다른 경로를 이긴 기준: `severe_miles` \| `high_miles` \| `avg_risk` \| `duration` \| `only_candidate`(후보가 1개뿐). 두 경로가 네 기준 모두 같으면 `duration`. `route_id`가 `null`이면 `null` |
| `versus_route_id` | 비교 대상(차순위 경로). 후보가 1개면 `null` |
| `duration_delta_minutes` | 추천 경로의 이동 시간 − 비교 대상의 이동 시간(양수면 더 느림). `versus_route_id`가 `null`이면 `null` |
| `excluded_route_ids` | No Travel 때문에 제외된 경로 |
| `ranking` | 제외되지 않은 경로를 1순위부터 나열 |

예: 위 값은 UI에서 "25 severe miles, 20 min slower than Route B"로 표시된다.

### `POST /api/heatmap` 응답 (200)

```json
{
  "start": "2026-11-09T14:00:00Z",
  "hours": 49,
  "spacing_deg": 0.5,
  "points": [[-87.5, 41.5], [-87.0, 41.5]],
  "scores": [
    [0.34, 0.0],
    [1.5, 0.82]
  ]
}
```

- `start`는 슬라이더 0시간 = **출발 시각을 가장 가까운 정시로 맞춘 값**(정확히 :30이면 늦은 쪽)이다. checkpoint와 같은 규칙이라서 checkpoint와 heatmap이 같은 예보를 보여준다(CLAUDE.md 2·7절). `hours`는 `49`(0~48시간)이고 `scores[h]`는 `start`로부터 `h`시간 뒤의 예보다.
- `points`는 `spacing_deg`의 정확한 배수 위에 있고 어느 경로에서든 40마일 이내인 격자 지점 `[lon, lat]`이다(CLAUDE.md 7절). `spacing_deg`는 `0.5`(약 34마일)이며, 600개를 넘는 여행은 `1.0` 또는 `2.0`으로 거칠게 해서 heatmap 한 번이 날씨 호출 600건을 넘지 않게 한다.
- `scores[h][i]`는 `h`시간째 `i`번 지점의 날씨가 얼마나 나쁜지를 `0`(잔잔함)~`4`(No Travel)로, 소수 둘째 자리까지 나타낸다. **정수 부분이 위험 등급**이다(checkpoint와 같은 규칙, 적재 규칙 포함). 그래서 경로 색과 heatmap 색이 항상 일치한다: 점수 2.5는 High, 3.0은 Severe, 4는 No Travel. 소수 부분은 그 등급 안에서 얼마나 진행됐는지다. 등급만 쓰지 않는 이유: 잔잔한 날에는 거의 모든 지점이 Low라서 5단계 등급 지도로는 날씨가 변하는 것이 보이지 않는다. 점수는 풍속·강우·강설 중 가장 나쁜 것을 표의 임계값 사이에 비례해 놓는다(풍속 12.5 mph는 0.5, 25 mph는 1.0, 30 mph는 1.5, 35 mph는 2.0 …). 적재 규칙이 등급을 올리면 점수는 그 등급의 시작점으로 올라간다. 점수는 그리기 전용이고, 나머지 모든 것은 등급과 그 규칙이 결정한다(CLAUDE.md 3·4절).
- `null`이 있는 지점·시간은 만들지 않고 오류로 처리한다(CLAUDE.md 7절).

## 오류 (7절)

모든 오류는 같은 형식이다.

```json
{ "error": { "code": "GEOCODE_NOT_FOUND", "message": "...", "field": "origin" } }
```

| HTTP | `code` | 상황 | 추가 필드 |
|---|---|---|---|
| 400 | `INVALID_INPUT` | 필드 누락·형식 오류·허용되지 않은 `interval_miles`·JSON 객체가 아닌 본문·출발지와 도착지가 같은 장소. 잘못된 HTTP 메서드(405)에도 쓴다 | `field` (본문 전체에 대한 오류면 생략) |
| 400 | `DEPARTURE_IN_PAST` | 출발 시각이 과거 | |
| 422 | `GEOCODE_NOT_FOUND` | 주소를 좌표로 바꾸지 못함 | `field`(`origin`/`destination`) |
| 422 | `NO_ROUTE` | TomTom이 경로를 하나도 주지 않음, 또는 출발·도착 지점이 도로 근처가 아님 | |
| 422 | `FORECAST_OUT_OF_RANGE` | 필요한 시간이 예보 끝을 넘음 | `forecast_end`(ISO, 예보가 있는 마지막 시각. 알아내지 못하면 생략) |
| 502 | `ROUTING_UNAVAILABLE` | TomTom 오류·시간 초과 | |
| 502 | `WEATHER_UNAVAILABLE` | Open-Meteo 오류·시간 초과·`null` 값 | |

모든 경로가 No Travel인 경우는 **오류가 아니다.** `200`에 `recommendation.route_id: null`로 응답하고 프론트가 경고 배너를 크게 띄운다.
