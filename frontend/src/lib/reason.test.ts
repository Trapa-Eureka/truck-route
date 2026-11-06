import { describe, expect, it } from 'vitest'
import {
  describeNoTravel,
  fewerRoutesNotice,
  noTravelHeadline,
  noTravelWarnings,
  recommendationReason,
} from './reason'
import { checkpoint, recommendation, route } from './testData'

describe('recommendationReason', () => {
  it('names the severe miles and the time difference (the contract example)', () => {
    const routes = [route('A', { severe: 25 }), route('B', { severe: 60 })]
    expect(recommendationReason(recommendation(), routes)).toBe(
      'Fewer severe miles than Route B (25 vs 60), 20 min slower than Route B.',
    )
  })

  it('says faster when the recommended route is quicker', () => {
    const routes = [route('A', { severe: 0 }), route('B', { severe: 5 })]
    expect(recommendationReason(recommendation({ duration_delta_minutes: -35 }), routes)).toBe(
      'Fewer severe miles than Route B (0 vs 5), 35 min faster than Route B.',
    )
  })

  it('says same travel time when the difference is zero', () => {
    const routes = [route('A', { severe: 0 }), route('B', { severe: 5 })]
    expect(recommendationReason(recommendation({ duration_delta_minutes: 0 }), routes)).toBe(
      'Fewer severe miles than Route B (0 vs 5), same travel time.',
    )
  })

  it('writes long differences in hours', () => {
    const routes = [route('A', { severe: 0 }), route('B', { severe: 5 })]
    expect(recommendationReason(recommendation({ duration_delta_minutes: 135 }), routes)).toContain(
      '2 h 15 min slower than Route B',
    )
  })

  it('high miles', () => {
    const routes = [route('A', { high: 10 }), route('B', { high: 40 })]
    expect(recommendationReason(recommendation({ decided_by: 'high_miles' }), routes)).toBe(
      'Fewer high miles than Route B (10 vs 40), 20 min slower than Route B.',
    )
  })

  it('average risk with two decimals', () => {
    const routes = [route('B', { avg: 0.1 }), route('A', { avg: 0.11 })]
    const rec = recommendation({
      route_id: 'B',
      versus_route_id: 'A',
      decided_by: 'avg_risk',
      duration_delta_minutes: 26,
    })
    expect(recommendationReason(rec, routes)).toBe(
      'Lower average risk than Route A (0.10 vs 0.11), 26 min slower than Route A.',
    )
  })

  it('shows a decimal when the whole miles read alike', () => {
    // The server compares at full precision: 24.6 beats 25.4 although both are "25" on a card.
    const routes = [route('A', { severe: 24.6 }), route('B', { severe: 25.4 })]
    expect(recommendationReason(recommendation(), routes)).toBe(
      'Fewer severe miles than Route B (24.6 vs 25.4), 20 min slower than Route B.',
    )
  })

  it('shows two decimals when one is not enough, and no more decimals than needed', () => {
    const close = [route('A', { high: 25.41 }), route('B', { high: 25.44 })]
    expect(recommendationReason(recommendation({ decided_by: 'high_miles' }), close)).toContain('(25.41 vs 25.44)')
    const far = [route('A', { high: 0.2 }), route('B', { high: 3.31 })]
    expect(recommendationReason(recommendation({ decided_by: 'high_miles' }), far)).toContain('(0 vs 3)')
  })

  it('shows a short Severe stretch as itself, not as 0 vs 0', () => {
    const routes = [route('A', { severe: 0 }), route('B', { severe: 0.2 })]
    expect(recommendationReason(recommendation(), routes)).toContain('(0.0 vs 0.2)')
  })

  it('shows more decimals of the average risk when two read alike', () => {
    // 15.3 and 44.7 Moderate miles over 3,000: both "0.01" on a card
    const routes = [route('A', { avg: 0.0051 }), route('B', { avg: 0.0149 })]
    expect(recommendationReason(recommendation({ decided_by: 'avg_risk' }), routes)).toBe(
      'Lower average risk than Route B (0.005 vs 0.015), 20 min slower than Route B.',
    )
    const closer = [route('A', { avg: 0.3301 }), route('B', { avg: 0.3304 })]
    expect(recommendationReason(recommendation({ decided_by: 'avg_risk' }), closer)).toContain('(0.3301 vs 0.3304)')
  })

  it('always shows the average risk with at least two decimals, as the cards do', () => {
    const routes = [route('A', { avg: 0.2 }), route('B', { avg: 1.4 })]
    expect(recommendationReason(recommendation({ decided_by: 'avg_risk' }), routes)).toContain('(0.20 vs 1.40)')
  })

  it('says so in words when even the last decimal sent is the same', () => {
    const routes = [route('A', { severe: 25.44 }), route('B', { severe: 25.44 })]
    expect(recommendationReason(recommendation(), routes)).toBe(
      'Fewer severe miles than Route B (by a hair: both about 25.44), 20 min slower than Route B.',
    )
  })

  it('never says fewest or lowest: the comparison is with the runner-up only', () => {
    // Route C has fewer High miles than the winner but lost on Severe miles.
    const routes = [route('A', { high: 10 }), route('B', { high: 20 }), route('C', { high: 0, severe: 5 })]
    const text = recommendationReason(recommendation({ decided_by: 'high_miles' }), routes)
    expect(text).toBe('Fewer high miles than Route B (10 vs 20), 20 min slower than Route B.')
    expect(text).not.toMatch(/fewest|lowest/i)
  })

  it('travel time when everything else ties', () => {
    const routes = [route('A'), route('B')]
    expect(
      recommendationReason(recommendation({ decided_by: 'duration', duration_delta_minutes: -10 }), routes),
    ).toBe('Same risk as Route B, 10 min faster than Route B.')
  })

  it('a complete tie', () => {
    const routes = [route('A'), route('B')]
    expect(
      recommendationReason(recommendation({ decided_by: 'duration', duration_delta_minutes: 0 }), routes),
    ).toBe('Same risk and travel time as Route B.')
  })

  it('only route available', () => {
    const rec = recommendation({ decided_by: 'only_candidate', versus_route_id: null, duration_delta_minutes: null })
    expect(recommendationReason(rec, [route('A')])).toBe('It is the only route available.')
  })

  it('only route without a No Travel stretch', () => {
    const rec = recommendation({
      decided_by: 'only_candidate',
      versus_route_id: null,
      duration_delta_minutes: null,
      excluded_route_ids: ['B', 'C'],
    })
    expect(recommendationReason(rec, [route('A'), route('B', { noTravelMiles: 10 }), route('C', { noTravelMiles: 10 })])).toBe(
      'It is the only route without a No Travel stretch.',
    )
  })

  it('no recommendation', () => {
    const rec = recommendation({
      route_id: null,
      decided_by: null,
      versus_route_id: null,
      duration_delta_minutes: null,
      excluded_route_ids: ['A', 'B'],
      ranking: [],
    })
    expect(recommendationReason(rec, [])).toBe('Every route has a No Travel stretch, so no route is recommended.')
  })

  it('does not crash when the compared route is missing from the list', () => {
    expect(recommendationReason(recommendation({ versus_route_id: 'Z' }), [route('A')])).toBe(
      'It has the lowest weather risk.',
    )
  })
})

describe('noTravelWarnings and headline', () => {
  const blocked = (id: string) =>
    route(id, {
      noTravelMiles: 10,
      checkpoints: [
        checkpoint({ index: 0, mile: 0 }),
        checkpoint({ index: 1, mile: 250, level: 'no_travel', eta: '2026-11-06T19:00:00Z' }),
        checkpoint({ index: 2, mile: 260, level: 'no_travel' }),
      ],
    })

  it('finds the first No Travel checkpoint of each blocked route', () => {
    const warnings = noTravelWarnings([route('A'), blocked('B'), blocked('C')])
    expect(warnings.map((w) => [w.routeId, w.checkpoint.mile, w.miles])).toEqual([
      ['B', 250, 10],
      ['C', 250, 10],
    ])
  })

  it('has none when no route is blocked', () => {
    expect(noTravelWarnings([route('A'), route('B')])).toEqual([])
    expect(noTravelHeadline([route('A'), route('B')])).toBeNull()
  })

  it('headline for some routes', () => {
    expect(noTravelHeadline([route('A'), blocked('B'), blocked('C')])).toBe('No Travel on Routes B and C')
    expect(noTravelHeadline([route('A'), route('B'), blocked('C')])).toBe('No Travel on Route C')
  })

  it('headline for every route', () => {
    expect(noTravelHeadline([blocked('A'), blocked('B'), blocked('C')])).toBe('No Travel on every route')
    expect(noTravelHeadline([blocked('A')])).toBe('No Travel: this route has a stretch you should not drive')
  })

  it('describes where and when', () => {
    const [warning] = noTravelWarnings([blocked('C')])
    expect(describeNoTravel(warning, 'America/Chicago')).toBe('Route C: near mile 250 at Fri, Nov 6, 1:00 PM CST')
  })

  it('mentions the load when it raised the level', () => {
    const heavy = route('B', {
      noTravelMiles: 10,
      checkpoints: [checkpoint({ mile: 80.4, level: 'no_travel', load_escalated: true, eta: '2026-11-06T19:00:00Z' })],
    })
    const [warning] = noTravelWarnings([heavy])
    expect(describeNoTravel(warning, 'UTC')).toBe(
      'Route B: near mile 80 at Fri, Nov 6, 7:00 PM UTC (heavy load in strong wind)',
    )
  })

  it('rounds the mile to the nearest whole mile', () => {
    const at = (mile: number) =>
      noTravelWarnings([
        route('A', { noTravelMiles: 10, checkpoints: [checkpoint({ mile, level: 'no_travel' })] }),
      ])[0]
    expect(describeNoTravel(at(80.6), 'UTC')).toContain('near mile 81 at')
    expect(describeNoTravel(at(80.4), 'UTC')).toContain('near mile 80 at')
  })

  it('skips a route flagged without a No Travel checkpoint rather than crashing', () => {
    const odd = route('A', { noTravelMiles: 10, checkpoints: [checkpoint()] })
    expect(noTravelWarnings([odd])).toEqual([])
  })
})

describe('fewerRoutesNotice', () => {
  it('is empty for three routes', () => {
    expect(fewerRoutesNotice(3)).toBeNull()
  })
  it('says how many there are', () => {
    expect(fewerRoutesNotice(2)).toBe('Only 2 routes available for this trip.')
    expect(fewerRoutesNotice(1)).toBe('Only 1 route available for this trip.')
  })
})
