// The names of the map's sources and layers, and the fade time, shared by layers.ts and reveal.ts.

export const SOURCE = {
  routes: 'routes',
  risk: 'risk-segments',
  draw: 'draw',
  dots: 'route-dots',
  checkpoints: 'checkpoints',
  places: 'places',
  heat: 'heat',
} as const

export const LAYER = {
  routeHit: 'route-hit',
  otherCasing: 'other-casing',
  riskOther: 'risk-other',
  otherDots: 'other-dots',
  routeCasing: 'route-casing',
  riskLine: 'risk-line',
  routeDraw: 'route-draw',
  checkpointDots: 'checkpoint-dots',
  checkpoints: 'checkpoints',
  checkpointActive: 'checkpoint-active',
  places: 'places',
} as const

/** How long things fade when the route is revealed (see reveal.ts). */
export const FADE_MS = 450
