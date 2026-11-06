import type { ExpressionSpecification, LineLayerSpecification, Map as MapLibreMap } from 'maplibre-gl'
import { OTHER_ROUTE_COLOR, RISK_COLORS, RISK_LEVELS } from '../lib/risk'
import { checkpointDots, placeDots, riskSegments, routeLines, selectedLine } from './geo'
import { heatColor, heatLayerId, heatRadius } from './heat'
import { FADE_MS, LAYER, SOURCE } from './ids'
import { DRAW_COLOR, drawGradient, OUTLINE_OPACITY, prefersReducedMotion } from './reveal'

/** `['match', ['get', 'level'], 'low', '#...', ..., fallback]` from the shared palette. */
function levelColor(): ExpressionSpecification {
  const pairs = RISK_LEVELS.flatMap((level) => [level, RISK_COLORS[level]])
  return ['match', ['get', 'level'], ...pairs, OTHER_ROUTE_COLOR] as unknown as ExpressionSpecification
}

const fade = { duration: FADE_MS, delay: 0 }
/** How long one forecast hour fades into the next on the heatmap. */
export const HEAT_FADE_MS = 280

/**
 * Line widths follow the zoom: thin, as in ref/route_ref_line.png, thinner when zoomed out and a bit
 * thicker close up. The white outline is a little wider than the line, so it only edges it.
 */
const widthAtZoom = (z3: number, z7: number, z12: number) =>
  ['interpolate', ['linear'], ['zoom'], 3, z3, 7, z7, 12, z12] as unknown as ExpressionSpecification
const ROUTE_WIDTH = widthAtZoom(2.5, 4, 6)
const OUTLINE_WIDTH = widthAtZoom(4.5, 6.5, 8.5)
const OTHER_WIDTH = widthAtZoom(2, 3, 4.5)

/**
 * Adds the empty sources and the layers, bottom to top: click target, white outline of the
 * selected route, the other routes in gray, the selected route in risk colors, the dark line that
 * is drawn while the route is revealed, the weather markers, the ring around the active marker,
 * origin and destination. Every line is solid. (The truck and the origin and destination labels
 * are HTML markers: see MapView.)
 *
 * They are drawn above the base map: under its label layer the base map's roads covered them.
 * The weather markers need their images in the map first (markers.ts).
 */
export function addRouteLayers(map: MapLibreMap): void {
  map.addSource(SOURCE.routes, { type: 'geojson', data: routeLines([], null) })
  map.addSource(SOURCE.risk, { type: 'geojson', data: riskSegments(undefined) })
  // lineMetrics gives every point its distance along the line, which the reveal animation needs.
  map.addSource(SOURCE.draw, { type: 'geojson', lineMetrics: true, data: selectedLine(undefined) })
  map.addSource(SOURCE.checkpoints, { type: 'geojson', data: checkpointDots(undefined) })
  map.addSource(SOURCE.places, { type: 'geojson', data: placeDots(null, null) })
  map.addSource(SOURCE.heat, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })

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
    filter: ['get', 'selected'],
    layout: roundLine,
    paint: { 'line-color': '#ffffff', 'line-width': OUTLINE_WIDTH, 'line-opacity': OUTLINE_OPACITY, 'line-opacity-transition': fade },
  })
  map.addLayer({
    id: LAYER.routeOther,
    type: 'line',
    source: SOURCE.routes,
    filter: ['!', ['get', 'selected']],
    layout: roundLine,
    paint: {
      'line-color': OTHER_ROUTE_COLOR,
      'line-width': OTHER_WIDTH,
      'line-opacity': 1,
      'line-opacity-transition': fade,
    },
  })
  // Butt caps, so one level ends where the next begins with no overlap.
  map.addLayer({
    id: LAYER.riskLine,
    type: 'line',
    source: SOURCE.risk,
    layout: { 'line-join': 'round', 'line-cap': 'butt' },
    paint: { 'line-color': levelColor(), 'line-width': ROUTE_WIDTH, 'line-opacity': 1, 'line-opacity-transition': fade },
  })
  map.addLayer({
    id: LAYER.routeDraw,
    type: 'line',
    source: SOURCE.draw,
    layout: roundLine,
    paint: {
      'line-color': DRAW_COLOR,
      'line-gradient': drawGradient(0) as unknown as ExpressionSpecification,
      'line-width': ROUTE_WIDTH,
      'line-opacity': 0,
      'line-opacity-transition': fade,
    },
  })
  map.addLayer({
    id: LAYER.checkpoints,
    type: 'symbol',
    source: SOURCE.checkpoints,
    layout: {
      'icon-image': ['concat', 'wx-', ['get', 'level'], '-', ['get', 'glyph']],
      // Smaller when zoomed out, full size close up.
      'icon-size': ['interpolate', ['linear'], ['zoom'], 3, 0.5, 6, 0.65, 9, 0.85, 12, 1],
      // Where two markers would overlap, only one is shown: the worse level wins (`rank`).
      'icon-allow-overlap': false,
      'icon-padding': 2,
      'symbol-sort-key': ['get', 'rank'],
    },
    paint: { 'icon-opacity': 1, 'icon-opacity-transition': fade },
  })
  map.addLayer({
    id: LAYER.checkpointActive,
    type: 'circle',
    source: SOURCE.checkpoints,
    filter: ['==', ['get', 'index'], -1],
    paint: {
      'circle-radius': 20,
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
      'circle-radius': 6,
      'circle-color': '#1a2530',
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 3,
    },
  })
}

/**
 * Adds one circle layer per forecast hour, under every route line, each reading its own hour's
 * level (`h0` ... `h48`) and all hidden. The slider then only switches a constant opacity.
 *
 * Why not one layer whose colour reads property `h<hour>` and changes on every slider step? A
 * colour that depends on the feature's properties is baked into the map's tile buffers, so
 * changing it makes the map rebuild the source's tiles in its worker each time: measured as the
 * main cost of a slider step on a slow CPU. A constant opacity is a plain uniform, and a layer at
 * opacity 0 is not drawn at all.
 */
export function addHeatLayers(map: MapLibreMap, hours: number, spacingDeg: number, latitude: number): void {
  const radius = heatRadius(spacingDeg, latitude) as ExpressionSpecification
  for (let hour = 0; hour < hours; hour++) {
    map.addLayer(
      {
        id: heatLayerId(hour),
        type: 'circle',
        source: SOURCE.heat,
        paint: {
          'circle-radius': radius,
          'circle-blur': 1,
          'circle-color': heatColor(hour) as ExpressionSpecification,
          'circle-opacity': 0,
          // A slider step fades the old hour out while the new one fades in, so the zones change
          // smoothly instead of jumping. (Both layers are drawn for that moment only.)
          'circle-opacity-transition': { duration: prefersReducedMotion() ? 0 : HEAT_FADE_MS, delay: 0 },
        },
      },
      LAYER.routeHit,
    )
  }
}

export function removeHeatLayers(map: MapLibreMap, hours: number): void {
  for (let hour = 0; hour < hours; hour++) {
    if (map.getLayer(heatLayerId(hour))) map.removeLayer(heatLayerId(hour))
  }
}
