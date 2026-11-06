# API contract (v1, finalized 2026-11-06; summary precision, forecast hours and error codes revised after the pre-deployment review)

[한국어](./api-contract.ko.md)

The format exchanged between the backend (Django) and the frontend (React). The rules come from `CLAUDE.md` (cited by section number), and the types in `frontend/src/types/api.ts` carry the same content. If the two disagree, this document wins.

## Common rules

- All times are **ISO 8601 UTC** (`2026-11-09T14:00:00Z`). The frontend converts them for display.
- Coordinate arrays are `[lon, lat]` (GeoJSON order); objects use `{ lat, lon }`.
- Distance is in **miles**, time is in **minutes** (integer), wind speed in mph, rain and snow in in/hr.
- Risk level strings: `low` `moderate` `high` `severe` `no_travel`. The whole part of a heatmap score (`0` to `4`) is the level, in the same order.
- The recommendation compares **unrounded** values (CLAUDE.md section 5); rounding is for display only. The summary carries miles with 2 decimals and `avg_risk` with 4, so that the screen can show a difference the comparison was decided on, and so that an amount above zero never arrives as `0`. Travel time is compared in whole minutes, as it is shown.
- The backend does not write the recommendation reason sentence. It sends structured values only, and the frontend builds the sentence **in English**.
- UI text is English. Error `message` is also English and is written as a sentence that can be shown on screen as is.

## Endpoints

Route/checkpoint calculation and the heatmap are independent, so they are **split into two endpoints**. This lets the route results appear first and the heatmap fill in afterwards (perceived UI speed). Both endpoints take **the same request body**, and the TomTom route response is cached per request so the second call does not call TomTom again.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/analyze` | 3 routes, checkpoints, risk summary, recommendation |
| `POST` | `/api/heatmap` | 0–48 hour weather scores on a grid around the routes |
| `GET` | `/api/places?q=` | Up to 5 places, addresses and cities for the text being typed (the From / To list) |
| `GET` | `/api/places/reverse?lat=&lon=` | The address at a position (the "my location" button) |

### Request body (shared)

```json
{
  "origin": "Chicago, IL",
  "destination": "Denver, CO",
  "departure": "2026-11-09T14:00:00Z",
  "load_weight_lb": 42000,
  "interval_miles": 25
}
```

| Field | Format | Rules |
|---|---|---|
| `origin`, `destination` | string **or** place | A **string** is typed text: the server takes the first result of TomTom Fuzzy Search for it (`countrySet=US`; it finds addresses, cities and named places such as "Willis Tower, Chicago"). Not empty, at most 200 characters; runs of spaces, tabs and line breaks become one space, and control characters are refused. A **place** `{ "label": "...", "lat": 41.8789, "lon": -87.6359 }` is a choice from the list (or "my location"): it is used as it is, with no lookup, so the position cannot change between choosing and routing (`label` as a string above; `lat` and `lon` finite numbers **inside the United States**: a coarse box of latitude 18 to 72 and longitude -180 to -66, which holds the 50 states and Puerto Rico. A place outside it is refused with `INVALID_INPUT` on that field, because the place search is US only and a request built by hand must not get around that). The two ends can be mixed. If both resolve to the same place the request is refused (`INVALID_INPUT`, `field: destination`) |
| `departure` | ISO 8601 **with a time zone** | **Must not be in the past**; a departure up to 5 minutes ago is accepted, because a form that says "now" is already a few seconds old when it arrives. A date before 2100 (this only keeps date arithmetic safe; the forecast is the real limit). If the needed hours run past the end of the forecast, `FORECAST_OUT_OF_RANGE` (see CLAUDE.md section 7) |
| `load_weight_lb` | number | 0 to 1,000,000. Used in lb as given for the rules, and converted to kg for TomTom |
| `interval_miles` | `10` \| `25` \| `50` | Only these three values are allowed (the frontend fills in 25 as the default) |

### `POST /api/analyze` response (200)

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

- `routes` holds exactly the **N (1 to 3)** routes TomTom returned. Fewer than 3 is not an error (CLAUDE.md Step 1 policy). The frontend tells the user the count is reduced.
- `geometry` is the route line **simplified for display**. Distance, time, and mile calculations use TomTom's original points (about 10,000 points per route, CLAUDE.md section 7).
- `segments` are pieces of `geometry` cut where the risk level changes, for coloring. The boundaries are the **midpoints** between adjacent checkpoints (the same as the miles-per-level definition in CLAUDE.md section 5). Neighbouring stretches with the same level are one segment. Joined together (each shared cut point once) they form `geometry`.
- **Rounding happens only in the response:** coordinates to 5 decimals (about 1 m), `mile` and `represents_miles` to 2 decimals, times to the second. `weather` values are as the forecast gave them. In the summary, `miles_by_level`, `severe_miles` and `high_miles` have 2 decimals and `avg_risk` has 4 (rounded half up; **an amount above 0 is never sent as 0**, it is sent as the smallest step instead, so a level that is present never reads as absent); `distance_miles` and `duration_minutes` are whole numbers. The recommendation was made on the unrounded values, so two routes whose numbers read alike here can still be ranked by them (see `decided_by`).
- `checkpoints[].mile` is the cumulative miles from the origin, and `represents_miles` is the stretch length that checkpoint stands for. The `represents_miles` of one route sum to `distance_miles`.
- `weather.wind_mph` is the forecast for the **hour nearest to `eta`** (:30 goes to the later hour). `rain_in_hr` and `snow_in_hr` are those of the **hour that contains `eta`**: the forecast gives rain and snow as the sum over the hour that ends at its time, so for an `eta` of 12:20 they are the 13:00 values, the rain that falls from 12:00 to 13:00 (CLAUDE.md section 7).
- `level_by` is the base level for each of wind, rain, and snow; `level` is the final level after applying the load rules to the highest of them; `load_escalated` says whether a load rule raised the level.
- The values in `miles_by_level` add up to the route's length; `distance_miles` is that length as a whole number, so the two agree within rounding.
- A route with `has_no_travel` set to `true` is excluded from the recommendation and listed in `excluded_route_ids`.

**`recommendation` fields**

| Field | Description |
|---|---|
| `route_id` | The recommended route. **`null` if every route has No Travel** |
| `decided_by` | The first criterion, in the order of CLAUDE.md section 5, on which the recommended route differs from **the runner-up** (not from every other route): `severe_miles` \| `high_miles` \| `avg_risk` \| `duration` \| `only_candidate` (only one candidate). The first three are compared unrounded, `duration` in whole minutes. If two routes tie on all four criteria, `duration`. `null` when `route_id` is `null` |
| `versus_route_id` | The route compared against (the runner-up). `null` when there is only one candidate |
| `duration_delta_minutes` | The recommended route's travel time minus the compared route's (positive means slower). `null` when `versus_route_id` is `null` |
| `excluded_route_ids` | Routes excluded because of No Travel |
| `ranking` | The non-excluded routes, from 1st place down |

Example: if Route B has 60.3 severe miles, the values above are shown in the UI as "Fewer severe miles than Route B (25 vs 60), 20 min slower than Route B." The sentence compares with the runner-up only (it never says "fewest"), and shows as few decimals as tell the two values apart: 24.6 against 25.4 reads "24.6 vs 25.4", not "25 vs 25".

### `POST /api/heatmap` response (200)

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

- `start` is slider hour 0 = **the departure time rounded to the nearest hour** (a time exactly on :30 goes to the later hour), the rule checkpoints use for wind (CLAUDE.md sections 2 and 7). At slider hour `h` the wind is the value at that hour and rain and snow are the sums of the hour before it, as the forecast gives them. So a checkpoint reached at 12:20 has the wind the heatmap shows at 12:00 and the rain and snow it shows at 13:00. `hours` is `49` (hours 0 to 48): `scores[h]` is the forecast `h` hours after `start`.
- `points` are grid points `[lon, lat]` on exact multiples of `spacing_deg`, within 40 miles of any of the routes (CLAUDE.md section 7). `spacing_deg` is `0.5` (about 34 miles); a trip that would need more than 600 points gets `1.0` or `2.0` instead, so one heatmap never costs more than 600 weather calls.
- `scores[h][i]` is how bad the weather is at point `i` at hour `h`, from `0` (calm) to `4` (No Travel), with 2 decimals. **The whole part is the risk level** by the same rules as checkpoints (load rules included), so the heatmap uses the same levels and colors as the routes: score 2.5 is High, 3.0 is Severe, 4 is No Travel. (At one place the two can still differ: a checkpoint is the weather when the truck gets there, at its exact position; the heatmap is the weather at the slider's hour on a grid about 34 miles wide.) The decimals are how far through the level the weather is. Why not just the level: on a calm day almost every point is Low, and a map of five levels cannot show the weather changing. The score places the worst of wind, rain and snow between its table thresholds (wind 12.5 mph is 0.5, 25 mph is 1.0, 30 mph is 1.5, 35 mph is 2.0, and so on); a load rule that raises the level lifts the score to the start of that level. The score is only for drawing; the level and its rules decide everything else (CLAUDE.md sections 3 and 4).
- Points and hours that contain `null` are not produced; they are treated as errors (CLAUDE.md section 7).

### `GET /api/places?q=willis tow` response (200)

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

- At most 5 choices, in TomTom's order, US only. `kind` is `place` (a building, a station ...), `address`, or `area` (a city, a neighbourhood). `name` is the main line of the list and `detail` the line under it (the address); `label` is the whole text put in the input when chosen, and `lat` / `lon` (5 decimals) are what the request then carries as a **place**.
- The same place listed several times a few meters apart is shown once (same name and same detail).
- `q` is required (not empty, at most 200 characters). Fewer than 3 characters is **not an error**: the answer is an empty list and TomTom is not called. No match is also an empty list, and so is a text TomTom cannot search for (it answers HTTP 400 to a text like `%%%`). The frontend searches from 3 characters, after a 250 ms pause. Answers are cached for an hour per text (case and extra spaces ignored).
- Errors: 400 `INVALID_INPUT` (missing or too long `q`, control characters), 429 `RATE_LIMITED`, 502 `ROUTING_UNAVAILABLE`.

### `GET /api/places/reverse?lat=41.8789&lon=-87.6359` response (200)

```json
{ "place": { "label": "217 South Wacker Drive, Chicago, IL 60606", "lat": 41.8789, "lon": -87.6359 } }
```

- The address within 1 km of the position (TomTom reverse geocoding). `lat` / `lon` are the position that was asked for (5 decimals), not the address's own, so the route starts where the user is. Cached 24 hours per position rounded to 4 decimals (about 10 m).
- Errors: 400 `INVALID_INPUT` (missing or out-of-range `lat` / `lon`); 422 `GEOCODE_NOT_FOUND` **without `field`** when the position is outside the United States or has no address nearby (the message says routes are US only); 429 `RATE_LIMITED`; 502 `ROUTING_UNAVAILABLE`.

## Errors (see CLAUDE.md section 7)

All errors share one format, and **every answer of the API is JSON**: an unknown path, a wrong method, a body that cannot be read and a failure nobody foresaw all answer in this shape, never with an HTML page. (With `DJANGO_DEBUG=1`, as in local development, an unknown path outside the API views shows Django's own debug page.)

```json
{ "error": { "code": "GEOCODE_NOT_FOUND", "message": "...", "field": "origin" } }
```

| HTTP | `code` | Situation | Extra field |
|---|---|---|---|
| 400 | `INVALID_INPUT` | Missing field, wrong format, a disallowed `interval_miles`, a number that is not finite (a 400-digit integer included), control characters in a text, a chosen place outside the United States, origin and destination being the same place, or a body that is not a JSON object, is not valid JSON, is nested too deeply or is too large. Also used for a wrong HTTP method (405) or media type (415) | `field` (omitted when it concerns the whole body) |
| 400 | `DEPARTURE_IN_PAST` | The departure time is in the past | `field` (`departure`) |
| 404 | `NOT_FOUND` | There is nothing at this path | |
| 422 | `GEOCODE_NOT_FOUND` | The address could not be turned into coordinates; or (`/api/places/reverse`) the position is outside the US or has no address | `field` (`origin`/`destination`; omitted for a position) |
| 422 | `NO_ROUTE` | TomTom returned no route at all, or an end point is not near a road | |
| 422 | `FORECAST_OUT_OF_RANGE` | The needed hours run past the end of the forecast | `forecast_end` (ISO, the last hour that has a forecast; omitted when it could not be determined) |
| 429 | `RATE_LIMITED` | Too many requests from this client address (see below). The message says how long to wait, and the `Retry-After` header carries the same number | `retry_after_seconds` (omitted when unknown) |
| 500 | `INTERNAL_ERROR` | A failure that is none of the above. The server logs it with its traceback; the message tells the user nothing about the server | |
| 502 | `ROUTING_UNAVAILABLE` | TomTom error or timeout, or a route from TomTom that is not consistent (for example guidance points that go backwards); such an answer is not cached | |
| 502 | `WEATHER_UNAVAILABLE` | Open-Meteo error, timeout, or a `null` value | |

**Request limits.** Every analysis spends free-tier quota that all visitors share (one TomTom routing call, and one Open-Meteo call per checkpoint and per heatmap point), so requests are limited per client address: `/api/analyze` and `/api/heatmap` together **12 a minute and 120 a day** (one analysis on screen is one of each, so 6 analyses a minute and 60 a day), `/api/places` and `/api/places/reverse` together **90 a minute and 1,500 a day**. A request that is refused calls no outside service. The numbers are `RATE_LIMITS` in `backend/config/settings.py`; behind a proxy the client address comes from `X-Forwarded-For`, which needs `DJANGO_NUM_PROXIES` (CLAUDE.md Step 12).

When every route has No Travel it is **not an error.** Respond `200` with `recommendation.route_id: null` and the frontend shows a large warning banner.
