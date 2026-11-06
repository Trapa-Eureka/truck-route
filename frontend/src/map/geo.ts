// GeoJSON for the map, built from the API's routes. Pure functions: no map library needed,
// so they are easy to test.

import { RISK_LEVELS } from '../lib/risk'
import { weatherGlyph, type WeatherGlyph } from '../lib/weatherIcon'
import type { Checkpoint, Coordinate, ResolvedPlace, RiskLevel, Route } from '../types/api'

export interface Feature<P, G> {
  type: 'Feature'
  properties: P
  geometry: G
}

export interface Collection<P, G> {
  type: 'FeatureCollection'
  features: Feature<P, G>[]
}

type Line = { type: 'LineString'; coordinates: Coordinate[] }
type Point = { type: 'Point'; coordinates: Coordinate }

/** Every route as one line. `selected` picks the style; the lines are also what a click hits. */
export function routeLines(
  routes: readonly Route[],
  selectedId: string | null,
): Collection<{ id: string; selected: boolean }, Line> {
  return {
    type: 'FeatureCollection',
    features: routes.map((route) => ({
      type: 'Feature',
      properties: { id: route.id, selected: route.id === selectedId },
      geometry: { type: 'LineString', coordinates: route.geometry },
    })),
  }
}

/** The selected route cut where the risk level changes, one line per level. */
export function riskSegments(route: Route | undefined): Collection<{ level: RiskLevel }, Line> {
  return {
    type: 'FeatureCollection',
    features: (route?.segments ?? []).map((segment) => ({
      type: 'Feature',
      properties: { level: segment.level },
      geometry: { type: 'LineString', coordinates: segment.coordinates },
    })),
  }
}

/** The selected route as one line (one feature, so the map can draw it growing from the origin). */
export function selectedLine(route: Route | undefined): Collection<{ id: string }, Line> {
  return {
    type: 'FeatureCollection',
    features: route
      ? [{ type: 'Feature', properties: { id: route.id }, geometry: { type: 'LineString', coordinates: route.geometry } }]
      : [],
  }
}

/**
 * The selected route's checkpoints, as markers: colored by level, with the weather picture.
 * `rank` is the placement priority when markers would overlap (0 is placed first): the worst
 * levels are never the ones that get hidden.
 */
export function checkpointDots(
  route: Route | undefined,
): Collection<{ index: number; level: RiskLevel; glyph: WeatherGlyph; rank: number }, Point> {
  return {
    type: 'FeatureCollection',
    features: (route?.checkpoints ?? []).map((checkpoint: Checkpoint) => ({
      type: 'Feature',
      properties: {
        index: checkpoint.index,
        level: checkpoint.level,
        glyph: weatherGlyph(checkpoint),
        rank: RISK_LEVELS.length - 1 - RISK_LEVELS.indexOf(checkpoint.level),
      },
      geometry: { type: 'Point', coordinates: [checkpoint.lon, checkpoint.lat] },
    })),
  }
}

/** The origin and the destination. */
export function placeDots(
  origin: ResolvedPlace | null,
  destination: ResolvedPlace | null,
): Collection<{ kind: 'origin' | 'destination' }, Point> {
  const features: Collection<{ kind: 'origin' | 'destination' }, Point>['features'] = []
  if (origin) {
    features.push({ type: 'Feature', properties: { kind: 'origin' }, geometry: { type: 'Point', coordinates: [origin.lon, origin.lat] } })
  }
  if (destination) {
    features.push({ type: 'Feature', properties: { kind: 'destination' }, geometry: { type: 'Point', coordinates: [destination.lon, destination.lat] } })
  }
  return { type: 'FeatureCollection', features }
}
