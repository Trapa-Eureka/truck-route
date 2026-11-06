// How big the checkpoint dots are. Every checkpoint of every route has a dot, and a dot must stay a
// dot: on a long route with 10-mile checkpoints the dots are a few pixels apart when the whole trip
// is on screen, and dots of a fixed size would touch and turn the solid route line into a string of
// beads. So a dot is never wider than a share of the distance to the next one, and that distance
// doubles with every zoom level. When even that is too small to draw (under about four pixels
// between checkpoints) the dots are left out: the line itself is cut at every checkpoint's stretch
// and shows each one's level by its color.

import type { Route } from '../types/api'
import { METERS_PER_PIXEL_Z0 } from './heat'

const METERS_PER_MILE = 1609.344
const MIN_ZOOM = 3
const MAX_ZOOM = 12
/** A dot narrower than this is not drawn. */
export const MIN_RADIUS = 0.8
/** The white edge of a dot, as a share of its radius, and its largest width. */
const STROKE_SHARE = 0.4

export interface DotSize {
  /** Radius in pixels at zoom 3, 7 and 12 when the checkpoints are far apart. */
  base: readonly [number, number, number]
  /** The radius is at most this share of the distance to the next checkpoint. */
  share: number
  /** Width of the white edge of a full-size dot. */
  stroke: number
}

export const SELECTED_DOT: DotSize = { base: [2.6, 4, 6], share: 0.22, stroke: 1.5 }
export const OTHER_DOT: DotSize = { base: [1.8, 2.8, 4.2], share: 0.17, stroke: 1 }

/** Pixels between two checkpoints that are `miles` apart, at this zoom and latitude. */
export function spacingPixels(miles: number, zoom: number, latitude: number): number {
  const metersPerPixel = (METERS_PER_PIXEL_Z0 * Math.cos((latitude * Math.PI) / 180)) / 2 ** zoom
  return (miles * METERS_PER_MILE) / metersPerPixel
}

function baseRadius([z3, z7, z12]: DotSize['base'], zoom: number): number {
  if (zoom <= 7) return z3 + ((z7 - z3) * (zoom - MIN_ZOOM)) / (7 - MIN_ZOOM)
  return z7 + ((z12 - z7) * (zoom - 7)) / (MAX_ZOOM - 7)
}

/** The radius of a dot at one zoom level: full size, or less where the checkpoints are close; 0 when too close. */
export function dotRadiusAt(size: DotSize, spacingMiles: number | null, zoom: number, latitude: number): number {
  const full = baseRadius(size.base, zoom)
  if (spacingMiles === null) return full
  const radius = Math.min(full, size.share * spacingPixels(spacingMiles, zoom, latitude))
  return radius < MIN_RADIUS ? 0 : Math.round(radius * 100) / 100
}

/**
 * `circle-radius` and `circle-stroke-width` as map expressions over the zoom, one stop per zoom
 * level. (A map expression may read the zoom only at its top level, so "the smaller of two zoom
 * curves" cannot be written in it; the stops are worked out here instead.)
 */
export function dotPaint(size: DotSize, spacingMiles: number | null, latitude: number): { radius: unknown[]; stroke: unknown[] } {
  const radius: unknown[] = ['interpolate', ['linear'], ['zoom']]
  const stroke: unknown[] = ['interpolate', ['linear'], ['zoom']]
  for (let zoom = MIN_ZOOM; zoom <= MAX_ZOOM; zoom++) {
    const r = dotRadiusAt(size, spacingMiles, zoom, latitude)
    radius.push(zoom, r)
    stroke.push(zoom, Math.round(Math.min(size.stroke, r * STROKE_SHARE) * 100) / 100)
  }
  return { radius, stroke }
}

/**
 * How far apart the checkpoints are (the interval the user chose) and where, for the dot sizes:
 * the distance between the first two checkpoints of the routes (the last gap of a route is
 * shorter) and the mean latitude. Null spacing when no route has two checkpoints.
 */
export function checkpointSpacing(routes: readonly Route[]): { miles: number | null; latitude: number } {
  const gaps = routes.filter((route) => route.checkpoints.length > 2).map((route) => route.checkpoints[1].mile - route.checkpoints[0].mile)
  const positive = gaps.filter((gap) => gap > 0)
  const lats = routes.flatMap((route) => route.checkpoints.map((checkpoint) => checkpoint.lat))
  return {
    miles: positive.length > 0 ? Math.min(...positive) : null,
    latitude: lats.length > 0 ? lats.reduce((sum, lat) => sum + lat, 0) / lats.length : 0,
  }
}
