# API 계약 (v1, 2026-11-06 확정. 배포 전 검수 뒤 요약 숫자의 자릿수, 예보 시각 규칙, 오류 코드를 고침)

[English](./api-contract.md) · 영문 `api-contract.md`의 한국어판입니다. 영문이 기준입니다.

백엔드(Django)와 프론트엔드(React)가 주고받는 형식이다. 규칙의 근거는 `CLAUDE.md`(절 번호로 표기)이고, 타입은 `frontend/src/types/api.ts`에 같은 내용으로 둔다. 둘이 어긋나면 이 문서가 기준이다.

## 공통 규칙

- 모든 시각은 **ISO 8601 UTC**(`2026-11-09T14:00:00Z`). 표시용 변환은 프론트가 한다.
- 좌표 배열은 `[lon, lat]`(GeoJSON 순서), 객체는 `{ lat, lon }`.
- 거리는 **마일**, 시간은 **분**(정수), 풍속은 mph, 강우·강설은 in/hr.
- 위험 등급 문자열: `low` `moderate` `high` `severe` `no_travel`. heatmap 점수의 정수 부분(`0`~`4`)이 등급이고, 같은 순서다.
- 추천은 **반올림하지 않은** 값으로 비교한다(CLAUDE.md 5절). 반올림은 표시용일 뿐이다. 요약은 마일을 소수 2자리, `avg_risk`를 소수 4자리로 보낸다. 비교를 가른 차이를 화면이 보여 줄 수 있어야 하고, 0보다 큰 양이 `0`으로 도착해서는 안 되기 때문이다. 소요 시간은 화면에 보이는 대로 분 단위로 비교한다.
- 추천 이유 문장은 백엔드가 만들지 않는다. 구조화된 값만 주고 문장은 프론트가 **영어로** 만든다.
- UI 문구는 영어다. 오류 `message`도 영어이며 화면에 그대로 표시할 수 있는 문장으로 쓴다.

## 엔드포인트

경로·checkpoint 계산과 heatmap은 서로 독립이라 **둘로 나눈다.** 경로 결과를 먼저 보여 주고 heatmap은 뒤따라 채우기 위해서다(UI 체감 속도). 두 엔드포인트는 **같은 요청 본문**을 받고, TomTom 경로 응답은 요청 단위로 캐시해 두 번째 호출이 TomTom을 다시 부르지 않게 한다.

| 메서드 | 경로 | 용도 |
|---|---|---|
| `POST` | `/api/analyze` | 경로 3개, checkpoint, 위험 요약, 추천 |
| `POST` | `/api/heatmap` | 경로 주변 격자의 0~48시간 날씨 점수 |
| `GET` | `/api/places?q=` | 입력 중인 글자에 맞는 장소·주소·도시 최대 5개(From / To 목록) |
| `GET` | `/api/places/reverse?lat=&lon=` | 위치의 주소("내 위치" 버튼) |

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
| `origin`, `destination` | 문자열 **또는** 장소 | **문자열**은 입력한 글자다: 서버가 TomTom Fuzzy Search의 첫 결과를 쓴다(`countrySet=US`. 주소, 도시, "Willis Tower, Chicago" 같은 장소 이름을 찾는다). 비어 있으면 안 되고 200자 이하. 연속된 공백·탭·줄바꿈은 공백 하나로 바꾸고, 제어 문자는 거부한다. **장소** `{ "label": "...", "lat": 41.8789, "lon": -87.6359 }`는 목록에서 고른 것(또는 "내 위치")이다: 조회 없이 그대로 쓰므로 고른 뒤 경로를 구할 때까지 위치가 바뀌지 않는다(`label`은 위 문자열과 같은 규칙, `lat`과 `lon`은 **미국 안**의 유한한 숫자: 위도 18~72, 경도 -180~-66의 넉넉한 사각형으로, 50개 주와 푸에르토리코가 들어간다. 그 밖의 장소는 해당 필드의 `INVALID_INPUT`으로 거부한다. 장소 검색이 미국 전용인데 손으로 만든 요청이 이를 우회해서는 안 되기 때문이다). 두 끝을 섞어 쓸 수 있다. 둘이 같은 장소로 확인되면 거부한다(`INVALID_INPUT`, `field: destination`) |
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
        "miles_by_level": { "low": 790.12, "moderate": 130.4, "high": 60.61, "severe": 24.87, "no_travel": 0 },
        "severe_miles": 24.87,
        "high_miles": 60.61,
        "avg_risk": 0.3243,
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
- **반올림은 응답을 만들 때만 한다:** 좌표는 소수 5자리(약 1 m), `mile`과 `represents_miles`는 소수 2자리, 시각은 초 단위. `weather` 값은 예보가 준 그대로다. 요약에서 `miles_by_level`, `severe_miles`, `high_miles`는 소수 2자리, `avg_risk`는 소수 4자리다(5 이상 올림. **0보다 큰 양은 0으로 보내지 않고** 가장 작은 단위로 보낸다. 있는 등급이 없는 것처럼 읽히지 않게 하기 위해서다). `distance_miles`와 `duration_minutes`는 정수다. 추천은 반올림하지 않은 값으로 정했으므로, 여기서 같아 보이는 두 경로도 그 값으로 순위가 갈릴 수 있다(`decided_by` 참고).
- `checkpoints[].mile`은 출발지부터의 누적 마일, `represents_miles`는 그 checkpoint가 대표하는 구간 길이. 한 경로의 `represents_miles` 합은 `distance_miles`와 같다.
- `weather.wind_mph`는 **`eta`에 가장 가까운 정시**의 예보다(:30은 늦은 쪽). `rain_in_hr`과 `snow_in_hr`은 **`eta`를 포함하는 한 시간**의 값이다: 예보는 비와 눈을 그 시각에 끝나는 한 시간의 합계로 주므로, `eta`가 12:20이면 13:00 값, 곧 12:00부터 13:00까지 내리는 양이다(CLAUDE.md 7절).
- `level_by`는 풍속·강우·강설 각각의 기본 등급, `level`은 최고 등급에 적재 규칙을 적용한 최종 등급, `load_escalated`는 적재 규칙이 등급을 올렸는지.
- `miles_by_level`을 모두 더하면 경로의 길이다. `distance_miles`는 그 길이를 정수로 나타낸 값이라, 둘은 반올림 범위 안에서 일치한다.
- `has_no_travel`이 `true`인 경로는 추천에서 제외되고 `excluded_route_ids`에 들어간다.

**`recommendation` 필드**

| 필드 | 설명 |
|---|---|
| `route_id` | 추천 경로. **모든 경로가 No Travel이면 `null`** |
| `decided_by` | CLAUDE.md 5절의 순서에서 추천 경로가 **2위 경로**와(다른 모든 경로가 아니라) 처음으로 달라지는 기준: `severe_miles` \| `high_miles` \| `avg_risk` \| `duration` \| `only_candidate`(후보가 1개뿐). 앞의 셋은 반올림하지 않고, `duration`은 분 단위로 비교한다. 두 경로가 네 기준 모두 같으면 `duration`. `route_id`가 `null`이면 `null` |
| `versus_route_id` | 비교 대상(차순위 경로). 후보가 1개면 `null` |
| `duration_delta_minutes` | 추천 경로의 이동 시간 − 비교 대상의 이동 시간(양수면 더 느림). `versus_route_id`가 `null`이면 `null` |
| `excluded_route_ids` | No Travel 때문에 제외된 경로 |
| `ranking` | 제외되지 않은 경로를 1순위부터 나열 |

예: Route B의 Severe 마일이 60.3이면, 위 값은 UI에서 "Fewer severe miles than Route B (25 vs 60), 20 min slower than Route B."로 표시된다. 문장은 2위 경로와만 비교하고("fewest"라고 쓰지 않는다), 두 값을 구별할 수 있는 최소한의 소수 자리만 보여 준다: 24.6과 25.4는 "25 vs 25"가 아니라 "24.6 vs 25.4"로 쓴다.

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

- `start`는 슬라이더 0시간 = **출발 시각을 가장 가까운 정시로 맞춘 값**(정확히 :30이면 늦은 쪽)이다. checkpoint가 풍속에 쓰는 규칙과 같다(CLAUDE.md 2·7절). 슬라이더 `h`시간의 풍속은 그 시각의 값이고, 비와 눈은 예보가 주는 대로 그 앞 한 시간의 합계다. 그래서 12:20에 도착하는 checkpoint의 풍속은 heatmap이 12:00에 보여 주는 값이고, 비와 눈은 13:00에 보여 주는 값이다. `hours`는 `49`(0~48시간)이고 `scores[h]`는 `start`로부터 `h`시간 뒤의 예보다.
- `points`는 `spacing_deg`의 정확한 배수 위에 있고 어느 경로에서든 40마일 이내인 격자 지점 `[lon, lat]`이다(CLAUDE.md 7절). `spacing_deg`는 `0.5`(약 34마일)이며, 600개를 넘는 여행은 `1.0` 또는 `2.0`으로 거칠게 해서 heatmap 한 번이 날씨 호출 600건을 넘지 않게 한다.
- `scores[h][i]`는 `h`시간째 `i`번 지점의 날씨가 얼마나 나쁜지를 `0`(잔잔함)~`4`(No Travel)로, 소수 둘째 자리까지 나타낸다. **정수 부분이 위험 등급**이다(checkpoint와 같은 규칙, 적재 규칙 포함). 그래서 heatmap은 경로와 같은 등급과 색을 쓴다: 점수 2.5는 High, 3.0은 Severe, 4는 No Travel. (같은 장소에서도 둘이 다를 수는 있다: checkpoint는 트럭이 그곳에 도착할 때 그 정확한 위치의 날씨이고, heatmap은 슬라이더 시각의 날씨를 약 34마일 간격의 격자로 나타낸 것이다.) 소수 부분은 그 등급 안에서 얼마나 진행됐는지다. 등급만 쓰지 않는 이유: 잔잔한 날에는 거의 모든 지점이 Low라서 5단계 등급 지도로는 날씨가 변하는 것이 보이지 않는다. 점수는 풍속·강우·강설 중 가장 나쁜 것을 표의 임계값 사이에 비례해 놓는다(풍속 12.5 mph는 0.5, 25 mph는 1.0, 30 mph는 1.5, 35 mph는 2.0 …). 적재 규칙이 등급을 올리면 점수는 그 등급의 시작점으로 올라간다. 점수는 그리기 전용이고, 나머지 모든 것은 등급과 그 규칙이 결정한다(CLAUDE.md 3·4절).
- `null`이 있는 지점·시간은 만들지 않고 오류로 처리한다(CLAUDE.md 7절).

### `GET /api/places?q=willis tow` 응답 (200)

```json
{
  "suggestions": [
    {
      "id": "A1b2...",
      "kind": "place",
      "name": "Willis Tower",
      "detail": "233 South Wacker Drive, Chicago, IL 60606",
      "label": "Willis Tower, 233 South Wacker Drive, Chicago, IL 60606",
      "lat": 41.87888,
      "lon": -87.63591
    }
  ]
}
```

- 최대 5개, TomTom의 순서, 미국만. `kind`는 `place`(건물·역 등), `address`, `area`(도시·동네). `name`은 목록의 주 줄, `detail`은 그 아래 줄(주소). `label`은 고를 때 입력창에 들어가는 전체 글자이고, `lat` / `lon`(소수 5자리)은 요청이 **장소**로 보내는 값이다.
- 몇 미터 간격으로 여러 번 나오는 같은 장소는 한 번만 보인다(이름과 detail이 같으면).
- `q`는 필수(비어 있으면 안 되고 200자 이하). 3자 미만은 **오류가 아니다**: 빈 목록을 돌려주고 TomTom을 부르지 않는다. 일치하는 것이 없어도 빈 목록이고, TomTom이 검색하지 못하는 글자(`%%%` 같은 글자에는 HTTP 400으로 답한다)도 빈 목록이다. 프론트는 3자부터, 입력이 250 ms 멈추면 검색한다. 답은 글자(대소문자·여분의 공백 무시)별로 1시간 캐시한다.
- 오류: 400 `INVALID_INPUT`(`q` 없음, 너무 긺, 제어 문자), 429 `RATE_LIMITED`, 502 `ROUTING_UNAVAILABLE`.

### `GET /api/places/reverse?lat=41.8789&lon=-87.6359` 응답 (200)

```json
{ "place": { "label": "217 South Wacker Drive, Chicago, IL 60606", "lat": 41.8789, "lon": -87.6359 } }
```

- 위치에서 1 km 이내의 주소(TomTom 역지오코딩). `lat` / `lon`은 주소의 좌표가 아니라 요청한 위치(소수 5자리)라서, 경로가 사용자가 있는 곳에서 시작한다. 소수 4자리(약 10 m)로 반올림한 위치별로 24시간 캐시한다.
- 오류: 400 `INVALID_INPUT`(`lat` / `lon` 없음 또는 범위 밖), 422 `GEOCODE_NOT_FOUND`(**`field` 없음**: 위치가 미국 밖이거나 근처에 주소가 없음. 메시지가 미국에서만 경로를 구한다고 알려 준다), 429 `RATE_LIMITED`, 502 `ROUTING_UNAVAILABLE`.

## 오류 (7절)

모든 오류는 같은 형식이고, **API의 모든 응답은 JSON이다**: 없는 경로, 잘못된 메서드, 읽을 수 없는 본문, 예상하지 못한 실패도 이 형식으로 답하며 HTML 페이지를 보내지 않는다. (로컬 개발처럼 `DJANGO_DEBUG=1`이면 API 뷰 밖의 없는 경로는 Django의 디버그 페이지를 보여 준다.)

```json
{ "error": { "code": "GEOCODE_NOT_FOUND", "message": "...", "field": "origin" } }
```

| HTTP | `code` | 상황 | 추가 필드 |
|---|---|---|---|
| 400 | `INVALID_INPUT` | 필드 누락·형식 오류·허용되지 않은 `interval_miles`·유한하지 않은 숫자(400자리 정수 포함)·글자 속 제어 문자·미국 밖의 고른 장소·출발지와 도착지가 같은 장소, 또는 본문이 JSON 객체가 아니거나, 올바른 JSON이 아니거나, 너무 깊게 중첩됐거나, 너무 큼. 잘못된 HTTP 메서드(405)와 미디어 타입(415)에도 쓴다 | `field` (본문 전체에 대한 오류면 생략) |
| 400 | `DEPARTURE_IN_PAST` | 출발 시각이 과거 | `field` (`departure`) |
| 404 | `NOT_FOUND` | 이 경로에는 아무것도 없음 | |
| 422 | `GEOCODE_NOT_FOUND` | 주소를 좌표로 바꾸지 못함. 또는(`/api/places/reverse`) 위치가 미국 밖이거나 주소가 없음 | `field`(`origin`/`destination`. 위치일 때는 생략) |
| 422 | `NO_ROUTE` | TomTom이 경로를 하나도 주지 않음, 또는 출발·도착 지점이 도로 근처가 아님 | |
| 422 | `FORECAST_OUT_OF_RANGE` | 필요한 시간이 예보 끝을 넘음 | `forecast_end`(ISO, 예보가 있는 마지막 시각. 알아내지 못하면 생략) |
| 429 | `RATE_LIMITED` | 이 클라이언트 주소의 요청이 너무 많음(아래 참고). 메시지가 얼마나 기다려야 하는지 알려 주고, `Retry-After` 헤더에 같은 숫자가 있다 | `retry_after_seconds`(알 수 없으면 생략) |
| 500 | `INTERNAL_ERROR` | 위의 어느 것도 아닌 실패. 서버가 traceback과 함께 기록하고, 메시지는 서버에 대해 아무것도 알려 주지 않는다 | |
| 502 | `ROUTING_UNAVAILABLE` | TomTom 오류·시간 초과, 또는 TomTom이 준 경로가 일관되지 않음(예: 안내 지점이 뒤로 감). 그런 응답은 캐시하지 않는다 | |
| 502 | `WEATHER_UNAVAILABLE` | Open-Meteo 오류·시간 초과·`null` 값 | |

**요청 제한.** 분석 한 번은 모든 방문자가 함께 쓰는 무료 할당량을 쓴다(TomTom 경로 호출 1건, checkpoint와 heatmap 지점마다 Open-Meteo 호출 1건). 그래서 클라이언트 주소별로 요청을 제한한다: `/api/analyze`와 `/api/heatmap`을 합쳐 **분당 12건, 하루 120건**(화면의 분석 한 번이 각각 1건씩이므로 분당 6회, 하루 60회 분석), `/api/places`와 `/api/places/reverse`를 합쳐 **분당 90건, 하루 1,500건**. 거부된 요청은 외부 서비스를 부르지 않는다. 숫자는 `backend/config/settings.py`의 `RATE_LIMITS`에 있다. 프록시 뒤에서는 클라이언트 주소를 `X-Forwarded-For`에서 읽으므로 `DJANGO_NUM_PROXIES`가 필요하다(CLAUDE.md Step 12).

모든 경로가 No Travel인 경우는 **오류가 아니다.** `200`에 `recommendation.route_id: null`로 응답하고 프론트가 경고 배너를 크게 띄운다.
