# API contract (v1, finalized 2026-11-06)

[한국어](./api-contract.ko.md)

The format exchanged between the backend (Django) and the frontend (React). The rules come from `CLAUDE.md` (cited by section number), and the types in `frontend/src/types/api.ts` carry the same content. If the two disagree, this document wins.

## Common rules

- All times are **ISO 8601 UTC** (`2026-11-09T14:00:00Z`). The frontend converts them for display.
- Coordinate arrays are `[lon, lat]` (GeoJSON order); objects use `{ lat, lon }`.
- Distance is in **miles**, time is in **minutes** (integer), wind speed in mph, rain and snow in in/hr.
- Risk level strings: `low` `moderate` `high` `severe` `no_travel`. The heatmap's integer levels `0` to `4` are in the same order.
- The values shown on screen and the values used for the recommendation comparison are **the same rounded values** (CLAUDE.md section 5): miles as integers, `avg_risk` to 2 decimals, time in minutes.
- The backend does not write the recommendation reason sentence. It sends structured values only, and the frontend builds the sentence **in English**.
- UI text is English. Error `message` is also English and is written as a sentence that can be shown on screen as is.

## Endpoints

Route/checkpoint calculation and the heatmap are independent, so they are **split into two endpoints**. This lets the route results appear first and the heatmap fill in afterwards (perceived UI speed). Both endpoints take **the same request body**, and the TomTom route response is cached per request so the second call does not call TomTom again.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/analyze` | 3 routes, checkpoints, risk summary, recommendation |
| `POST` | `/api/heatmap` | 0–48 hour risk levels on a grid around the routes |

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
| `origin`, `destination` | string | Geocoded by the server (`countrySet=US`, first result). Not empty, at most 200 characters. If both resolve to the same place the request is refused (`INVALID_INPUT`, `field: destination`) |
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

- `routes` holds exactly the **N (1 to 3)** routes TomTom returned. Fewer than 3 is not an error (CLAUDE.md Step 1 policy). The frontend tells the user the count is reduced.
- `geometry` is the route line **simplified for display**. Distance, time, and mile calculations use TomTom's original points (about 10,000 points per route, CLAUDE.md section 7).
- `segments` are pieces of `geometry` cut where the risk level changes, for coloring. The boundaries are the **midpoints** between adjacent checkpoints (the same as the miles-per-level definition in CLAUDE.md section 5). Neighbouring stretches with the same level are one segment. Joined together (each shared cut point once) they form `geometry`.
- **Rounding happens only in the response:** coordinates to 5 decimals (about 1 m), `mile` and `represents_miles` to 2 decimals, times to the second. `weather` values are as the forecast gave them. The summary numbers are the rounded values the recommendation compares.
- `checkpoints[].mile` is the cumulative miles from the origin, and `represents_miles` is the stretch length that checkpoint stands for. The `represents_miles` of one route sum to `distance_miles`.
- `level_by` is the base level for each of wind, rain, and snow; `level` is the final level after applying the load rules to the highest of them; `load_escalated` says whether a load rule raised the level.
- The values in `miles_by_level` add up to `distance_miles` (within rounding error).
- A route with `has_no_travel` set to `true` is excluded from the recommendation and listed in `excluded_route_ids`.

**`recommendation` fields**

| Field | Description |
|---|---|
| `route_id` | The recommended route. **`null` if every route has No Travel** |
| `decided_by` | The criterion that beat the other routes: `severe_miles` \| `high_miles` \| `avg_risk` \| `duration` \| `only_candidate` (only one candidate). If two routes tie on all four criteria, `duration`. `null` when `route_id` is `null` |
| `versus_route_id` | The route compared against (the runner-up). `null` when there is only one candidate |
| `duration_delta_minutes` | The recommended route's travel time minus the compared route's (positive means slower). `null` when `versus_route_id` is `null` |
| `excluded_route_ids` | Routes excluded because of No Travel |
| `ranking` | The non-excluded routes, from 1st place down |

Example: the values above are shown in the UI as "25 severe miles, 20 min slower than Route B".

### `POST /api/heatmap` response (200)

```json
{
  "start": "2026-11-09T14:00:00Z",
  "hours": 49,
  "points": [[-87.5, 41.5], [-87.0, 41.5]],
  "levels": [
    [0, 0],
    [1, 0]
  ]
}
```

- `start` is slider hour 0 = **the departure time floored to the hour** (CLAUDE.md section 2). `hours` is `49` (hours 0 to 48).
- `points` are grid points `[lon, lat]` (0.5° spacing, 40 miles on each side of the union of the 3 routes, CLAUDE.md section 7).
- `levels[h][i]` is the level `0` to `4` at point `i` at hour `h`. It is computed with **the same rules as checkpoints (including the load rules)**, so route colors and heatmap colors match.
- Points and hours that contain `null` are not produced; they are treated as errors (CLAUDE.md section 7).

## Errors (see CLAUDE.md section 7)

All errors share one format.

```json
{ "error": { "code": "GEOCODE_NOT_FOUND", "message": "...", "field": "origin" } }
```

| HTTP | `code` | Situation | Extra field |
|---|---|---|---|
| 400 | `INVALID_INPUT` | Missing field, wrong format, a disallowed `interval_miles`, a body that is not a JSON object, or origin and destination being the same place. Also used for a wrong HTTP method (405) | `field` (omitted when it concerns the whole body) |
| 400 | `DEPARTURE_IN_PAST` | The departure time is in the past | |
| 422 | `GEOCODE_NOT_FOUND` | The address could not be turned into coordinates | `field` (`origin`/`destination`) |
| 422 | `NO_ROUTE` | TomTom returned no route at all, or an end point is not near a road | |
| 422 | `FORECAST_OUT_OF_RANGE` | The needed hours run past the end of the forecast | `forecast_end` (ISO, the last hour that has a forecast; omitted when it could not be determined) |
| 502 | `ROUTING_UNAVAILABLE` | TomTom error or timeout | |
| 502 | `WEATHER_UNAVAILABLE` | Open-Meteo error, timeout, or a `null` value | |

When every route has No Travel it is **not an error.** Respond `200` with `recommendation.route_id: null` and the frontend shows a large warning banner.
