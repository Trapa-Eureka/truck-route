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

- **Map**: a quiet gray base map that shows the 3 routes together, **all of them in the risk colors**: each line changes color by risk level along its length. The selected route is bold and is drawn from the origin to the destination (a short animation); the other routes are thinner and paler. **Every checkpoint of every route is a dot** in its level's color. On the selected route a checkpoint also carries a weather picture (calm, light rain, rain, snow, wind) in a white circle with a ring in the risk color; where pictures would overlap (a long route seen whole) some are left out, the worse level staying, and the dot under them remains. On a very long route seen whole the dots themselves get smaller and finally give way to the line, which is cut at every checkpoint's stretch and shows each one's level by its color. The legend is always visible, and the map keeps the routes clear of the legend, the trip bar and the slider when it zooms to them.
- **Route cards**: each route shows only 4 numbers: `Severe mi`, `High mi`, `Avg risk`, `Duration`. Under them a thin bar and one line say where the route's miles are by level ("All Low along the route", or "Low 980 mi · Moderate 26 mi"). A stretch shorter than half a mile shows as "<1", never as 0.
- **Recommendation reason**: the recommended route shows its reason in one line, compared with the runner-up (for example "Fewer severe miles than Route B (0 vs 25), 20 min slower than Route B.").
- **Checkpoints**: each checkpoint shows its estimated arrival time (ETA), the weather at that time, and its risk level. Click one on the map or in the list: wind, rain and snow appear as three picture tiles with their values and levels. The list shows the first 10 checkpoints, with `Load more` and `Show all`.
- **No Travel warning**: if a route has a No Travel stretch, a large warning banner is shown.
- **Forecast slider**: moving the 0–48 hour slider changes the weather heatmap and the truck's expected position on the map together. Hour 0 is the departure hour (the departure rounded to the nearest hour) and the date and time of the chosen hour are shown next to the slider. The whole 48 hours are loaded once, so moving the slider never calls the server.

## Rule interpretations and assumptions

Where the assignment document is silent, these choices were made.

**Inputs**

- Places are in the **United States only**. The From / To fields list matching places, addresses and cities while you type (from 3 characters), and a button fills the field from the browser's position. A text that was typed and not chosen from the list resolves to its **first match**; the name it resolved to is shown, so a wrong match is visible. A place outside the US is refused, also when the request is built by hand.
- All times on screen are in **the browser's time zone** (it is named next to the form and the checkpoint list); the API works in UTC.
- A departure up to 5 minutes in the past is accepted, because a form that says "now" is already a few seconds old when it arrives. Anything earlier is refused.
- If the origin and the destination are the same place, the request is refused.
- The routing service promises "up to 3" routes. If it returns fewer, the app shows exactly those and says so ("Only 2 routes available for this trip."); it never invents a route.
- Requests are limited per client address (6 analyses a minute and 60 a day), because every analysis spends free-tier quota that all visitors share. Over the limit the app says how long to wait.

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
- The interval decides how finely the weather is sampled, so the numbers can differ between intervals: a storm 15 miles wide can fall between two 50-mile checkpoints and be caught at 10 miles. 10 miles is the most precise and the slowest.
- **An ETA assumes non-stop driving.** It is the departure time plus the routing service's travel time to that point (truck speeds and, for a departure close to now, live traffic); rest breaks and fuel stops are not modelled, and the weather does not slow the truck. On a trip of more than a day the later ETAs are therefore optimistic.

**Route recommendation**

- The 4 criteria are compared in order, and the next criterion is used only when the previous one is tied. They are never blended into a weighted score.
- Severe miles, High miles and average risk are compared **as computed, not as rounded for the screen**: 24.6 Severe miles beats 25.4 although a card shows 25 for both, and the reason line then shows the decimals ("24.6 vs 25.4"). Travel time is compared in whole minutes. Travel time still decides often, because on a calm day every route has exactly 0 Severe miles, 0 High miles and an average of 0. If two routes tie on everything, the route the routing service listed first wins.
- A route with any No Travel stretch is excluded from the recommendation. If all 3 routes have one, no route is recommended and the reason is shown.

**Weather forecast**

- Weather is forecast-based, not real-time. Each checkpoint's weather is looked up for the truck's estimated arrival time.
- The forecast comes in whole hours. **Wind** is a value at an instant, so a checkpoint uses the hour **nearest to its estimated arrival** (exactly on the half hour goes to the later hour). **Rain and snow** are amounts over an hour, so a checkpoint uses the hour **that contains its arrival**: for an arrival at 12:20, the rain that falls from 12:00 to 13:00 (inches per hour).
- Rain is the forecast's rain plus showers. Snow is the depth of fresh snow in inches, not its water equivalent.
- The forecast reaches about 15 days ahead. No latest departure is imposed: a trip is refused only when an hour it needs is past the end of the forecast, and the message says until when the forecast is available.
- Missing forecast data is **never treated as 0**. If the needed time is past the end of the forecast, or the weather service fails, the app shows an error instead of a risk level.
- Heatmap slider hour 0 is the departure time (rounded to the nearest hour). The date and time are shown next to the slider so it is clear which moment the forecast is for.
- The heatmap shows **the same risk scale as the routes**, continuously: the worst of wind, rain and snow placed between the table's thresholds, load rules included, on a grid of points about 34 miles apart within 40 miles of the routes. It is the weather at the slider's hour everywhere at once, while a route's colors are the weather when the truck reaches each point, so the two answer different questions and can differ at the same place.

## Tech stack

- Frontend: React + TypeScript (Vite) + MapLibre (WebGL map)
- Backend: Django + Django REST Framework (no Django admin: the PDF asks for none and the backend stores no data)
- External APIs (third-party)
  - Routing and places: [TomTom](https://developer.tomtom.com/) Routing API (truck mode) and Search API (Fuzzy Search for the From / To list and for typed text, reverse geocoding for "my location")
  - Weather forecast: [Open-Meteo](https://open-meteo.com/) (CC BY 4.0)

## Documentation

- [CLAUDE.md](./CLAUDE.md): detailed requirements and implementation rules
- [docs/api-contract.md](./docs/api-contract.md): API contract between the backend and the frontend
