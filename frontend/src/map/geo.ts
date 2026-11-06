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

/**
 * Every route cut where the risk level changes, one line per stretch of one level. All routes are
 * drawn in the risk colors (the selected one bold, the others thin and pale), so the weather on
 * the routes can be compared on the map without choosing each one in turn.
 */
export function riskSegments(
  routes: readonly Route[],
  selectedId: string | null,
): Collection<{ id: string; level: RiskLevel; selected: boolean }, Line> {
  return {
    type: 'FeatureCollection',
    features: routes.flatMap((route) =>
      route.segments.map((segment) => ({
        type: 'Feature' as const,
        properties: { id: route.id, level: segment.level, selected: route.id === selectedId },
        geometry: { type: 'LineString' as const, coordinates: segment.coordinates },
      })),
    ),
  }
}

/**
 * Every checkpoint of every route as a small dot in its level's color. The dots are plain map
 * circles, so none is ever left out: the weather pictures (`checkpointDots`) are thinned where
 * they would overlap, and the dot under a picture that was left out still marks the checkpoint.
 */
export function routeDots(
  routes: readonly Route[],
  selectedId: string | null,
): Collection<{ id: string; index: number; level: RiskLevel; selected: boolean }, Point> {
  return {
    type: 'FeatureCollection',
    features: routes.flatMap((route) =>
      route.checkpoints.map((checkpoint) => ({
        type: 'Feature' as const,
        properties: { id: route.id, index: checkpoint.index, level: checkpoint.level, selected: route.id === selectedId },
        geometry: { type: 'Point' as const, coordinates: [checkpoint.lon, checkpoint.lat] as Coordinate },
      })),
    ),
  }
}

/**
 * Which route a click on the map chooses, given the routes under the pointer, or null to leave
 * the selection alone. Routes share stretches of road (all of them near the origin and the
 * destination), and there the click hits several: it must not jump away from the selected route.
 */
export function routeToSelect(hitIds: readonly unknown[], selectedId: string | null): string | null {
  const ids = hitIds.filter((id): id is string => typeof id === 'string')
  if (ids.length === 0 || (selectedId !== null && ids.includes(selectedId))) return null
  return ids[0]
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
 * The selected route's checkpoints, as weather markers: a ring in the level's color and the picture.
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
