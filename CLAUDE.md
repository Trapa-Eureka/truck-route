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
- `[Interpretation]` Tie rule: compare the rounded values that are shown on screen (miles to 1 mile, average risk to 2 decimals, travel time to the minute). Comparing unrounded floats almost always decides at criterion 3, so criterion 4 (travel time) would never be used, which contradicts the PDF's "balancing weather risk and travel time".
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
    - **Departure validation:** the PDF sets no departure range, so **do not impose an arbitrary upper limit (e.g. +7 days).** There are only two rejection conditions. (1) The departure is in the past (TomTom accepts a past `departAt` without error, so the app must block it). (2) The needed hours (last checkpoint ETA, departure + 48 hours) run past the end of the forecast, detected from `null` / out-of-range in the response.
    - **Heatmap grid `[Decision]`:** 0.5° spacing (about 34 miles) with a 40-mile buffer on each side of the union of the 3 routes. For Chicago→Denver (routes of 1,004 / 1,163 / 1,336 miles) that is **278 points**. A 0.25° grid is 570 to 1,116 points and does not fit the limit, so it is not used. Variables are `wind_speed_10m`, `rain`, `showers`, `snowfall`; the window is departure to +48 hours (hours 0 to 48, 49 values).
    - **Checkpoint weather:** fetched separately from the heatmap, directly at the checkpoint coordinates (rounded to 2 decimals). Checkpoint counts (3 routes, deduplicated): 351 at 10 miles / 141 at 25 miles / 71 at 50 miles.
    - **Cost of one analysis (Chicago→Denver):** 25-mile interval 141 + 278 = **419 calls** (about 23 analyses/day), 10-mile interval 351 + 278 = **629 calls** (about 15/day). The cache key is (rounded coordinates, window start) with a TTL of about 1 hour. Load weight does not affect weather, so re-analyzing with only a different weight must not call the weather API again.
  - TomTom call spec `[Decision]` (confirmed with real calls on 2026-11-06):
    - Route: `GET /routing/1/calculateRoute/{lat,lon}:{lat,lon}/json` + `travelMode=truck`, `vehicleCommercial=true`, `vehicleWeight=<kg>`, `maxAlternatives=2`, `departAt=<departure>`, `instructionsType=coded`
    - Geocode: `GET /search/2/geocode/{address}.json` + `countrySet=US`, `limit=1`
    - The app's load input is in lb, so convert to kg for TomTom (× 0.45359237). Risk and load rules use the lb value as entered.
    - The route line is `routes[].legs[].points[]` (latitude and longitude only, no time). One Chicago→Denver route is about 10,000 points.
    - `[Interpretation]` ETA: use (`pointIndex`, `routeOffsetInMeters`, `travelTimeInSeconds`) from `guidance.instructions[]` as anchor points and interpolate time between anchors by distance along the route line. The error of this method is verified in Step 4.
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

- [ ] Wind/rain/snow classification functions (section 3)
- [ ] Checkpoint level = highest of the three levels
- [ ] Load rule escalation (section 4)
- [ ] Test: wind boundaries 25, 35, 45, 55 mph and in-between values such as 34.5
- [ ] Test: rain 0.10, 0.25, 0.50, 1.00 and snow 0.5, 1.0, 2.0, 3.0
- [ ] Test: the 3 load rules (including exactly 30,000 lb and 40,000 lb)

### Step 4. Route sampling and ETA

- [ ] Create checkpoints: origin (mile 0), every interval (10/25/50 miles), destination
- [ ] ETA = departure time + cumulative travel time to that point
- [ ] Handle time zones explicitly
- [ ] Compute the miles each checkpoint represents (to the midpoints with its neighbors)
- [ ] Test: sum of represented miles = total route distance
- [ ] Test: routes shorter than the interval and routes not divisible by the interval

### Step 5. Weather lookup at ETA

- [ ] Fetch the forecast for each checkpoint's ETA time (not current weather)
- [ ] Unit conversion: mph, in/hr
- [ ] Batch fetch and cache 48 hours of data
- [ ] Return an error when the ETA is outside the forecast range
- [ ] Test: unit conversion, matching ETA time to forecast time

### Step 6. Route summary and recommendation

- [ ] Compute the route summary: Severe miles, High miles, average risk, travel time
- [ ] Compare the 4 criteria in order (no weighted score, ties decided on rounded values)
- [ ] Exclude No Travel routes, and no recommendation if all 3 are No Travel
- [ ] Generate the one-line recommendation reason
- [ ] Test: cases decided at each of criteria 1, 2, 3, 4
- [ ] Test: some routes No Travel and all routes No Travel

### Step 7. Backend integration and manual verification

- [ ] Integrate Steps 3 to 6 behind the endpoints
- [ ] Error handling: geocoding failure, too few routes, external API outage
- [ ] Pick one real route and compare levels and the recommendation with values computed by hand

### Step 8. Basic screen layout

- [ ] Layout: left panel (input form, route cards) + map on the right
- [ ] Input form: origin, destination, departure time, load weight, sampling interval
- [ ] Show the 3 routes on the map (selected route bold, the others gray)
- [ ] Route cards with 4 numbers: Severe miles / High miles / average risk / duration
- [ ] Show the recommended route and a one-line reason
- [ ] No Travel warning banner

### Step 9. Risk display

- [ ] Draw the route line in risk-colored stretches
- [ ] Always-visible legend
- [ ] Checkpoint markers: ETA, weather at that time, risk level
- [ ] Checkpoint list (timeline)

### Step 10. Heatmap and 0–48 hour slider

- [ ] Receive the 48-hour forecast for the trip-corridor grid in one go
- [ ] Show the heatmap as a WebGL layer
- [ ] Slider hour 0 = departure time `[Decision]`, with the absolute date and time shown next to the slider
- [ ] Moving the slider swaps the layer without calling the API again
- [ ] Sync the slider with the truck's expected position

### Step 11. Performance and final checks

- [ ] Loading and error states
- [ ] Confirm the slider does not stutter
- [ ] Check response time under the heaviest condition (10-mile interval + long route)
- [ ] Re-measure map rendering performance: frame time with 3 routes + heatmap layer + slider interaction (Step 2 baseline: average 17.1ms, p95 17.5ms, 2 frames over 100ms). If possible also check low-end hardware with CPU throttling (DevTools)
- [ ] Review code-splitting the JS bundle (currently 357KB gzip)
- [ ] All unit tests pass

### Step 12. Deployment

- [ ] Decide the hosting location
- [ ] Deploy backend and frontend, set environment variables
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
│   ├── config/                 # settings (loads .env), urls
│   └── trip/                   # API app: pure logic (risk rules, recommendation) + views, tests/
└── frontend/                   # Vite + React + TypeScript + maplibre-gl
    └── src/{components, types}
```

| Purpose | Command (directory) |
|---|---|
| Run backend | `uv run python manage.py runserver` (`backend/`, port 8000) |
| Backend tests | `uv run pytest` (`backend/`) |
| Backend check | `uv run python manage.py check` (`backend/`) |
| Run frontend | `npm run dev` (`frontend/`, port 5173, `/api` is proxied to 8000) |
| Frontend checks | `npm run lint`, `npm run build` (`frontend/`) |

- Environment variables: root `.env` (server-side `TOMTOM_API_KEY`, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`) and frontend `frontend/.env.local` (`VITE_TOMTOM_MAP_KEY`, the map-only key). Never commit either.
- If `VITE_TOMTOM_MAP_KEY` is missing at build time, the map code is dropped from the bundle (with the key, JS is about 1.28MB, 357KB gzip). Always set it for the production build. Bundle size is reviewed in Step 11 (consider code-splitting the map).
- The system has a broken `black`, so `django-admin startproject` prints a `Bad CPU type` error, but the files are created correctly (ignore it).

### Known MapLibre 6 + Vite pitfalls (2026-11-06, all fixed, do not revert)

After touching map code, do not only check the dev server: **also open the production build** (`npm run build` → `npx vite preview` → browser). The dev server was fine while the build was broken once.

1. **Dev server: `Worker failed to load`.** Vite pre-bundles maplibre-gl and looks for the worker file under `.vite/deps/`, which 404s. → `optimizeDeps.exclude: ['maplibre-gl']` in `vite.config.ts`.
2. **Production build: same error.** The worker URL is `new URL('./maplibre-gl-worker.mjs', import.meta.url)` but the build never emits that file. → In `MapView.tsx` import `maplibre-gl/dist/maplibre-gl-worker.mjs?url` and pass it to `setWorkerUrl()`. (The exclude in item 1 alone fixes only the dev server, and `setWorkerUrl` alone does not fix the dev server. Both are needed.)
3. **Map height 0.** `maplibre-gl.css` overrides the container to `position: relative`, which voids `.map { position: absolute; inset: 0 }`. → Raise selector specificity with `.map-area .map` in `index.css`.
