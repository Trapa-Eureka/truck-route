// Heatmap data and the truck's position at a forecast hour. Pure functions.

import type { Coordinate, HeatmapResponse, Route } from '../types/api'
import { formatDateTime, formatDuration } from './format'
import { formatShortTime } from './checkpoint'

const HOUR_MS = 3600 * 1000

/** The property that holds the level at slider hour `hour`: "h0" ... "h48". */
export const hourProperty = (hour: number) => `h${hour}`

export interface HeatFeature {
  type: 'Feature'
  properties: Record<string, number>
  geometry: { type: 'Point'; coordinates: Coordinate }
}

/**
 * One point per grid point, carrying all its scores (0 to 4) as h0..h48. The whole forecast is
 * loaded into the map once; moving the slider only changes which property the color is read from.
 */
export function heatFeatures(data: HeatmapResponse): { type: 'FeatureCollection'; features: HeatFeature[] } {
  return {
    type: 'FeatureCollection',
    features: data.points.map((coordinates, i) => {
      const properties: Record<string, number> = {}
      for (let hour = 0; hour < data.scores.length; hour++) properties[hourProperty(hour)] = data.scores[hour][i]
      return { type: 'Feature', properties, geometry: { type: 'Point', coordinates } }
    }),
  }
}

/** The moment slider hour `hour` stands for, as ISO 8601 UTC. */
export function hourTime(startIso: string, hour: number): string {
  return new Date(Date.parse(startIso) + hour * HOUR_MS).toISOString()
}

// ---------------------------------------------------------------------------------- the truck

export type TruckStatus =
  | { kind: 'not_started'; departsAt: string; position: Coordinate }
  | { kind: 'driving'; mile: number; totalMiles: number; position: Coordinate }
  | { kind: 'arrived'; arrivedAt: string; position: Coordinate }

function haversineMiles([lon1, lat1]: Coordinate, [lon2, lat2]: Coordinate): number {
  const rad = Math.PI / 180
  const a =
    Math.sin(((lat2 - lat1) * rad) / 2) ** 2 +
    Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(((lon2 - lon1) * rad) / 2) ** 2
  return 2 * 3958.8 * Math.asin(Math.sqrt(a))
}

/** The point `fraction` (0 to 1) of the way along a line, by length. */
export function pointAlong(line: readonly Coordinate[], fraction: number): Coordinate {
  if (line.length === 0) throw new Error('an empty line has no points')
  const lengths = line.slice(1).map((point, i) => haversineMiles(line[i], point))
  const total = lengths.reduce((sum, length) => sum + length, 0)
  if (total === 0 || fraction <= 0) return line[0]
  if (fraction >= 1) return line[line.length - 1]

  let remaining = fraction * total
  for (let i = 0; i < lengths.length; i++) {
    if (remaining <= lengths[i]) {
      const t = lengths[i] === 0 ? 0 : remaining / lengths[i]
      const [lon1, lat1] = line[i]
      const [lon2, lat2] = line[i + 1]
      return [lon1 + (lon2 - lon1) * t, lat1 + (lat2 - lat1) * t]
    }
    remaining -= lengths[i]
  }
  return line[line.length - 1]
}

/**
 * Where the truck is on `route` at `timeIso`. Between two checkpoints the mile is interpolated by
 * time (the checkpoints' ETAs), and the position is that share of the way along the route line.
 * Before the departure it waits at the origin; after the arrival it stays at the destination.
 */
export function truckPosition(route: Route, timeIso: string): TruckStatus | null {
  const { checkpoints, geometry } = route
  if (checkpoints.length < 2 || geometry.length === 0) return null

  const time = Date.parse(timeIso)
  const first = checkpoints[0]
  const last = checkpoints[checkpoints.length - 1]
  if (time <= Date.parse(first.eta)) {
    return { kind: 'not_started', departsAt: first.eta, position: geometry[0] }
  }
  if (time >= Date.parse(last.eta)) {
    return { kind: 'arrived', arrivedAt: last.eta, position: geometry[geometry.length - 1] }
  }

  // The last checkpoint reached by `time`. The next one is later: it was passed over because its ETA
  // is after `time` (the last one too, from the check above), so the span below is never zero.
  let i = checkpoints.length - 2
  while (Date.parse(checkpoints[i].eta) > time) i--
  const from = checkpoints[i]
  const to = checkpoints[i + 1]
  const share = (time - Date.parse(from.eta)) / (Date.parse(to.eta) - Date.parse(from.eta))
  const mile = from.mile + share * (to.mile - from.mile)
  return {
    kind: 'driving',
    mile,
    totalMiles: last.mile,
    position: pointAlong(geometry, mile / last.mile),
  }
}

/** "Route B: truck at mile 123 of 207", "Route B: leaves Fri 2:00 PM", "Route B: arrived Fri 5:25 PM". */
export function truckDescription(status: TruckStatus, routeId: string, timeZone?: string): string {
  switch (status.kind) {
    case 'not_started':
      return `Route ${routeId}: leaves ${formatShortTime(status.departsAt, timeZone)}`
    case 'driving':
      return `Route ${routeId}: truck at mile ${Math.round(status.mile)} of ${Math.round(status.totalMiles)}`
    case 'arrived':
      return `Route ${routeId}: arrived ${formatShortTime(status.arrivedAt, timeZone)}`
  }
}

/** "Hour 12 · Sat, Nov 7, 2:00 AM GMT+8"; hour 0 is the departure hour. */
export function forecastHourLabel(startIso: string, hour: number, timeZone?: string): string {
  const when = formatDateTime(hourTime(startIso, hour), timeZone)
  return hour === 0 ? `Departure hour · ${when}` : `+${formatDuration(hour * 60)} · ${when}`
}

/** What the heatmap request is doing. */
export type HeatmapStatus =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'done'; data: HeatmapResponse }
