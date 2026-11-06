# Loom Walkthrough Script

About 8 minutes at a slow pace. Read the numbers on your screen in place of the parts in `[ ]`.

## 0:00–0:30 · Intro

**Screen**: The first screen of the deployed app (the form and an empty map).

1. Hello. This is my truck route app for the Spotter test.
2. It helps a truck driver pick the safest route.
3. It looks at three things: weather, load weight, and travel time.
4. The front end is React. The back end is Django.
5. The routes come from TomTom. The weather comes from Open-Meteo.

## 0:30–1:15 · Input

**Screen**: Clear the To field, type "Denver" to show the list, and choose it → departure time → weight 42000 → interval 25 mi → click `Analyze routes`.

6. First, I type the start and the end of the trip.
7. As I type, the app shows a list of places.
8. Next, I set the date and time to leave.
9. Then I enter the load weight in pounds.
10. Last, I choose how often to check the weather: every 10, 25, or 50 miles.
11. I pick 25 miles and click Analyze.

## 1:15–2:05 · Three Routes

**Screen**: Loading → the map zooms to the routes and the line is drawn → three cards. Click the Route B card, then go back to Route A.

12. Now the back end asks TomTom for three truck routes.
13. Then it puts checkpoints on each route and gets the weather for all of them.
14. Here are the three routes. Each line shows its risk by color.
15. The route I picked is thick. The other two are thin.
16. Each card shows four numbers: Severe miles, High miles, average risk, and travel time.
17. This bar shows how many miles are at each risk level.
18. I can click a card or a line to see another route.

## 2:05–3:00 · Checkpoints and Weather at Arrival Time

**Screen**: Click one weather icon on the map → popup. Scroll the left panel down to the checkpoint list → click a row → `Load more`.

19. Each dot on the route is a checkpoint.
20. I click one. It shows when the truck will get there.
21. This is not the weather now. It is the weather at that time.
22. I see wind, rain, and snow. Each one has a risk level.
23. The checkpoint takes the highest level of the three.
24. The same checkpoints are in this list on the left.
25. I click a row, and the map moves to that point.
26. The arrival times come from TomTom's travel time data.

## 3:00–3:50 · Risk Rules and Load Rules

**Screen**: Point at the legend → change the interval to 10 mi and click `Analyze routes` again → the map with more dots.

27. The risk levels come from the table in the task: Low, Moderate, High, Severe, and No Travel.
28. A heavy load makes strong wind more dangerous.
29. For example: wind of 45 miles per hour, with a load over 30,000 pounds, means No Travel.
30. The load rules only make the level go up. They never make it go down.
31. Now I change to 10 miles and click Analyze again.
32. There are more checkpoints now, so the app can find a small storm.
33. The app counts miles of road, not the number of checkpoints.

## 3:50–4:45 · Recommendation Reason

**Screen**: The green recommendation card at the top of the left panel and the `Recommended` badge.

34. The app picks one route and tells me why in one line.
35. It checks four things in order.
36. One: fewer Severe miles. Two: fewer High miles. Three: lower average risk. Four: shorter travel time.
37. It uses the next rule only if the routes are equal.
38. So I do not mix them into one score.
39. (On a calm day) Today the weather is calm. All routes have the same risk. So time decides. Route [A] is [two and a half hours] faster than Route [B].
40. (On a day with weather, in place of line 39) Today Route [B] wins. It has lower [average risk], but it is [26 minutes] slower.
41. If a route has a No Travel part, the app does not pick it. It shows a big warning.

## 4:45–5:45 · Heatmap and 0–48 Hour Slider

**Screen**: Drag the slider under the map slowly to the end and back → zoom and move the map while dragging → point at the date and time next to the slider and the truck position text.

42. These colors on the map are the weather heat map.
43. The slider goes from 0 to 48 hours. Hour zero is the time I leave.
44. The date and time are shown next to the slider.
45. When I move it, I can see the weather change and move.
46. The colors use the same risk levels as the routes.
47. This dark dot is the truck at that hour.
48. The app loads all 48 hours one time. So the slider does not call the server.
49. It stays smooth, even when I move and zoom the map.

## 5:45–6:25 · Error Handling

**Screen**: Change the departure date to three weeks from now and click `Analyze routes` → error message → set the departure date back.

50. The app does not guess when there is no data.
51. I pick a date three weeks from now. There is no weather data that far.
52. So the app shows a clear message. It tells me the last date I can use.
53. No data is never counted as zero. Zero would make a bad road look safe.
54. A wrong address or a past time also gets a clear message.

## 6:25–7:25 · Code and Tests

**Screen**: In the editor, `backend/trip/risk.py` → `backend/trip/recommend.py` → the terminal with the test results.

55. All the rules are in the Django back end. The front end only shows the result.
56. Each rule is a small function. Weather and load go in. A risk level comes out.
57. So it is easy to test each number in the table, like 25 miles per hour or 30,000 pounds.
58. This file picks the best route. It checks the four things in order.
59. I have about 1,500 back end tests and 350 front end tests.
60. I also checked one real route with a second script. Every number was the same.
61. The API keys stay on the server. The app also limits how many requests one user can send.

## 7:25–7:55 · Docs and Closing

**Screen**: Scroll the "Rule interpretations and assumptions" part of `README.md` → go back to the app.

62. Some things are not in the task. I wrote my choices in the README.
63. For example, I use normal wind speed, not gusts.
64. I put correct results and a clear screen first, before extra features.
65. Thank you for watching.
