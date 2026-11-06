// Style expressions for the heatmap layer. Pure functions that build MapLibre expressions.

import { HEAT_OPACITY, RISK_COLORS, RISK_LEVELS } from '../lib/risk'
import { hourProperty } from '../lib/heatmap'

type Expression = unknown[]

/** Colour of a point at slider hour `hour`: the palette entry for the level in property `h<hour>`. */
export function heatColor(hour: number): Expression {
  const pairs = RISK_LEVELS.flatMap((level, index) => [index, RISK_COLORS[level]])
  return ['match', ['get', hourProperty(hour)], ...pairs, RISK_COLORS.low]
}

/** Strength of the shading at slider hour `hour`: faint for Low, stronger as the level rises. */
export function heatOpacity(hour: number): Expression {
  const pairs = HEAT_OPACITY.flatMap((opacity, index) => [index, opacity])
  return ['match', ['get', hourProperty(hour)], ...pairs, HEAT_OPACITY[0]]
}

const METERS_PER_DEGREE = 111_195
/**
 * The circle radius as a share of the grid spacing. Rows are a full spacing apart north-south but
 * closer east-west (a degree of longitude is shorter away from the equator), so a radius under
 * about 0.9 spacings leaves visible stripes between the rows.
 */
export const HEAT_RADIUS_SHARE = 0.9
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
