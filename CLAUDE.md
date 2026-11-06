# CLAUDE.md

[한국어](./CLAUDE.ko.md)

Implementation spec for the Spotter Full Stack Developer assessment (`fs-assessment-spotter.pdf`): **Weather-Aware Truck Routing**.

A **React + Django** web app that helps a truck driver choose the safest route based on **weather, load weight, and travel time**.

> Principle: **correctness and clarity over extra features.** (PDF: *Prioritize correctness and clarity over extra features.*)
> Tags below: `[PDF]` is stated in the PDF, `[Interpretation]` is an assumption where the PDF is silent, `[Decision]` is a direction set by the user. When you change an interpretation or decision, update this document and README.md together.

---

## 0. Documentation conventions

- **English is the default.** Every doc exists in English (`CLAUDE.md`, `README.md`, `docs/api-contract.md`) and the English file links to its Korean counterpart (`*.ko.md`) at the top.
- English is canonical. When you change a doc, update the Korean version in the same change.
- UI text is English. Commit messages are English. Code comments are English.

## 1. User inputs `[PDF]`

| Input | Notes |
|---|---|
| Origin & destination | Address strings, converted to coordinates by the geocoding API |
| Departure date/time | Basis for each checkpoint's ETA |
| Load weight | In lb (the load rules are defined in lb) |

## 2. What the app must do `[PDF]`

1. Generate **3 route options** using a routing API.
2. Sample each route every **10 / 25 / 50 miles** to create checkpoints, and fetch the weather at each checkpoint for **the truck's estimated arrival time (ETA)** there (not the current weather).
3. Calculate weather risk using the provided risk/load rules.
4. Recommend the best route, balancing **weather risk and travel time**.
5. Show **all routes, checkpoints, risk levels, ETAs, and route summaries** on a map.
6. Show a **weather heatmap along the trip corridor** with a **0–48 hour forecast slider**.

- **Third-party APIs are allowed** for routing / geocoding / weather. There is no need to build a routing engine.
- `[Decision]` Slider hour 0 is the **departure time** (slider value h = forecast h hours after departure). The PDF does not say what hour 0 is anchored to (it can also be read as "now"). Show the absolute date and time next to the slider so there is no doubt which moment the forecast is for.
- `[Interpretation]` "10 / 25 / 50 miles" is a sampling-interval option the user picks in the UI (default 25). A smaller interval is more precise but needs more weather API calls, so batch and cache the calls.

## 3. Risk rules `[PDF]`

Classify the weather at each checkpoint with these thresholds.

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind | < 25 mph | 25–34 | 35–44 | 45–54 | ≥ 55 mph |
| Rain | < 0.10 in/hr | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow | < 0.5 in/hr | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

- `[Interpretation]` Boundary handling: weather values are continuous, so read the table as gap-free, overlap-free intervals.
  - Wind: the table uses whole-number ranges, which leaves values like 34.5 mph undefined. Read it as `below 25 / 25 up to (not including) 35 / 35 up to 45 / 45 up to 55 / 55 and above`. The wind ranges in the load rules are read the same way.
  - Rain and Snow: values where range ends overlap (Rain 0.25 and 0.50, Snow 1.0 and 2.0) go to the **higher level**, consistent with "< 0.10 → Low" (0.10 is Moderate). No Travel applies only on strictly greater (`>`), exactly as written: Rain 1.00 and Snow 3.0 are Severe.
- `[Interpretation]` Wind means sustained wind speed. The PDF says only "Wind" and does not mention gusts.
- Convert weather API values to the table's units (mph, in/hr) before classifying.
- `[Interpretation]` A checkpoint's final risk level = **the highest of the Wind / Rain / Snow levels** (then raised by the load rules).
- Level order: `Low < Moderate < High < Severe < No Travel`

## 4. Load rules `[PDF]`

The load rules **raise** the wind-based level.

| Condition | Result |
|---|---|
| Wind ≥ 55 mph | **No Travel** (any load) |
| Wind 45–54 mph + load > 30,000 lb | **No Travel** |
| Wind 35–44 mph + load > 40,000 lb | **Severe** |

- The load rules only raise a level, never lower it. (Example: 45–54 mph with load ≤ 30,000 lb stays at the base Severe.)
- Load comparisons are strictly `>`. (Exactly 30,000 lb does not trigger the rule.)

## 5. Route recommendation `[PDF]`

Apply the priorities below as a **lexicographic comparison**: look at the next criterion only when the previous one is tied. Do not blend the four criteria into a weighted score.

1. **Fewest Severe miles**
2. **Fewest High miles**
3. **Lowest average risk**
4. **Shortest travel time**

- `[Interpretation]` Miles per level: place checkpoints at the origin (mile 0), every sampling interval, and the destination. Each checkpoint stands for the stretch from the midpoint to the previous checkpoint to the midpoint to the next (miles per level sum to the route's total distance), and that length is added to the checkpoint's level.
- `[Interpretation]` Tie rule: compare the rounded values that are shown on screen (miles to 1 mile, average risk to 2 decimals, travel time to the minute). Comparing unrounded floats almost always decides at criterion 3, so criterion 4 (travel time) would never be used, which contradicts the PDF's "balancing weather risk and travel time". Rounding is **half up** (24.5 miles shows as 25), not Python's round-half-to-even, so an exact half does not turn a tie on screen into a difference. If two routes tie on all four, the route listed first by the routing API wins (reported as `decided_by: duration`).
- `[Interpretation]` Average risk = levels converted to numbers (Low 0, Moderate 1, High 2, Severe 3, No Travel 4) and averaged weighted by stretch length.
- `[Interpretation]` A route with **any No Travel** checkpoint is excluded from the recommendation and shown as impassable. If all 3 routes have No Travel, show no recommendation and explain why. (The PDF does not say how to handle No Travel routes.)
- The recommendation states **why this route** won (which criterion beat the others) in one line. Example (the UI is English): "0 severe miles, 20 min slower than Route B"

## 6. Evaluation `[PDF]`

| Weight | Item |
|---|---|
| **40%** | Routes, Weather, risk & recommendation logic |
| **40%** | UI, map & heatmap smoothness and performance |
| **15%** | Code quality |
| **5%** | Documentation & walkthrough |

**Deliverables:** GitHub repository / hosted application / 5–10 min Loom walkthrough.

→ Work priority: correctness of risk and recommendation logic > map/heatmap performance > code quality > documentation.

## 7. Tech stack

**Stated in the PDF:** React (frontend) + Django (backend). Third-party APIs allowed for routing/geocoding/weather.

**`[Interpretation]` Concrete choices (not in the PDF, changeable):**

- Frontend: React + **TypeScript** (Vite) + a WebGL map (MapLibre), with the heatmap drawn as a WebGL layer `[Decision]`. API types live in `frontend/src/types/api.ts`, the contract in `docs/api-contract.md`.
- Backend: Django + Django REST Framework. API keys stay on the server and the frontend calls Django.
- External APIs `[Decision]` (Step 1 findings, free tiers):
  - routing: **TomTom Routing API, Calculate Route.** `travelMode=truck`, `vehicleWeight` (kg), `maxAlternatives` (0–5, means "up to N" and is not guaranteed). Free 20K requests/month, no credit card.
  - geocoding: **TomTom Geocoding API.** Free 20K requests/month. (Do not use Places Search Suggest autocomplete.)
  - weather: **Open-Meteo Forecast API.** No key, hourly data, units `wind_speed_unit=mph` / `precipitation_unit=inch`. Use only the default (best match) models and do not pick a model (HRRR ends 2026-11-30).
  - Weather variables `[Interpretation]`: wind = `wind_speed_10m` (instantaneous speed, gusts `wind_gusts_10m` not used), rain = `rain + showers` (preceding-hour sum in inches = in/hr), snow = `snowfall` (snow depth in inches, not liquid equivalent).
  - Open-Meteo's free tier is non-commercial (ad-free, subscription-free, non-profit). Show the CC BY 4.0 attribution on screen. Limits: 10,000/day, 5,000/hour, 600/minute.
  - Open-Meteo call spec `[Decision]` (measured with real calls on 2026-11-06):
    - **Cost = number of locations.** The response header `X-RateLimit-Cost` is 1 for 1 location and 100 for 100. The time span (48 hours / 7 days) and variable count (4 / 6) do not change the cost. `X-RateLimit-Remaining` drifts between calls, so do not trust it as an exact remaining count.
    - **Locations per request:** 400 (URL 6.3K chars) worked, 700 returned HTTP 414 (URI too long). Split into requests of **200 locations or fewer** (URL about 3.2K chars). Space calls so they stay under 600/minute, and retry on 429.
    - **Time window:** do not use `forecast_hours=48` because it means "from now". For a window anchored at departure use `start_hour` / `end_hour` (e.g. `start_hour=2026-11-09T12:00&end_hour=2026-11-11T12:00`). Use `timezone=UTC` everywhere.
    - **Forecast range:** `start_date` goes up to about +15 days from today (2026-11-21 as of 2026-11-06), and beyond that returns HTTP 400. Measured over the full 16 days at 2 locations: `null` appeared **only in the last 5 hours of the final day (+15 days)** and 0 times in the 15 days before. So `null` means hours past the end of the forecast, not degraded quality.
    - Treat `null` and out-of-range values as errors, never as 0. The error message says "The forecast is available until <last available time>."
    - **Two ways to run past the end (measured 2026-11-06):** (a) HTTP 400 `Parameter 'start_hour' (or 'end_hour') is out of allowed range from 2026-08-05 to 2026-11-21` (the last forecast *day*, no time), or (b) HTTP 200 with `null` from 19:00 UTC on the last day. Both become `FORECAST_OUT_OF_RANGE`. For (a) the last good hour is found with one extra one-location call (error path only); if that fails the error is still sent without `forecast_end`.
    - **Response facts:** one location answers with an object and several with a list. The wind unit label is `mp/h` (not `mph`), so the code checks the unit labels it receives and refuses anything else. Rain and snow values have 3 decimals.
    - **Departure validation:** the PDF sets no departure range, so **do not impose an arbitrary upper limit (e.g. +7 days).** There are only two rejection conditions. (1) The departure is in the past (TomTom accepts a past `departAt` without error, so the app must block it). (2) The needed hours (last checkpoint ETA, departure + 48 hours) run past the end of the forecast, detected from `null` / out-of-range in the response.
    - **Heatmap grid `[Decision]`:** 0.5° spacing (about 34 miles) with a 40-mile buffer on each side of the union of the 3 routes. For Chicago→Denver (routes of 1,004 / 1,163 / 1,336 miles) that is **278 points**. A 0.25° grid is 570 to 1,116 points and does not fit the limit, so it is not used. Built in Step 10 (`backend/trip/grid.py`): 280 points for that trip (live, 2026-11-06). The grid is every point on a multiple of the spacing that is within 40 miles of a route. A trip that would need more than 600 points (three far-apart routes across the country) gets a 1.0° or 2.0° grid, which bounds the cost of one heatmap at 600 weather calls; the response says which spacing was used. Variables are `wind_speed_10m`, `rain`, `showers`, `snowfall`; the window is departure to +48 hours (hours 0 to 48, 49 values).
    - **Checkpoint weather:** fetched separately from the heatmap, directly at the checkpoint coordinates (rounded to 2 decimals). Checkpoint counts (3 routes, deduplicated): 351 at 10 miles / 141 at 25 miles / 71 at 50 miles.
    - `[Interpretation]` **Which hour:** a checkpoint uses the forecast for the **hour nearest to its ETA** (a time exactly on :30 goes to the later hour). The forecast comes in whole hours and the heatmap slider shows whole hours too, so a checkpoint and the heatmap show the same forecast. Wind is the instantaneous value at that hour; rain and snow are the sums of the *preceding* hour (in/hr).
    - `[Interpretation]` `rain + showers` is rounded to 4 decimals, because a float sum such as 0.09 + 0.01 = 0.09999999999999999 would fall under the 0.10 boundary.
    - **Cost of one analysis (Chicago→Denver):** 25-mile interval 141 + 278 = **419 calls** (about 23 analyses/day), 10-mile interval 351 + 278 = **629 calls** (about 15/day). The cache key is (rounded coordinates, window start) with a TTL of about 1 hour. Load weight does not affect weather, so re-analyzing with only a different weight must not call the weather API again.
  - TomTom call spec `[Decision]` (confirmed with real calls on 2026-11-06):
    - Route: `GET /routing/1/calculateRoute/{lat,lon}:{lat,lon}/json` + `travelMode=truck`, `vehicleCommercial=true`, `vehicleWeight=<kg>`, `maxAlternatives=2`, `departAt=<departure>`, `instructionsType=coded`
    - Geocode: `GET /search/2/geocode/{address}.json` + `countrySet=US`, `limit=1`
    - The app's load input is in lb, so convert to kg for TomTom (× 0.45359237). Risk and load rules use the lb value as entered.
    - The route line is `routes[].legs[].points[]` (latitude and longitude only, no time). One Chicago→Denver route is about 10,000 points.
    - `[Interpretation]` ETA: use (`pointIndex`, `routeOffsetInMeters`, `travelTimeInSeconds`) from `guidance.instructions[]` as anchor points and interpolate time between anchors by distance along the route line. Verified in Step 4: median error 0.1 min, at most 3.7 min over a 14 hour trip (see the Step 4 checklist).
    - Risk: response size about 1.8MB and response time 6–10 seconds (3 routes, long distance). Per-request caching and a loading state are needed.
  - TomTom key: **confirmed in the dashboard that one key provides both Routing API and Geocoding API** (2026-11-06, Billing Type "Evaluation"). Whether Evaluation has a time limit is unknown, so check the expiry terms in the dashboard. The key is used only on the server (`.env`) and never exposed to the frontend.
  - Map background `[Decision]`: **TomTom Vector Tiles + MapLibre.** Dashboard limits (2026-11-06): Map Display Vector Tiles 200,000, Raster Tiles 200,000, Raster Non-tile 20,000. These are separate from routing/geocoding (20,000 each), and the dashboard shows no period. Raster is not used.
    - Confirmed with real calls (2026-11-06): classic vector tile `GET /map/1/tile/basic/main/{z}/{x}/{y}.pbf` and Orbis vector tile `GET /maps/orbis/display/vector/tile/{z}/{x}/{y}?apiVersion=2` both returned 200, and the MapLibre style JSON is available. Tile responses carry `cache-control: max-age=86400`, so the browser cache cuts requests.
    - Style candidates: classic `GET /style/1/style/*?map=basic_main` (775 layers, 333KB) / Orbis `GET /maps/orbis/assets/styles/*/style.json?apiVersion=1&map=basic_street-light` (121 layers, 139KB, light background). **`[Decision]` use classic `basic_main`.** Dashboard usage check (2026-11-06): 2 classic vector tile calls → Vector Tiles 2/200,000 and 1 raster call → Raster Tiles 1/200,000 matched exactly, and style JSON requests were not counted. The 1 Orbis tile was not added to Vector Tiles, so it is unclear which limit it counts against. Take the side whose limit is certain. The map rendering performance was measured in Step 2 and no layer hiding was needed.
    - **Key exposure `[Decision]`:** the style JSON and tile URLs contain the key, so it is visible in the browser. Keep the routing/geocoding key only on the server (`.env`) and **issue a separate map key used only by the frontend.** The dev key (`spotter-map-dev`) has no whitelist because TomTom does not accept `localhost` in the whitelist, and is used locally only. The production key (`spotter-map-prod`) is whitelisted to the deployment domain only. Whether the whitelist is actually enforced on tile requests is not confirmed and is verified in Step 12. Do not put a whitelist on the server key (`spotter-server`), since server calls carry no browser origin and may be blocked.

## 8. Implementation principles

- Risk and recommendation logic lives in the backend (Django). The frontend only displays results and handles interaction.
- Fetch weather for each checkpoint's **ETA time**. Handle time zones explicitly. If an ETA falls outside the weather API's forecast range, report an error instead of filling in a value.
- Reduce response time by making external API calls parallel/batched and cached. On failure show the user a clear error.
- Do not add features that were not requested.
- Keep secrets such as API keys in environment variables (`.env`) and never commit them.

## 9. UI references `[Decision]`

**Main (following only these is enough)**

1. **WeatherRoute**: the basis for the overall structure
   - Its concept of ranking 3 routes by weather safety is almost the same as the assignment.
   - Reference how the slider, route cards, and map dots change together.
2. **Weather on the Way**: how to present "weather at arrival time"
   - Shows each checkpoint's ETA together with the weather at that time.
   - It presents the assignment's core logic (ETA-based sampling) most clearly to the user.
3. **Google Maps**: 3-route comparison UI
   - The selected route is bold and the others gray. Users already know it, so it needs no explanation.

**Secondary (reference only parts)**

4. **Windy**: reference only the heatmap colors and legend. Do not copy flashy effects such as wind animation (performance cost, out of scope).
5. **Is it clear: Route Weather**: reference only the checkpoint list (timeline) form.

**Excluded**

6. **Drive Weather's live radar**: unnecessary because the assignment is forecast-based, not real-time.
7. **Sofar Wayfinder**: good structure but too complex. Simplify to slider + heatmap + truck position sync.

## 10. Build direction `[Decision]`

One line: combine **WeatherRoute's structure + Weather on the Way's ETA presentation + Google Maps' route comparison**, and spend time on **logic tests and explaining the recommendation** rather than flashy effects.

**Logic (40%): correctness**

- **Separate the risk and load rules into pure functions** (input: weather values and load → output: level) and write unit tests: boundary values (25, 35, 45, 55 mph etc.), the 3 load rules, and priority comparison.
- Compare the assignment's 4 priorities in order, exactly as given. Do not blend them into a weighted score. (→ section 5)
- Let the user choose the checkpoint interval of 10/25/50 miles. (→ section 2)
- Document in the README how Severe/High miles are computed from the stretch length between checkpoints (→ definition in section 5).

**UI (40%): clarity**

- Draw the route line in risk-colored stretches and keep the legend always visible.
- Route cards show only 4 numbers: Severe miles / High miles / average risk / duration. (UI labels: `Severe mi` / `High mi` / `Avg risk` / `Duration`)
- Show the reason for the recommended route in one line. (→ section 5)
- If there is a No Travel stretch, show a large warning banner.
- **All UI text is English** `[Decision]`: labels, buttons, legend, recommendation reason, and error messages. Risk levels use the PDF's terms exactly: `Low` / `Moderate` / `High` / `Severe` / `No Travel`. Repository docs are English by default with Korean counterparts (`*.ko.md`), and **commit messages are English**.

**Performance: smoothness**

- The backend fetches 48 hours of weather in one go and caches it.
- Moving the slider must not call the API again; the frontend only swaps the layer.
- Draw the heatmap with a WebGL map (Mapbox GL / MapLibre).

**Docs/video (5%)**

- The README records how the rules are interpreted and the assumptions.
- Keep the Loom short, in the order "input → 3 routes → recommendation reason → slider".

## 11. Step-by-step checklist

The order is: lock the logic down with tests first, then attach the screens. Mark an item `[x]` when it is done. Do not move to the next step before the previous one is finished.

### Step 1. Confirm and verify external APIs

- [x] Routing API chosen: TomTom Routing (done, recorded in section 7)
- [x] Confirmed **3 routes** from TomTom (2026-11-06, Chicago→Denver, truck, `maxAlternatives=2`): 1,006mi/14.1h, 1,164mi/16.6h, 1,338mi/19.5h
- [x] Confirmed 3 routes on short/medium trips too (2026-11-06): Chicago→O'Hare 17.8/27.6/38.5mi, →Milwaukee 89.5/94.6/194mi, →Indianapolis 191.9/222.6/218.7mi. The third route can be more than 2× the shortest (Milwaukee)
- [x] Checked the effect of `vehicleWeight`: at 5,000kg / 20,000kg / 36,000kg Chicago→Denver is 1,004.4 / 1,006.3 / 1,006.3mi, nearly identical. TomTom's weight is for road restrictions and barely changes routes. Weather and load risk are decided by our own rules (section 4)
- [x] Cumulative distance and time per checkpoint: `guidance.instructions[]` with `instructionsType=coded` gives `routeOffsetInMeters`, `travelTimeInSeconds`, `pointIndex`. Confirmed the last instruction's values match the `summary` totals exactly (1,619,492m / 50,822s)
- [x] Confirmed `departAt` support: a future time changes `departureTime`/`arrivalTime` accordingly. **A past time is also accepted with 200 and no error**, so the app must validate input itself
- [x] Policy when fewer than 3 routes come back `[Interpretation]`: TomTom guarantees only "up to N" (all 4 trips tested returned 3), so use exactly the routes received and show "Only N alternative routes available" on screen. Do not invent routes to fill the gap. Risk analysis and display must work the same with only 1 route (for reference: the public OSRM and Valhalla servers returned only 2 for Chicago→Denver)
- [x] Weather API chosen: Open-Meteo (confirmed keyless call with 2 locations · 48 hours · mph/inch)
- [x] Geocoding API chosen: TomTom Geocoding (done)
- [x] TomTom API key issued: confirmed one key provides Routing + Geocoding
- [x] Checked the TomTom key's "Evaluation" limits: the API Usage screen shows Routing 20,000 and Geocoding 20,000 (usage 3 and 2 as of 2026-11-06). Enough for demo scale. The expiry date was not visible on the screen (re-check that the key is alive before deployment and the Loom)
- [x] Confirmed TomTom Geocoding calls: "Chicago, IL" and "Denver, CO" with `countrySet=US` each returned 1 result with correct coordinates
- [x] Measured Open-Meteo cost for multiple locations: 1 location = 1 call (`X-RateLimit-Cost`), split into requests of 200 or fewer
- [x] Decided heatmap grid density: 0.5° grid + 40-mile buffer = 278 points. One analysis is 419 to 629 calls, within 10,000/day (details in section 7)
- [x] Recorded the chosen APIs in section 7 (tech stack)
- [x] Recorded the chosen APIs in the README tech stack

### Step 2. Project skeleton and API contract

- [x] Created the Django + DRF backend (`backend/`, Python 3.12 + uv, Django 6.1, DRF 3.18, pytest). `manage.py check` passes, dev server responds
- [x] Created the React frontend (`frontend/`, Vite 8 + React 19 + **TypeScript** `[Decision]` + maplibre-gl 6). lint and build pass, Vite proxy (`/api` → Django) confirmed
- [x] Confirmed map rendering (2026-11-06): both the dev server and the production build (`vite preview`) show the North America map with no console errors. See section 12 for the 3 MapLibre 6 + Vite pitfalls
- [x] Issued the dev map key (`spotter-map-dev`, separate from the server key). TomTom's input does not accept `localhost` as a domain (only `example.com` style), so **leave the dev key's whitelist empty.** Put it in `VITE_TOMTOM_MAP_KEY` in `frontend/.env.local`
- [ ] (At Step 12 deployment) Issue the production map key (`spotter-map-prod`) + register the deployment domain in the whitelist, and put only this key in the production build. The dev map key has no product restriction and **can also call the routing API** (confirmed 2026-11-06, HTTP 200). For the production key, check whether Products can be limited to Map Display, and if not, defend with the domain whitelist alone. Verify that the whitelist is actually enforced on tile and style requests (rejected from a non-allowed domain)
- [x] Chose the map style: classic `basic_main` (the Orbis tile was not added to the Vector Tiles limit, so it is excluded)
- [x] Measured rendering performance of the classic style (775 layers) (2026-11-06, production build, Apple M4 Pro, Chrome, base map only): over 22 seconds of zoom/pan/zoom-out, 1,285 frames, average 17.1ms (about 58fps), p95 17.5ms, p99 33.3ms. 2 frames over 100ms (max 217ms), 1 long task (229ms, right after the first zoom). Idle baseline average 20.5ms. Style load about 0.4s, JS 357KB (gzip) + worker 145KB (gzip). **No layer hiding** (no problem). Caveat: measured on a fast machine without routes or heatmap, so re-measure in Step 11
- [x] Manage API keys with `.env` and add it to `.gitignore` (`.env.example` written; Django settings refuse to start without `DJANGO_SECRET_KEY` in `.env`)
- [x] Fixed the request/response format `[Decision]` (2026-11-06, confirmed by the user): `docs/api-contract.md`, `frontend/src/types/api.ts`. Routes and heatmap are separate endpoints, the recommendation reason is passed as structured values (the frontend assembles the English sentence), heatmap levels include the load rules, 7 error codes

### Step 3. Risk rule pure functions and unit tests

- [x] Wind/rain/snow classification functions (section 3): `classify_wind`, `classify_rain`, `classify_snow` in `backend/trip/risk.py`
- [x] Checkpoint level = highest of the three levels: `assess_checkpoint()` returns `level_by`, `base_level`, `level`, `load_escalated` (the contract's checkpoint fields)
- [x] Load rule escalation (section 4): `apply_load_rules()` only raises a level. `load_escalated` is true only when the final level is above the base level (false when the weather already reached it)
- [x] Test: wind boundaries 25, 35, 45, 55 mph and in-between values such as 34.5 (`backend/trip/tests/test_risk.py`)
- [x] Test: rain 0.10, 0.25, 0.50, 1.00 and snow 0.5, 1.0, 2.0, 3.0, each with the value just below and just above
- [x] Test: the 3 load rules (including exactly 30,000 lb and 40,000 lb), plus "a load rule never lowers a level" and "level is the highest of the three" over a grid
- [x] Verified the tests catch mistakes (2026-11-06): 20 deliberate mutations of `risk.py` (flipped `>=`/`>`, shifted thresholds, a load rule that lowers a level, missing input checks ...) were all caught. 427 tests pass
- [x] Invalid measurements raise `ValueError` instead of being treated as 0: `None`, NaN, infinity, negative, booleans, strings. A missing weather value must never make a stretch look safe, so Step 5 must turn a missing/`null` forecast value into the `WEATHER_UNAVAILABLE` error and never pass 0 in its place
- [x] Tests run on a fresh checkout and in CI without a `.env`: pytest uses `config/settings_test.py`, which supplies a throwaway `DJANGO_SECRET_KEY` only when none is set. The app itself still refuses to start without one

### Step 4. Route sampling and ETA

- [x] Create checkpoints: origin (mile 0), every interval (10/25/50 miles), destination: `checkpoint_miles()` and `build_checkpoints()` in `backend/trip/sampling.py` (pure functions). A destination exactly on an interval is not listed twice (a 1e-6 mile tolerance absorbs float noise)
- [x] ETA = departure time + cumulative travel time to that point: time is known only at TomTom's guidance anchors and is interpolated by distance between them. Measured on the 3 real Chicago→Denver routes by leaving one anchor out and predicting it from its neighbours: median 0.1 min, at most 3.7 min over a 14 hour trip (a single average speed over the whole route is off by up to 43 min)
- [x] Handle time zones explicitly: `departure` must be timezone-aware (a naive datetime raises `ValueError`) and ETAs are returned in UTC, rounded to the second. Tested with CST/MST/Seoul offsets and across midnight and the 2026-11-01 US fall-back date
- [x] Compute the miles each checkpoint represents (to the midpoints with its neighbors): `represented_miles()`; the first checkpoint starts at mile 0 and the last ends at the destination
- [x] Distance along the route: the polyline holds only coordinates and its haversine length is about 0.2% short of TomTom's (up to 3.3 km on a 1,000 mile route), so the distance is stretched piecewise between anchors until it equals each anchor's TomTom distance exactly. A checkpoint placed at an anchor's distance lands exactly on that anchor's point
- [x] Test: sum of represented miles = total route distance (uniform, profiled, real and 25 random routes)
- [x] Test: routes shorter than the interval and routes not divisible by the interval (8 mi, 25 mi, 25.5 mi, 101 mi and more, at 10/25/50)
- [x] Real-data test: `backend/trip/tests/fixtures/tomtom_route_prefix.json` is the first 156.6 miles of a recorded TomTom route (2,909 points, 26 anchors, two of them sharing `pointIndex` 1080)
- [x] Edge rules: anchors sharing a `pointIndex` keep the first; the first and last anchors are always pinned to (0 m, 0 s) and (total length, total time); anchors that go backwards in distance or time are rejected; with no anchors, time is proportional to distance. A stop (same distance, later time) gives the checkpoint the time the truck *first arrives*
- [x] Mutation check (2026-11-06): 26 deliberate mutations of `sampling.py`, 23 caught; the 3 others are behaviourally identical (a `<`/`<=` that differs only on exact equality, and two input checks that another check already covers). It found a **real bug**: `checkpoint_miles` looped for ever for an infinite length or a tiny interval. Now it rejects non-finite values and more than `MAX_CHECKPOINTS` (10,000) checkpoints. 635 tests pass
- [x] Done in Step 7: origin = destination is refused as `INVALID_INPUT` on `destination` (places within about 1 m, or a route of length 0)
- [x] Done in Step 7: `mile`, `represents_miles`, coordinates and times are rounded only when the response is built

### Step 5. Weather lookup at ETA

- [x] Fetch the forecast for each checkpoint's ETA time (not current weather): `WeatherClient.get_weather_at()` in `backend/trip/weather_client.py` takes (lat, lon, ETA) and returns wind / rain / snow in the order given. The ETA is matched to the nearest forecast hour (`nearest_hour()` in `weather.py`)
- [x] Unit conversion: Open-Meteo is asked for `mph` and `inch` directly, and the response's unit labels are checked (a mismatch such as `km/h` is refused). rain = `rain + showers`, snow = `snowfall`. The label for mph is `mp/h`
- [x] Batch fetch and cache: requests of at most 200 locations (run in parallel, up to 4 at once), each asking only for the hours it needs; the same (position, hour) is fetched once; every good hour of an answer is cached for 1 hour (Django cache, 50,000 entries). Measured live: 230 locations = 2 requests in 1.4 s, a repeat = 0 requests. The same departure with a different load weight makes no weather call. (The 48-hour grid for the heatmap is Step 10)
- [x] Error when the ETA is outside the forecast range: `ForecastOutOfRange` (HTTP 400 or `null` hours at the end of the forecast, with `forecast_end` when it can be found) → `FORECAST_OUT_OF_RANGE`; any other failure (timeout, 429/5xx after 3 attempts, bad data, a `null` in the middle) → `WeatherUnavailable` → `WEATHER_UNAVAILABLE`. A missing value is never replaced by 0, and one bad location fails the whole call
- [x] Test: unit conversion, matching ETA time to forecast time (`backend/trip/tests/test_weather.py`, `test_weather_client.py`): :29/:30 rounding, other time zones, midnight and the US fall-back date; the request parameters; order of results; dedupe; batching at 200/201; cache hits/misses; retries; both out-of-range forms; units; garbage values
- [x] Verified the tests catch mistakes (2026-11-06): 59 deliberate mutations of `weather.py` and `weather_client.py`. The first run found 3 real gaps (a response with *more* locations than requested was accepted; a cache key without latitude or longitude would return another place's weather), now covered; 4 survivors behave identically to the original. 784 tests pass
- [x] Checked against the live API (2026-11-06): a recorded Chicago route (8 checkpoints) went through sampling → weather → risk. The values match a direct API call for the same hour. A departure past the forecast gives `FORECAST_OUT_OF_RANGE` with `forecast_end` 2026-11-21 18:00Z in both forms

### Step 6. Route summary and recommendation

- [x] Compute the route summary: `summarize_route()` in `backend/trip/summary.py` takes the checkpoints' levels with the miles each stands for and returns the contract's summary fields, already rounded for display (miles per level, `severe_miles`, `high_miles`, `avg_risk` weighted by length, `duration_minutes`, `arrival`, `has_no_travel`). Severe miles are the Severe level only (not No Travel), High miles the High level only
- [x] Compare the 4 criteria in order (no weighted score, ties decided on rounded values): `recommend()` in `backend/trip/recommend.py` sorts by the tuple (Severe miles, High miles, average risk, minutes) of the rounded values. The sort is stable, so a full tie keeps the routing API's order. `decided_by` is the first criterion on which the winner differs from the **runner-up** (not from last place)
- [x] Exclude No Travel routes, and no recommendation if all 3 are No Travel: excluded routes are listed in `excluded_route_ids`; with none left `route_id` is `null` (not an error); with one left it is `only_candidate`; fewer than 3 routes work the same way
- [x] The one-line recommendation reason: the backend sends the structured values (`decided_by`, `versus_route_id`, `duration_delta_minutes`), as the contract says. The English sentence is built by the frontend in Step 8 ("Show the recommended route and a one-line reason")
- [x] Test: cases decided at each of criteria 1, 2, 3, 4 (`backend/trip/tests/test_recommend.py`), plus "not a blended score" cases (0 severe miles beats any speed, and so on) and ties on rounded values (24.6 vs 25.4 severe miles, average risk 0.331 vs 0.334, 30-second differences in minutes) built end to end through `summarize_route`
- [x] Test: some routes No Travel and all routes No Travel, one route left, one route given, no route given; 3,000 random cases (with many ties) against a plain `min()` of the four values
- [x] Verified the tests catch mistakes (2026-11-06): 42 deliberate mutations of `summary.py` and `recommend.py` (criteria dropped or swapped, round-half-even, unweighted average, wrong level fields, flipped delta sign, wrong runner-up ...), all caught. 883 tests pass
- [x] Checked on a real route (2026-11-06): the recorded Chicago route with live weather plus two invented storm variants went through sampling → weather → risk → summary → recommendation. By hand, 40 mph at 3 checkpoints of 25 miles gives 75 High miles and average risk 75×2/157 = 0.96; with a 45,000 lb load the same wind is Severe and a 50 mph checkpoint becomes No Travel, which excludes that route

### Step 7. Backend integration and manual verification

- [x] Integrate Steps 3 to 6 behind `POST /api/analyze` (`backend/trip/`): `validation.py` (request) → `analysis.py` (geocode both ends in parallel → TomTom routes → checkpoints → **one** weather call for every checkpoint of every route → risk → summary → recommendation → response) with `tomtom.py` (geocoding, truck routes, cached), `geometry.py` (risk-coloured segments, Douglas-Peucker simplification at about 33 m: 89 miles → about 117 points instead of 2,000), `errors.py` (one error shape) and `views.py`. The shared retry logic is in `http.py`. `/api/heatmap` is Step 10
- [x] Error handling, checked against the live server: unknown address (422 `GEOCODE_NOT_FOUND` with the field), no route (Chicago → Honolulu, 422), same place (400), past departure (400), departure beyond the forecast (422 with `forecast_end`), bad interval / naive time / negative weight / missing field / invalid JSON / array body / GET (400, 405), TomTom or Open-Meteo down (502, with no URL or key in the message). Fewer than 3 routes are passed on as they are. Routes are cached for 15 minutes, so a repeat (for example another interval) took 25 ms instead of 4 s
- [x] Compared one real route with values computed by hand (2026-11-06): Raleigh, NC → Norfolk, VA, departure 14:00Z, 42,000 lb, 10-mile checkpoints, during a real rain storm. An independent script (it imports nothing from `trip/`) called TomTom and Open-Meteo itself and recomputed everything: all 70 checkpoints' positions (within 5 m of the route line), ETAs (within 1 s), weather values, levels, miles per level, average risk, ranking, exclusion and `decided_by`. **Every number matched.** Route C had a real No Travel checkpoint (mile 250, 18:00Z, rain 1.02 in/hr) and was excluded; A and B tied on Severe and High miles (both 0), and B won on average risk (20 moderate miles over 206.9 miles = 0.097 → 0.10, against 20 over 184.6 = 0.108 → 0.11) although it is 26 minutes slower
- [x] Verified the tests catch mistakes (2026-11-06): 107 deliberate mutations of the new modules; the first run found 12 real gaps (the route cache ignored the destination, the longitude was not scaled by latitude, the cut positions were never checked ...), now covered. The survivors behave identically to the original. 1,148 tests pass

### Step 8. Basic screen layout

- [x] Layout: left panel (form, results, route cards, credits) + map on the right (`frontend/src/App.tsx`, `index.css`). Under 820 px wide the map goes on top and the panel below. Checked in a real browser (dev server and the production build)
- [x] Input form (`components/AnalysisForm.tsx`): From, To, Departure (`datetime-local`), Load weight (lb), checkpoint interval 10 / 25 / 50 mi (default 25). Defaults are Chicago, IL → Denver, CO, 42,000 lb and the next quarter hour, so a reviewer can press the button at once. Missing or invalid values are caught before anything is sent; errors the server reports for a field (unknown address, past departure ...) show under that field, other errors in a box. Only the latest request counts (an older one is aborted), and the button shows "Analyzing…" with a note that it can take up to 10 seconds
- [x] Routes on the map (`components/MapView.tsx`): the selected route is bold blue with a white outline, the others thin gray; clicking a gray route on the map or its card selects it; green origin and red destination dots; the map zooms to the routes when a result arrives (not when the selection changes). The lines are drawn above the base map: under the first label layer the basemap's roads covered them
- [x] Route cards (`components/RouteCard.tsx`) with the 4 numbers `Severe mi` / `High mi` / `Avg risk` / `Duration`. The header also shows the route's distance (it is a label, not one of the 4 numbers) and the badges `Recommended` and `No Travel`; a blocked route has a dashed border
- [x] The recommended route and a one-line reason: `lib/reason.ts` builds the sentence from the structured values, for example "Lowest average risk (0.10 vs 0.11 on Route A), 26 min slower than Route A." All branches are unit-tested (severe, high, average, time, full tie, only candidate, no recommendation). The place names the server resolved are shown above the cards, so a wrong address match is visible
- [x] No Travel warning banner (`components/NoTravelBanner.tsx`): a large red banner naming the blocked routes and, for each, the first No Travel point (mile and local time, plus "heavy load in strong wind" when the load rule caused it). Also a notice when fewer than 3 routes came back ("Only 2 routes available for this trip."), and the Open-Meteo CC BY 4.0 credit is always on screen
- [x] Frontend tests (`npm test`, vitest): 65 tests for the time conversions (local time to UTC, the fall-back date, midnight), the reason sentences, the warnings and the API client's error handling (network failure, HTML error page, abort). 36 deliberate mutations of these modules, all caught except one that behaves identically (the first run found one real gap, the mile rounding, now covered)
- [x] Measured (2026-11-06): with a departure close to now, TomTom uses **live traffic**: Chicago → Denver gave 1,184 / 1,212 / 1,338 miles (the 1,006-mile I-80 route is missing because of traffic delays), while a departure 4 days out gave 1,006 / 1,164 / 1,338 as in Step 1, and `traffic=false` gives the Step 1 set again. So the route set and times depend on when you leave. The request is correct; this is TomTom's real-time data

### Step 9. Risk display

- [x] The route line in risk-colored stretches: the selected route is drawn from the API's `segments`, one color per level (`map/layers.ts`, `map/geo.ts`); the other routes stay gray. One palette (`lib/risk.ts`: green, yellow, orange, red, dark purple) serves the line, the dots, the legend and, in Step 10, the heatmap. The steps differ in lightness as well as hue, so the order survives for people who cannot tell red from green, and a unit test checks that the colors are distinct and get darker from Moderate up. Butt line caps, so one level ends exactly where the next begins
- [x] Always-visible legend (`components/Legend.tsx`): the five levels with the PDF's names plus "Other routes", on the map's bottom-left corner whether or not a route is shown
- [x] Checkpoint markers: a dot on the selected route at every checkpoint, colored by its level. Clicking one opens a popup with the arrival time, wind / rain / snow with the level each gives, the final level, and, when a load rule raised the level, which rule (`map/popup.ts`, `lib/checkpoint.ts`: "Load over 30,000 lb with wind of 45-54 mph" or "Load over 40,000 lb with wind of 35-44 mph", told apart by the final level). Rain and snow are shown with up to 3 decimals so a Low 0.095 never reads as 0.10. A click on a dot is not a click on the route under it
- [x] Checkpoint list (timeline) (`components/CheckpointTimeline.tsx`): the selected route's checkpoints in driving order with mile, level, arrival time (your time zone, stated above the list) and the weather line; Severe and No Travel are in red. It is linked both ways with the map: choosing a list item moves the map there and opens the popup; clicking a dot highlights and scrolls to its list item; closing the popup clears the highlight; choosing another route clears it
- [x] Checked in a real browser (2026-11-06, Raleigh → Norfolk during a real rain storm, dev server and production build): green line with a yellow Moderate stretch for Route B, and a dark-purple No Travel stretch on Route C whose popup shows rain 1.02 in/hr. Unit tests for the checkpoint text, the palette and the map data (35 more, 100 in all, then 28 deliberate mutations, all caught)

### Step 10. Heatmap and 0–48 hour slider

- [x] The 48-hour forecast for the trip-corridor grid in one go: `POST /api/heatmap` (`backend/trip/heatmap.py`, `grid.py`, `views.py`) takes the same body as `/api/analyze`, reuses the cached routes, builds the grid, asks for every point at every hour in one batched weather call (280 points x 49 hours, 2 requests) and returns the levels for all 49 hours with the same risk and load rules as checkpoints. Live: 8.8 s the first time with a cold route cache, 0.15 s when repeated, 31 KB. The weather cache keeps the hours, so changing only the load weight calls Open-Meteo again for nothing.
- [x] The heatmap as a WebGL layer: one MapLibre `circle` layer under the route lines. The circles are soft (blur 1) and about 0.9 grid spacings wide, so they blend into a surface; their radius doubles with every zoom level so the shading keeps its size on the ground, and the colors are the same palette as the route. Calm weather is faint and trouble is strong (opacity 0.16 to 0.66). A first version with a smaller radius showed horizontal stripes between the grid rows, because rows are a full spacing apart north-south but closer east-west
- [x] Slider hour 0 = departure time `[Decision]`, with the absolute date and time next to the slider (`components/ForecastSlider.tsx`): "Departure hour · Fri, Nov 6, 10:00 PM GMT+8", then "+5 h · ...". Hour 0 is the departure **rounded to the nearest hour** (the contract said "floored"; rounding uses the same rule as checkpoints, so a checkpoint and the heatmap show the same forecast, and it is at most 30 minutes from the real departure). If the heatmap cannot be built (for example the forecast ends before departure + 48 h) the routes still show and the slider area says why
- [x] Moving the slider swaps the layer without calling the API again: the whole grid is loaded into the map once with the levels of every hour as properties `h0` to `h48`, and the slider only changes which property the colour is read from (`setPaintProperty`). Measured in the browser, 97 slider steps: **0 API calls**, average frame 16.6 ms, slowest 19.2 ms on the dev server and 23.6 ms on the production build, no frame over 50 ms. The slow parts of the page do not re-render on a slider move
- [x] The slider is synced with the truck's expected position: a dark dot on the selected route at the position the truck has at that hour (`lib/heatmap.ts`: the mile is interpolated between the checkpoints by their ETAs, and the position is that share of the way along the route line by length), with "Route A: truck at mile 407 of 1028", "leaves Fri 2:15 PM" before departure and "arrived Fri 5:25 PM" after
- [x] Tests: backend 73 more (grid against a brute-force reference, the heatmap use case, the endpoint; 1,221 in all) and frontend 40 more (140 in all). Mutation tests: the grid and heatmap found a real flaw, a long straight segment over many degrees of latitude measured its far end with the wrong scale and dropped points that are within 40 miles (found by a new test, not by a mutant); the segments are now cut into 0.25° pieces. The frontend found 2 more gaps and one piece of dead code (removed). The few survivors behave identically to the original

### Step 11. Performance and final checks

- [x] Loading and error states, each looked at in a real browser: the analysis (spinner and "This takes 5 to 10 seconds, and up to 30 for a very long trip"), a field error under its field, a general error in a box, the API not answering (HTTP 502 from the proxy: "The server is not responding", plus a start-the-backend hint in development only), the heatmap loading and failing (the routes stay; the slider area says why), the map chunk loading ("Loading map…"), and a map the server refuses (a wrong key: "The map was refused: its key may be missing, expired, or not allowed for this site", in the middle of the empty map, so it is not mistaken for no result). The map reports such errors only for a style that never loads or a 401/403, not for each missing tile (`map/errors.ts`, tested)
- [x] The slider does not stutter (measured below, 0 API calls during 97 steps)
- [x] Response time under the heaviest condition. **Chicago to Denver, 10-mile checkpoints (355 checkpoints, 3 routes of 1,006 / 1,164 / 1,338 miles), live, empty caches: the analysis takes 8.3 s** (TomTom routes 5.4 s, address lookup about 1.1 s, weather 1.4 s) and **the heatmap 0.8 s**; repeated, 0.32 s and 0.15 s. Our own work is 0.31 s and 0.08 s (a profile shows the route line simplification and the distances along the route as the largest parts). **A coast-to-coast trip, Seattle to Miami (3 routes of 3,336 / 3,555 / 3,554 miles, 42,000 to 49,000 points each): TomTom alone takes 20.7 s**; our work is 0.48 s (analysis) and 0.52 s (heatmap, 178 points on a 1.0° grid); 1,049 checkpoints become 954 distinct weather locations, plus 178 for the heatmap, about 1,130 Open-Meteo calls of the 10,000 a day (about 8 such trips a day). The weather for this trip was stubbed to save quota; the TomTom and our own times are real. Consequences: the answer can be 800 KB of JSON, so **responses are gzipped** now (`GZipMiddleware`, tested); the wait text says up to 30 s; and **the host must allow a request of at least 60 s** (see Step 12)
- [x] Map rendering performance re-measured (2026-11-06, production build, Apple M4 Pro, Chrome driven over the DevTools Protocol with real mouse input, `frontend/scripts/measure-frames.mjs`): 3 routes, the heatmap, 104 checkpoint dots and a 104-item list (Chicago to Denver, 10 miles). **Normal CPU: slider sweep 97 frames avg 16.7 ms, max 17.7 ms; zoom in / pan / zoom out 501 frames avg 16.7 ms, max 17.7 ms; slider while panning avg 16.7 ms, max 17.7 ms; no frame over 50 ms** (Step 2 baseline for the bare map: avg 17.1 ms, 2 frames over 100 ms, max 217 ms). **CPU 4x slower: slider avg 14.4 ms, max 25.9 ms; no frame over 50 ms. CPU 6x slower: slider avg 25.6 ms (about 40 fps), p95 34 ms, one frame of 83 ms; panning and zooming are unchanged because the GPU does that work**
- [x] A slider step was made cheaper after profiling it on the 6x CPU. The profile showed the map rebuilding the heatmap's tiles in its worker on every step: a layer colour that reads each feature's property (`h<hour>`) is baked into the tile buffers, so changing it reloads the source. Now there is one layer per hour (49) and a step only switches a constant opacity (0 / 1), which does not rebuild anything, and a layer at opacity 0 is not drawn. Main-thread work per step at 6x: 30.2 ms to 24.1 ms (the rest is the map library re-evaluating the 800 base-map layers on any style change). Also done: one `rgba` colour expression (alpha built in) instead of separate colour and opacity, date formatters created once (`Intl.DateTimeFormat` is slow to build), and the truck as an HTML marker rather than a GeoJSON source (the marker alone did not change the profile; kept because moving a marker is the cheaper way to move one dot). These gave no big win by themselves: the layer-per-hour change is what mattered
- [x] The JS bundle is split: the first load is **76 KB gzip** (React and the app; it was 367 KB), and the map library loads on demand as its own chunk (296 KB gzip, plus the 10 KB gzip CSS and the map worker), downloaded while the form is shown (`React.lazy`, `Suspense`). Form ready in about 0.5 s and first paint in about 0.1 s in the harness. The size warning limit is set to 1.3 MB because the map chunk is inherently about 1 MB
- [x] All unit tests pass: backend 1,224, frontend 160. The new code was mutation-tested (the frontend helpers 11 of 11 caught); `manage.py check` is clean and the production build works in a real browser

### Step 12. Deployment

- [ ] Decide the hosting location
- [ ] Deploy backend and frontend, set environment variables. Things Step 11 found that the deployment must handle: (1) the server's request timeout must be at least 60 s, because a coast-to-coast trip takes about 21 s at TomTom alone and the form says up to 30 s (gunicorn's default 30 s would cut it off); (2) `manage.py check --deploy` reports `DEBUG` on (from `.env`), no HSTS and no HTTPS redirect: set `DJANGO_DEBUG=0` and let the host or a setting force HTTPS; (3) gzip is on in Django, but a front proxy may do it too
- [ ] Re-run the Step 7 verification route on the deployed app

### Step 13. Docs and Loom

- [ ] Add run instructions to the README
- [ ] Check that the README's rule interpretations and assumptions match the implementation
- [ ] Clean up the GitHub repository (confirm no secrets were committed)
- [ ] Record a 5–10 min Loom: input → 3 routes → recommendation reason → slider

## 12. Project structure and dev commands

```
spotter/
├── CLAUDE.md, README.md, .env.example   # each doc has a Korean counterpart: *.ko.md
├── docs/api-contract.md        # backend ↔ frontend API contract (source of truth)
├── backend/                    # Django + DRF (Python 3.12, uv)
│   ├── config/                 # settings (loads .env), settings_test (used by pytest), urls
│   └── trip/                   # API app: pure logic (risk rules, recommendation) + views, tests/
└── frontend/                   # Vite + React + TypeScript + maplibre-gl
    └── src/{components, lib, types}   # lib: API client, formatting, recommendation sentence (tested)
```

| Purpose | Command (directory) |
|---|---|
| Run backend | `uv run python manage.py runserver` (`backend/`, port 8000; `POST /api/analyze`) |
| Backend tests | `uv run pytest` (`backend/`, no `.env` needed) |
| Backend check | `uv run python manage.py check` (`backend/`) |
| Run frontend | `npm run dev` (`frontend/`, port 5173, `/api` is proxied to 8000). **The backend must be running too** (second terminal); without it the form shows "The server is not responding (HTTP 502)" and the dev server prints `ECONNREFUSED` |
| Frontend checks | `npm run lint`, `npm test`, `npm run build` (`frontend/`) |

- Environment variables: root `.env` (server-side `TOMTOM_API_KEY`, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`) and frontend `frontend/.env.local` (`VITE_TOMTOM_MAP_KEY`, the map-only key). Never commit either.
- The first load is about 76KB gzip (React and the app). The map is a separate chunk loaded on demand (296KB gzip with the key; without `VITE_TOMTOM_MAP_KEY` at build time part of its code is dropped, 190KB, and the map area shows a message instead). Always set the key for the production build.
- When mutation-testing, delete `__pycache__` and run Python with `-B`: a stale `.pyc` (same file size and modification second as the previous mutant) once made a mutant look "caught" when it was not.
- The system has a broken `black`, so `django-admin startproject` prints a `Bad CPU type` error, but the files are created correctly (ignore it).

### Known MapLibre 6 + Vite pitfalls (2026-11-06, all fixed, do not revert)

After touching map code, do not only check the dev server: **also open the production build** (`npm run build` → `npx vite preview` → browser). The dev server was fine while the build was broken once.

1. **Dev server: `Worker failed to load`.** Vite pre-bundles maplibre-gl and looks for the worker file under `.vite/deps/`, which 404s. → `optimizeDeps.exclude: ['maplibre-gl']` in `vite.config.ts`.
2. **Production build: same error.** The worker URL is `new URL('./maplibre-gl-worker.mjs', import.meta.url)` but the build never emits that file. → In `MapView.tsx` import `maplibre-gl/dist/maplibre-gl-worker.mjs?url` and pass it to `setWorkerUrl()`. (The exclude in item 1 alone fixes only the dev server, and `setWorkerUrl` alone does not fix the dev server. Both are needed.)
3. **Map height 0.** `maplibre-gl.css` overrides the container to `position: relative`, which voids `.map { position: absolute; inset: 0 }`. → Raise selector specificity with `.map-area .map` in `index.css`.
