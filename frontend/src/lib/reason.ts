// The one-line "why this route" sentence and the No Travel warnings. The backend sends only
// structured values (docs/api-contract.md); the English text is built here.

import type { Checkpoint, Recommendation, Route } from '../types/api'
import { distinctPair, formatDateTime, formatDuration, plural, routeNames } from './format'

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
  // `decided_by` compares the recommended route with the runner-up only, so the sentence says
  // "fewer than Route B", not "fewest": a third route can have fewer and still rank lower,
  // because it lost on an earlier criterion.
  switch (decided_by) {
    case 'severe_miles':
      return `Fewer severe miles than Route ${versus.id} (${compared(w.severe_miles, v.severe_miles, 0, 2)}), ${delta}.`
    case 'high_miles':
      return `Fewer high miles than Route ${versus.id} (${compared(w.high_miles, v.high_miles, 0, 2)}), ${delta}.`
    case 'avg_risk':
      return `Lower average risk than Route ${versus.id} (${compared(w.avg_risk, v.avg_risk, 2, 4)}), ${delta}.`
    case 'duration':
      return duration_delta_minutes === 0
        ? `Same risk and travel time as Route ${versus.id}.`
        : `Same risk as Route ${versus.id}, ${delta}.`
  }
}

/** "0 vs 25", "24.6 vs 25.4", or "by a hair: both about 25.44" when even the API's decimals agree. */
function compared(winner: number, versus: number, minDecimals: number, maxDecimals: number): string {
  const [a, b] = distinctPair(winner, versus, minDecimals, maxDecimals)
  return a === b ? `by a hair: both about ${a}` : `${a} vs ${b}`
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
