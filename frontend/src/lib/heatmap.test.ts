import { describe, expect, it } from 'vitest'
import type { HeatmapResponse } from '../types/api'
import { forecastHourLabel, heatFeatures, hourProperty, hourTime, pointAlong, truckDescription, truckPosition } from './heatmap'
import { eastwardRoute } from './testData'

function heatmap(points: [number, number][], scoreAt: (hour: number, i: number) => number): HeatmapResponse {
  return {
    start: '2026-11-09T14:00:00Z',
    hours: 49,
    spacing_deg: 0.5,
    points,
    scores: Array.from({ length: 49 }, (_, hour) => points.map((_, i) => scoreAt(hour, i))),
  }
}

describe('heatFeatures', () => {
  const data = heatmap(
    [
      [-90, 40],
      [-89.5, 40],
      [-89, 40.5],
    ],
    (hour, i) => ((hour + i) % 5) + 0.25,
  )

  it('has a point per grid point at its (lon, lat)', () => {
    const { features } = heatFeatures(data)
    expect(features.map((f) => f.geometry.coordinates)).toEqual(data.points)
  })

  it('carries every hour as h0..h48, each equal to scores[hour][i]', () => {
    const { features } = heatFeatures(data)
    features.forEach((feature, i) => {
      expect(Object.keys(feature.properties)).toHaveLength(49)
      for (let hour = 0; hour < 49; hour++) {
        expect(feature.properties[hourProperty(hour)]).toBe(data.scores[hour][i])
      }
    })
  })

  it('names the properties h0 .. h48', () => {
    expect(hourProperty(0)).toBe('h0')
    expect(hourProperty(48)).toBe('h48')
  })

  it('keeps the decimals of a score (they carry the weather within a level)', () => {
    const { features } = heatFeatures(heatmap([[-90, 40]], () => 0.8))
    expect(features[0].properties.h0).toBe(0.8)
    expect(features[0].properties.h48).toBe(0.8)
  })

  it('is empty without points', () => {
    expect(heatFeatures(heatmap([], () => 0)).features).toEqual([])
  })
})

describe('hourTime', () => {
  it('adds whole hours to the start', () => {
    expect(hourTime('2026-11-09T14:00:00Z', 0)).toBe('2026-11-09T14:00:00.000Z')
    expect(hourTime('2026-11-09T14:00:00Z', 12)).toBe('2026-11-10T02:00:00.000Z')
    expect(hourTime('2026-11-09T14:00:00Z', 48)).toBe('2026-11-11T14:00:00.000Z')
  })
})

describe('pointAlong', () => {
  const bent: [number, number][] = [
    [-90, 40],
    [-89, 40], // about 53 miles east
    [-89, 41], // then about 69 miles north
  ]

  it('is the start at 0 and the end at 1', () => {
    expect(pointAlong(bent, 0)).toEqual([-90, 40])
    expect(pointAlong(bent, 1)).toEqual([-89, 41])
  })

  it('goes by length, not by number of points', () => {
    // The first leg is 53 of 122 miles (43%): a fraction of 0.2 is still on the first leg.
    const [lon, lat] = pointAlong(bent, 0.2)
    expect(lat).toBe(40)
    expect(lon).toBeGreaterThan(-90)
    expect(lon).toBeLessThan(-89.4)
    // At 0.8 it is on the second leg.
    const [lon2, lat2] = pointAlong(bent, 0.8)
    expect(lon2).toBe(-89)
    expect(lat2).toBeGreaterThan(40.4)
  })

  it('finds the corner at its share of the length', () => {
    const [lon, lat] = pointAlong(bent, 53.0 / 122.0)
    expect(lon).toBeCloseTo(-89, 1)
    expect(lat).toBeCloseTo(40, 1)
  })

  it('clamps outside 0..1', () => {
    expect(pointAlong(bent, -1)).toEqual([-90, 40])
    expect(pointAlong(bent, 5)).toEqual([-89, 41])
  })

  it('handles a line that does not move', () => {
    expect(pointAlong([[-90, 40], [-90, 40]], 0.5)).toEqual([-90, 40])
  })

  it('refuses an empty line', () => {
    expect(() => pointAlong([], 0.5)).toThrow()
  })
})

describe('truckPosition', () => {
  const route = eastwardRoute([
    { mile: 0, eta: '2026-11-09T12:00:00Z' },
    { mile: 50, eta: '2026-11-09T13:00:00Z' },
    { mile: 100, eta: '2026-11-09T15:00:00Z' },
  ])

  it('waits at the origin before it leaves', () => {
    const status = truckPosition(route, '2026-11-09T11:00:00Z')
    expect(status).toEqual({ kind: 'not_started', departsAt: '2026-11-09T12:00:00Z', position: [-90, 40] })
  })

  it('is still at the origin at the departure moment', () => {
    expect(truckPosition(route, '2026-11-09T12:00:00Z')?.kind).toBe('not_started')
  })

  it('drives: the mile is interpolated between the two checkpoints by time', () => {
    const status = truckPosition(route, '2026-11-09T12:30:00Z')
    expect(status?.kind).toBe('driving')
    if (status?.kind === 'driving') {
      expect(status.mile).toBeCloseTo(25)
      expect(status.totalMiles).toBe(100)
      // a quarter of the way along the line (-90 to -89)
      expect(status.position[0]).toBeCloseTo(-89.75, 5)
      expect(status.position[1]).toBe(40)
    }
  })

  it('uses the speed of the right stretch (50 miles in 1 h, then 50 miles in 2 h)', () => {
    const status = truckPosition(route, '2026-11-09T14:00:00Z')
    if (status?.kind === 'driving') expect(status.mile).toBeCloseTo(75)
    else throw new Error('expected driving')
  })

  it('is exactly at a checkpoint at its ETA', () => {
    const status = truckPosition(route, '2026-11-09T13:00:00Z')
    if (status?.kind === 'driving') expect(status.mile).toBeCloseTo(50)
    else throw new Error('expected driving')
  })

  it('stays at the destination after it arrives', () => {
    expect(truckPosition(route, '2026-11-09T15:00:00Z')).toEqual({
      kind: 'arrived',
      arrivedAt: '2026-11-09T15:00:00Z',
      position: [-89, 40],
    })
    expect(truckPosition(route, '2026-11-11T15:00:00Z')?.kind).toBe('arrived')
  })

  it('does not move while it is stopped (two checkpoints with the same ETA)', () => {
    const stopped = eastwardRoute([
      { mile: 0, eta: '2026-11-09T12:00:00Z' },
      { mile: 50, eta: '2026-11-09T13:00:00Z' },
      { mile: 50, eta: '2026-11-09T13:00:00Z' },
      { mile: 100, eta: '2026-11-09T14:00:00Z' },
    ])
    const status = truckPosition(stopped, '2026-11-09T13:30:00Z')
    if (status?.kind === 'driving') expect(status.mile).toBeCloseTo(75)
    else throw new Error('expected driving')
  })

  it('follows a bent route line by length', () => {
    const bent = eastwardRoute(
      [
        { mile: 0, eta: '2026-11-09T12:00:00Z' },
        { mile: 122, eta: '2026-11-09T14:00:00Z' },
      ],
      [[-90, 40], [-89, 40], [-89, 41]],
    )
    const status = truckPosition(bent, '2026-11-09T13:30:00Z') // 3/4 of the way: on the second leg
    expect(status?.kind).toBe('driving')
    if (status?.kind === 'driving') {
      expect(status.position[0]).toBe(-89)
      expect(status.position[1]).toBeGreaterThan(40.4)
    }
  })

  it('places the truck by its share of the whole route, whatever the total miles are', () => {
    // 200 miles in 4 h: half way in time is half way along the line
    const long = eastwardRoute([
      { mile: 0, eta: '2026-11-09T12:00:00Z' },
      { mile: 200, eta: '2026-11-09T16:00:00Z' },
    ])
    const status = truckPosition(long, '2026-11-09T14:00:00Z')
    expect(status?.kind).toBe('driving')
    if (status?.kind === 'driving') {
      expect(status.mile).toBeCloseTo(100)
      expect(status.totalMiles).toBe(200)
      expect(status.position[0]).toBeCloseTo(-89.5, 5)
    }
  })

  it('has no position for a route with fewer than two checkpoints', () => {
    expect(truckPosition(eastwardRoute([{ mile: 0, eta: '2026-11-09T12:00:00Z' }]), '2026-11-09T12:30:00Z')).toBeNull()
  })

  it('moves forward as the time goes on', () => {
    let last = -1
    for (let minutes = 1; minutes < 180; minutes += 7) {
      const time = new Date(Date.parse('2026-11-09T12:00:00Z') + minutes * 60_000).toISOString()
      const status = truckPosition(route, time)
      if (status?.kind === 'driving') {
        expect(status.mile).toBeGreaterThan(last)
        last = status.mile
      }
    }
    expect(last).toBeGreaterThan(90)
  })
})


describe('truckDescription', () => {
  it('says where the truck is', () => {
    expect(
      truckDescription({ kind: 'driving', mile: 123.6, totalMiles: 206.4, position: [0, 0] }, 'B'),
    ).toBe('Route B: truck at mile 124 of 206')
    expect(
      truckDescription({ kind: 'driving', mile: 123.4, totalMiles: 206.6, position: [0, 0] }, 'B'),
    ).toBe('Route B: truck at mile 123 of 207')
  })

  it('says when it leaves and when it arrived, in the given zone', () => {
    expect(
      truckDescription({ kind: 'not_started', departsAt: '2026-11-09T20:00:00Z', position: [0, 0] }, 'A', 'America/Chicago'),
    ).toBe('Route A: leaves Mon 2:00 PM')
    expect(
      truckDescription({ kind: 'arrived', arrivedAt: '2026-11-10T02:30:00Z', position: [0, 0] }, 'C', 'America/Chicago'),
    ).toBe('Route C: arrived Mon 8:30 PM')
  })
})

describe('forecastHourLabel', () => {
  const start = '2026-11-09T20:00:00Z'

  it('calls hour 0 the departure hour and shows the absolute time', () => {
    expect(forecastHourLabel(start, 0, 'America/Chicago')).toBe('Departure hour · Mon, Nov 9, 2:00 PM CST')
  })

  it('shows the offset and the absolute time for later hours', () => {
    expect(forecastHourLabel(start, 5, 'America/Chicago')).toBe('+5 h · Mon, Nov 9, 7:00 PM CST')
    expect(forecastHourLabel(start, 12, 'America/Chicago')).toBe('+12 h · Tue, Nov 10, 2:00 AM CST')
    expect(forecastHourLabel(start, 48, 'UTC')).toBe('+48 h · Wed, Nov 11, 8:00 PM UTC')
  })

  it('crosses the fall-back date correctly (the zone label changes)', () => {
    // 2026-11-01 07:00 UTC is 2:00 AM CDT; 5 hours later (12:00 UTC) is 6:00 AM CST
    expect(forecastHourLabel('2026-11-01T05:00:00Z', 7, 'America/Chicago')).toBe('+7 h · Sun, Nov 1, 6:00 AM CST')
  })
})
