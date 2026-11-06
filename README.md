# Spotter — Weather-Aware Truck Routing

[한국어](./README.ko.md)

A web app (React + Django) that helps a truck driver choose the safest route based on **weather, load weight, and travel time**.

## What the app does

1. **Takes input**: origin/destination, departure date and time, and load weight.
2. **Generates 3 routes**: creates 3 alternative routes with a routing API.
3. **Checks the weather along each route**: splits the route every 10 / 25 / 50 miles and fetches the weather (wind, rain, snow) for **the truck's estimated arrival time** at each point.
4. **Rates the risk**: classifies the weather as `Low / Moderate / High / Severe / No Travel`, and raises the risk level in high-wind stretches when the load is heavier.
5. **Recommends the best route**: compares the routes in the order below and recommends the safest one.
   1. Fewest Severe miles
   2. Fewest High miles
   3. Lowest average risk
   4. Shortest travel time
6. **Shows it on a map**: all routes, checkpoints, risk levels, estimated arrival times (ETAs), and route summaries are shown on the map, and a **weather heatmap** along the route can be explored with a **0–48 hour forecast slider**.

## Risk rules at a glance

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind | < 25 mph | 25–34 | 35–44 | 45–54 | ≥ 55 mph |
| Rain | < 0.10 in/hr | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow | < 0.5 in/hr | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

Load rules:

- Wind ≥ 55 mph → **No Travel** for any load
- Wind 45–54 mph + load > 30,000 lb → **No Travel**
- Wind 35–44 mph + load > 40,000 lb → **Severe**

## Screen layout

- **Map**: shows the 3 routes together. The selected route is bold and the others gray. The route line changes color by risk level along its length, and the legend is always visible.
- **Route cards**: each route shows only 4 numbers: `Severe mi`, `High mi`, `Avg risk`, `Duration`.
- **Recommendation reason**: the recommended route shows its reason in one line (for example "0 severe miles, 20 min slower than Route B").
- **Checkpoints**: each checkpoint shows its estimated arrival time (ETA), the weather at that time, and its risk level.
- **No Travel warning**: if a route has a No Travel stretch, a large warning banner is shown.
- **Forecast slider**: moving the 0–48 hour slider changes the weather heatmap and the truck's expected position on the map together. Hour 0 is the departure hour (the departure rounded to the nearest hour) and the date and time of the chosen hour are shown next to the slider. The whole 48 hours are loaded once, so moving the slider never calls the server.

## Rule interpretations and assumptions

Where the assignment document is silent, these choices were made.

**Inputs**

- Addresses are looked up in the United States only, and the **first match** is used. The name it resolved to is shown, so a wrong match is visible (for example "Toronto, Canada" resolves to Toronto, Kansas).
- A departure up to 5 minutes in the past is accepted, because a form that says "now" is already a few seconds old when it arrives. Anything earlier is refused.
- If the origin and the destination are the same place, the request is refused.

**Risk levels**

- A checkpoint's level is the **highest** of its wind, rain, and snow levels. The load rules only raise this level, never lower it.
- Wind means sustained wind speed. Gusts are not used.
- The wind table uses whole-number ranges, which leaves values like 34.5 mph undefined. It is read as `below 25 / 25 up to (not including) 35 / 35 up to 45 / 45 up to 55 / 55 and above`.
- In the rain and snow tables, values where range ends overlap (rain 0.25 and 0.50, snow 1.0 and 2.0) go to the higher level. No Travel applies only when the value is strictly greater than the limit, as written (rain 1.00 and snow 3.0 are Severe).

**Checkpoints and miles per level**

- The user chooses the sampling interval (10 / 25 / 50 miles). The default is 25 miles.
- Checkpoints are placed at the origin (mile 0), at every sampling interval, and at the destination.
- **Severe and High miles are computed from the stretch length between checkpoints, not from the number of checkpoints.** Each checkpoint stands for the stretch from the midpoint to its previous checkpoint to the midpoint to its next checkpoint, and that length is added to the checkpoint's level. The miles of all levels add up to the route's total distance.
- Average risk is the stretch-length-weighted average after converting levels to numbers (Low 0, Moderate 1, High 2, Severe 3, No Travel 4).

**Route recommendation**

- The 4 criteria are compared in order, and the next criterion is used only when the previous one is tied. They are never blended into a weighted score.
- Ties are decided on the values shown on screen (miles to 1 mile, average risk to 2 decimals, travel time to the minute), rounding halves up (24.5 miles shows as 25). If two routes tie on everything, the route the routing service listed first wins.
- A route with any No Travel stretch is excluded from the recommendation. If all 3 routes have one, no route is recommended and the reason is shown.

**Weather forecast**

- Weather is forecast-based, not real-time. Each checkpoint's weather is looked up for the truck's estimated arrival time.
- A checkpoint uses the forecast for the **hour nearest to its estimated arrival** (exactly on the half hour goes to the later hour). Wind is the value at that hour; rain and snow are the amounts in the preceding hour, in inches per hour.
- Missing forecast data is **never treated as 0**. If the needed time is past the end of the forecast, or the weather service fails, the app shows an error instead of a risk level.
- Heatmap slider hour 0 is the departure time. The date and time are shown next to the slider so it is clear which moment the forecast is for.
- If an estimated arrival time falls outside the weather forecast range, the value is not estimated and an error is shown.

## Tech stack

- Frontend: React + TypeScript (Vite) + MapLibre (WebGL map)
- Backend: Django + Django REST Framework
- External APIs (third-party)
  - Routing and geocoding: [TomTom](https://developer.tomtom.com/) Routing API (truck mode) and Geocoding API
  - Weather forecast: [Open-Meteo](https://open-meteo.com/) (CC BY 4.0)

## Documentation

- [CLAUDE.md](./CLAUDE.md): detailed requirements and implementation rules
- [docs/api-contract.md](./docs/api-contract.md): API contract between the backend and the frontend
