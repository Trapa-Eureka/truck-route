import type { ExpressionSpecification, LineLayerSpecification, Map as MapLibreMap } from 'maplibre-gl'
import { OTHER_ROUTE_COLOR, RISK_COLORS, RISK_LEVELS } from '../lib/risk'
import { dotPaint, OTHER_DOT, SELECTED_DOT } from './dots'
import { checkpointDots, placeDots, riskSegments, routeDots, routeLines, selectedLine } from './geo'
import { heatColor, heatLayerId, heatRadius } from './heat'
import { FADE_MS, LAYER, SOURCE } from './ids'
import {
  DRAW_COLOR,
  drawGradient,
  OTHER_DOT_OPACITY,
  OTHER_OPACITY,
  OTHER_OUTLINE_OPACITY,
  OUTLINE_OPACITY,
  prefersReducedMotion,
} from './reveal'

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
 * thicker close up. The white outline is a little wider than the line, so it only edges it. The
 * routes that are not selected are thinner still.
 */
const widthAtZoom = (z3: number, z7: number, z12: number) =>
  ['interpolate', ['linear'], ['zoom'], 3, z3, 7, z7, 12, z12] as unknown as ExpressionSpecification
const ROUTE_WIDTH = widthAtZoom(2.5, 4, 6)
const OUTLINE_WIDTH = widthAtZoom(4.5, 6.5, 8.5)
const OTHER_WIDTH = widthAtZoom(1.8, 2.6, 4)
const OTHER_OUTLINE_WIDTH = widthAtZoom(3.2, 4.4, 6)
/** Checkpoint dots, before any route is known: full size (see dots.ts and `sizeDots`). */
const DOT_RADIUS = widthAtZoom(...SELECTED_DOT.base)
const OTHER_DOT_RADIUS = widthAtZoom(...OTHER_DOT.base)

const SELECTED: ExpressionSpecification = ['get', 'selected']
const NOT_SELECTED: ExpressionSpecification = ['!', ['get', 'selected']]

/**
 * Adds the empty sources and the layers, bottom to top:
 *
 * - the click target (wide, invisible);
 * - the routes that are not selected: a white outline, the line in risk colors (thin and pale)
 *   and a small dot at every checkpoint;
 * - the selected route: a white outline, the line in risk colors, the dark line that is drawn
 *   while the route is revealed, and a dot at every checkpoint;
 * - the weather markers of the selected route (left out where they would overlap; the dot under
 *   a marker that is left out still shows the checkpoint), the ring around the active one;
 * - origin and destination.
 *
 * Every line is solid. (The truck and the origin and destination labels are HTML markers: see
 * MapView.) They are drawn above the base map: under its label layer the base map's roads covered
 * them. The weather markers need their images in the map first (markers.ts).
 */
export function addRouteLayers(map: MapLibreMap): void {
  map.addSource(SOURCE.routes, { type: 'geojson', data: routeLines([], null) })
  map.addSource(SOURCE.risk, { type: 'geojson', data: riskSegments([], null) })
  // lineMetrics gives every point its distance along the line, which the reveal animation needs.
  map.addSource(SOURCE.draw, { type: 'geojson', lineMetrics: true, data: selectedLine(undefined) })
  map.addSource(SOURCE.dots, { type: 'geojson', data: routeDots([], null) })
  map.addSource(SOURCE.checkpoints, { type: 'geojson', data: checkpointDots(undefined) })
  map.addSource(SOURCE.places, { type: 'geojson', data: placeDots(null, null) })
  map.addSource(SOURCE.heat, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })

  const roundLine: LineLayerSpecification['layout'] = { 'line-join': 'round', 'line-cap': 'round' }
  // Butt caps, so one level ends where the next begins with no overlap.
  const buttLine: LineLayerSpecification['layout'] = { 'line-join': 'round', 'line-cap': 'butt' }

  // A wide invisible line: makes thin routes easy to click.
  map.addLayer({
    id: LAYER.routeHit,
    type: 'line',
    source: SOURCE.routes,
    layout: roundLine,
    paint: { 'line-width': 18, 'line-opacity': 0 },
  })

  // ---- the routes that are not selected
  map.addLayer({
    id: LAYER.otherCasing,
    type: 'line',
    source: SOURCE.routes,
    filter: NOT_SELECTED,
    layout: roundLine,
    paint: {
      'line-color': '#ffffff',
      'line-width': OTHER_OUTLINE_WIDTH,
      'line-opacity': OTHER_OUTLINE_OPACITY,
      'line-opacity-transition': fade,
    },
  })
  map.addLayer({
    id: LAYER.riskOther,
    type: 'line',
    source: SOURCE.risk,
    filter: NOT_SELECTED,
    layout: buttLine,
    paint: { 'line-color': levelColor(), 'line-width': OTHER_WIDTH, 'line-opacity': OTHER_OPACITY, 'line-opacity-transition': fade },
  })
  map.addLayer({
    id: LAYER.otherDots,
    type: 'circle',
    source: SOURCE.dots,
    filter: NOT_SELECTED,
    paint: {
      'circle-radius': OTHER_DOT_RADIUS,
      'circle-color': levelColor(),
      'circle-opacity': OTHER_DOT_OPACITY,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 1,
      'circle-stroke-opacity': OTHER_DOT_OPACITY,
      'circle-opacity-transition': fade,
      'circle-stroke-opacity-transition': fade,
    },
  })

  // ---- the selected route
  map.addLayer({
    id: LAYER.routeCasing,
    type: 'line',
    source: SOURCE.routes,
    filter: SELECTED,
    layout: roundLine,
    paint: { 'line-color': '#ffffff', 'line-width': OUTLINE_WIDTH, 'line-opacity': OUTLINE_OPACITY, 'line-opacity-transition': fade },
  })
  map.addLayer({
    id: LAYER.riskLine,
    type: 'line',
    source: SOURCE.risk,
    filter: SELECTED,
    layout: buttLine,
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
    id: LAYER.checkpointDots,
    type: 'circle',
    source: SOURCE.dots,
    filter: SELECTED,
    paint: {
      'circle-radius': DOT_RADIUS,
      'circle-color': levelColor(),
      'circle-opacity': 1,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 1.5,
      'circle-stroke-opacity': 1,
      'circle-opacity-transition': fade,
      'circle-stroke-opacity-transition': fade,
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
      // Where two markers would overlap, only one is shown: the worse level wins (`rank`). The
      // checkpoint that loses its picture keeps its dot (the layer below).
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
 * Sizes the checkpoint dots for these routes: full size where the checkpoints are far apart on
 * screen, smaller where they are close, so the dots never run together (dots.ts).
 */
export function sizeDots(map: MapLibreMap, spacingMiles: number | null, latitude: number): void {
  for (const [layer, size] of [
    [LAYER.checkpointDots, SELECTED_DOT],
    [LAYER.otherDots, OTHER_DOT],
  ] as const) {
    const { radius, stroke } = dotPaint(size, spacingMiles, latitude)
    map.setPaintProperty(layer, 'circle-radius', radius as ExpressionSpecification)
    map.setPaintProperty(layer, 'circle-stroke-width', stroke as ExpressionSpecification)
  }
}

/**
 * Adds one circle layer per forecast hour, under every route line, each reading its own hour's
 * weather score (`h0` ... `h48`) and all hidden. The slider then only switches a constant opacity.
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
