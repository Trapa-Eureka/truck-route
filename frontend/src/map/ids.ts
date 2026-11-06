// The names of the map's sources and layers, and the fade time, shared by layers.ts and reveal.ts.

export const SOURCE = {
  routes: 'routes',
  risk: 'risk-segments',
  draw: 'draw',
  checkpoints: 'checkpoints',
  places: 'places',
  heat: 'heat',
} as const

export const LAYER = {
  routeHit: 'route-hit',
  routeCasing: 'route-casing',
  routeOther: 'route-other',
  riskLine: 'risk-line',
  routeDraw: 'route-draw',
  checkpoints: 'checkpoints',
  checkpointActive: 'checkpoint-active',
  places: 'places',
} as const

/** How long things fade when the route is revealed (see reveal.ts). */
export const FADE_MS = 450
