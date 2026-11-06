// The one-line "why this route" sentence and the No Travel warnings. The backend sends only
// structured values (docs/api-contract.md); the English text is built here.

import type { Checkpoint, Recommendation, Route } from '../types/api'
import { formatAvgRisk, formatDateTime, formatDuration, plural, routeNames } from './format'

function durationDifference(deltaMinutes: number, versusId: string): string {
  if (deltaMinutes === 0) return 'same travel time'
  const amount = formatDuration(Math.abs(deltaMinutes))
  return `${amount} ${deltaMinutes > 0 ? 'slower' : 'faster'} than Route ${versusId}`
}

/** Why the recommended route was chosen, in one line. */
export function recommendationReason(recommendation: Recommendation, routes: readonly Route[]): string {
  const { route_id, decided_by, versus_route_id, duration_delta_minutes } = recommendation
  if (route_id === null || decided_by === null) {
    return 'Every route has a No Travel stretch, so no route is recommended.'
  }
  if (decided_by === 'only_candidate') {
    return routes.length === 1
      ? 'It is the only route available.'
      : 'It is the only route without a No Travel stretch.'
  }

  const winner = routes.find((r) => r.id === route_id)
  const versus = routes.find((r) => r.id === versus_route_id)
  if (!winner || !versus || versus_route_id === null || duration_delta_minutes === null) {
    return 'It has the lowest weather risk.'
  }

  const delta = durationDifference(duration_delta_minutes, versus_route_id)
  const w = winner.summary
  const v = versus.summary
  switch (decided_by) {
    case 'severe_miles':
      return `Fewest severe miles (${w.severe_miles} vs ${v.severe_miles} on Route ${versus.id}), ${delta}.`
    case 'high_miles':
      return `Fewest high miles (${w.high_miles} vs ${v.high_miles} on Route ${versus.id}), ${delta}.`
    case 'avg_risk':
      return (
        `Lowest average risk (${formatAvgRisk(w.avg_risk)} vs ${formatAvgRisk(v.avg_risk)} ` +
        `on Route ${versus.id}), ${delta}.`
      )
    case 'duration':
      return duration_delta_minutes === 0
        ? `Same risk and travel time as Route ${versus.id}.`
        : `Same risk as Route ${versus.id}, ${delta}.`
  }
}

export interface NoTravelWarning {
  routeId: string
  /** First No Travel checkpoint on the route. */
  checkpoint: Checkpoint
  /** Miles of the route at No Travel. */
  miles: number
}

/** The first No Travel checkpoint of every route that has one. */
export function noTravelWarnings(routes: readonly Route[]): NoTravelWarning[] {
  const warnings: NoTravelWarning[] = []
  for (const route of routes) {
    if (!route.summary.has_no_travel) continue
    const checkpoint = route.checkpoints.find((c) => c.level === 'no_travel')
    if (checkpoint) {
      warnings.push({ routeId: route.id, checkpoint, miles: route.summary.miles_by_level.no_travel })
    }
  }
  return warnings
}

/** Headline of the No Travel banner, or null when no route has a No Travel stretch. */
export function noTravelHeadline(routes: readonly Route[]): string | null {
  const blocked = routes.filter((r) => r.summary.has_no_travel).map((r) => r.id)
  if (blocked.length === 0) return null
  if (blocked.length === routes.length) {
    return routes.length === 1
      ? 'No Travel: this route has a stretch you should not drive'
      : 'No Travel on every route'
  }
  return `No Travel on ${routeNames(blocked)}`
}

/** "Route C: near mile 250 at Fri, Nov 6, 1:00 PM CST (heavy load in strong wind)". */
export function describeNoTravel(warning: NoTravelWarning, timeZone?: string): string {
  const { checkpoint } = warning
  const where = `near mile ${Math.round(checkpoint.mile)} at ${formatDateTime(checkpoint.eta, timeZone)}`
  const why = checkpoint.load_escalated ? ' (heavy load in strong wind)' : ''
  return `Route ${warning.routeId}: ${where}${why}`
}

/** "Only 2 routes available for this trip.", or null when all 3 came back. */
export function fewerRoutesNotice(count: number): string | null {
  if (count >= 3) return null
  return `Only ${plural(count, 'route')} available for this trip.`
}
