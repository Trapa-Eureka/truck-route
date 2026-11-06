// Style expressions for the heatmap layer. Pure functions that build MapLibre expressions.

import { hourProperty } from '../lib/heatmap'
import { RISK_COLORS } from '../lib/risk'

type Expression = unknown[]

/** The id of the layer that draws slider hour `hour`. */
export const heatLayerId = (hour: number) => `heat-${hour}`

function rgbOf(hex: string): [number, number, number] {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16))
  return [r, g, b]
}

/** A point on the shading scale: from this score on, this color and strength (until the next stop). */
export interface HeatStop {
  /** 0 (calm) to 4 (No Travel). The whole numbers are where the risk levels start. */
  score: number
  rgb: [number, number, number]
  /** How opaque the shading is (0 to 1). */
  alpha: number
}

/**
 * The shading scale, a continuous ramp over the score (0 to 4):
 * - 0 to 1, "Low": nothing for calm weather, then blue, teal, green and lime as the weather picks
 *   up, and a yellow-green just before Moderate. This quarter of the scale is where almost all of a
 *   calm day lies (measured: 99% of the values under 0.7, and a change of 0.03 per hour), so it
 *   gets five color steps and a clear strength: a small change in the weather is a visible change
 *   of color, not just of transparency.
 * - 1 to 4: the levels' own colors (yellow, orange, red, purple), reached exactly at their score
 *   (1, 2, 3, 4), and growing stronger. A color for the start of a level is the same as on the route.
 */
export const HEAT_STOPS: readonly HeatStop[] = [
  { score: 0, rgb: [111, 168, 220], alpha: 0 },
  { score: 0.15, rgb: [96, 176, 238], alpha: 0.38 },
  { score: 0.35, rgb: [40, 184, 190], alpha: 0.46 },
  { score: 0.55, rgb: rgbOf(RISK_COLORS.low), alpha: 0.5 },
  { score: 0.8, rgb: [142, 198, 56], alpha: 0.52 },
  { score: 0.97, rgb: [205, 200, 50], alpha: 0.54 },
  { score: 1, rgb: rgbOf(RISK_COLORS.moderate), alpha: 0.56 },
  { score: 2, rgb: rgbOf(RISK_COLORS.high), alpha: 0.62 },
  { score: 3, rgb: rgbOf(RISK_COLORS.severe), alpha: 0.69 },
  { score: 4, rgb: rgbOf(RISK_COLORS.no_travel), alpha: 0.76 },
]

const rgbaOf = ({ rgb: [r, g, b], alpha }: HeatStop, strength = 1) =>
  `rgba(${r}, ${g}, ${b}, ${Math.min(1, +(alpha * strength).toFixed(3))})`

/**
 * Colour of a point at slider hour `hour`: read the score from property `h<hour>` and find its
 * place on the scale (`HEAT_STOPS`). Colour and strength are one expression, so a slider step is
 * one style update, not two.
 */
export function heatColor(hour: number): Expression {
  return ['interpolate', ['linear'], ['get', hourProperty(hour)], ...HEAT_STOPS.flatMap((stop) => [stop.score, rgbaOf(stop)])]
}

/**
 * The same scale as a CSS gradient for the legend, left (0) to right (4). The map's shading is
 * see-through, so the legend uses a stronger version (`strength` times the alpha) to be readable.
 */
export function heatRampCss(strength = 1): string {
  const stops = HEAT_STOPS.map((stop) => `${rgbaOf(stop, strength)} ${(stop.score / 4) * 100}%`)
  return `linear-gradient(to right, ${stops.join(', ')})`
}

const METERS_PER_DEGREE = 111_195
/**
 * The circle radius as a share of the grid spacing. Rows are a full spacing apart north-south but
 * closer east-west (a degree of longitude is shorter away from the equator), so a radius under
 * about 0.9 spacings leaves visible stripes between the rows.
 */
export const HEAT_RADIUS_SHARE = 1.3
/** Meters per pixel at zoom 0 on the equator (512 px tiles). */
const METERS_PER_PIXEL_Z0 = 78_271.517
/** Above this zoom the circles stop growing: a grid of 34 miles means little at street level. */
const MAX_GROWTH_ZOOM = 12

/**
 * Radius of each heat circle so neighbouring circles overlap and blend into a continuous
 * surface. It is a share of the grid spacing in meters, turned into pixels at zoom 0 and doubled
 * for every zoom level (exponential base 2), so the shading keeps its size on the ground.
 */
export function heatRadius(spacingDeg: number, latitude: number): Expression {
  const meters = HEAT_RADIUS_SHARE * spacingDeg * METERS_PER_DEGREE
  const atZoom0 = meters / (METERS_PER_PIXEL_Z0 * Math.cos((latitude * Math.PI) / 180))
  const atMax = atZoom0 * 2 ** MAX_GROWTH_ZOOM
  return ['interpolate', ['exponential', 2], ['zoom'], 0, atZoom0, MAX_GROWTH_ZOOM, atMax, 22, atMax]
}
