import type { ExpressionSpecification, LineLayerSpecification, Map as MapLibreMap } from 'maplibre-gl'
import { OTHER_ROUTE_COLOR, RISK_COLORS, RISK_LEVELS } from '../lib/risk'
import { checkpointDots, placeDots, riskSegments, routeLines } from './geo'

export const SOURCE = {
  routes: 'routes',
  risk: 'risk-segments',
  checkpoints: 'checkpoints',
  places: 'places',
} as const

export const LAYER = {
  routeHit: 'route-hit',
  routeCasing: 'route-casing',
  routeOther: 'route-other',
  riskLine: 'risk-line',
  checkpoints: 'checkpoints',
  checkpointActive: 'checkpoint-active',
  places: 'places',
} as const

/** `['match', ['get', 'level'], 'low', '#...', ..., fallback]` from the shared palette. */
function levelColor(): ExpressionSpecification {
  const pairs = RISK_LEVELS.flatMap((level) => [level, RISK_COLORS[level]])
  return ['match', ['get', 'level'], ...pairs, OTHER_ROUTE_COLOR] as unknown as ExpressionSpecification
}

/**
 * Adds the empty sources and the layers, bottom to top:
 * click target, white outline, gray other routes, the selected route in risk colors,
 * checkpoint dots, the ring around the active checkpoint, origin and destination.
 * They are drawn above the base map: under its label layer the base map's roads covered them.
 */
export function addRouteLayers(map: MapLibreMap): void {
  map.addSource(SOURCE.routes, { type: 'geojson', data: routeLines([], null) })
  map.addSource(SOURCE.risk, { type: 'geojson', data: riskSegments(undefined) })
  map.addSource(SOURCE.checkpoints, { type: 'geojson', data: checkpointDots(undefined) })
  map.addSource(SOURCE.places, { type: 'geojson', data: placeDots(null, null) })

  const roundLine: LineLayerSpecification['layout'] = { 'line-join': 'round', 'line-cap': 'round' }

  // A wide invisible line: makes thin gray routes easy to click.
  map.addLayer({
    id: LAYER.routeHit,
    type: 'line',
    source: SOURCE.routes,
    layout: roundLine,
    paint: { 'line-width': 18, 'line-opacity': 0 },
  })
  map.addLayer({
    id: LAYER.routeCasing,
    type: 'line',
    source: SOURCE.routes,
    layout: roundLine,
    paint: {
      'line-color': '#ffffff',
      'line-width': ['case', ['get', 'selected'], 12, 7],
      'line-opacity': 0.95,
    },
  })
  map.addLayer({
    id: LAYER.routeOther,
    type: 'line',
    source: SOURCE.routes,
    filter: ['!', ['get', 'selected']],
    layout: roundLine,
    paint: { 'line-color': OTHER_ROUTE_COLOR, 'line-width': 4 },
  })
  // Butt caps, so one level ends where the next begins with no overlap.
  map.addLayer({
    id: LAYER.riskLine,
    type: 'line',
    source: SOURCE.risk,
    layout: { 'line-join': 'round', 'line-cap': 'butt' },
    paint: { 'line-color': levelColor(), 'line-width': 8 },
  })
  map.addLayer({
    id: LAYER.checkpoints,
    type: 'circle',
    source: SOURCE.checkpoints,
    paint: {
      'circle-radius': 6,
      'circle-color': levelColor(),
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 2,
    },
  })
  map.addLayer({
    id: LAYER.checkpointActive,
    type: 'circle',
    source: SOURCE.checkpoints,
    filter: ['==', ['get', 'index'], -1],
    paint: {
      'circle-radius': 12,
      'circle-color': '#ffffff',
      'circle-opacity': 0,
      'circle-stroke-color': '#1a2530',
      'circle-stroke-width': 3,
    },
  })
  map.addLayer({
    id: LAYER.places,
    type: 'circle',
    source: SOURCE.places,
    paint: {
      'circle-radius': 8,
      'circle-color': ['match', ['get', 'kind'], 'origin', '#1f8f4d', '#c23b2b'],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 3,
    },
  })
}
