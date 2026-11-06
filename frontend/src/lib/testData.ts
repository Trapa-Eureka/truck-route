// Builders for test data (used by the *.test.ts files only).
import type { Checkpoint, Recommendation, RiskLevel, Route } from '../types/api'

export function checkpoint(overrides: Partial<Checkpoint> = {}): Checkpoint {
  return {
    index: 0,
    mile: 0,
    lat: 41.88,
    lon: -87.63,
    eta: '2026-11-09T14:00:00Z',
    represents_miles: 12.5,
    weather: { wind_mph: 5, rain_in_hr: 0, snow_in_hr: 0 },
    level_by: { wind: 'low', rain: 'low', snow: 'low' },
    level: 'low',
    load_escalated: false,
    ...overrides,
  }
}

interface RouteOptions {
  severe?: number
  high?: number
  avg?: number
  minutes?: number
  noTravelMiles?: number
  checkpoints?: Checkpoint[]
  geometry?: Route['geometry']
}

export function route(id: string, options: RouteOptions = {}): Route {
  const { severe = 0, high = 0, avg = 0, minutes = 600, noTravelMiles = 0, checkpoints = [checkpoint()], geometry } = options
  const miles_by_level: Record<RiskLevel, number> = {
    low: 100,
    moderate: 0,
    high,
    severe,
    no_travel: noTravelMiles,
  }
  return {
    id,
    summary: {
      distance_miles: 100 + high + severe + noTravelMiles,
      duration_minutes: minutes,
      arrival: '2026-11-09T23:00:00Z',
      miles_by_level,
      severe_miles: severe,
      high_miles: high,
      avg_risk: avg,
      has_no_travel: noTravelMiles > 0,
    },
    geometry: geometry ?? [
      [-87.63, 41.88],
      [-87.7, 41.9],
    ],
    segments: [],
    checkpoints,
  }
}

export function recommendation(overrides: Partial<Recommendation> = {}): Recommendation {
  return {
    route_id: 'A',
    decided_by: 'severe_miles',
    versus_route_id: 'B',
    duration_delta_minutes: 20,
    excluded_route_ids: [],
    ranking: ['A', 'B'],
    ...overrides,
  }
}

/** A route going east along 40 degrees north, with checkpoints at the given miles and ETAs. */
export function eastwardRoute(
  stops: { mile: number; eta: string }[],
  geometry: Route['geometry'] = [
    [-90, 40],
    [-89, 40],
  ],
): Route {
  return route('A', {
    checkpoints: stops.map((stop, index) => checkpoint({ index, mile: stop.mile, eta: stop.eta })),
    geometry,
  })
}
