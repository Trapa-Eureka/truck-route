import { describe, expect, it } from 'vitest'
import { checkpoint, route } from '../lib/testData'
import { checkpointDots, placeDots, riskSegments, routeLines } from './geo'

describe('routeLines', () => {
  it('has one line per route, flagging the selected one', () => {
    const lines = routeLines([route('A'), route('B'), route('C')], 'B')
    expect(lines.features.map((f) => [f.properties.id, f.properties.selected])).toEqual([
      ['A', false],
      ['B', true],
      ['C', false],
    ])
  })

  it('selects nothing when there is no selection', () => {
    expect(routeLines([route('A')], null).features[0].properties.selected).toBe(false)
  })

  it('uses the route geometry as it is (lon, lat)', () => {
    const [feature] = routeLines([route('A')], 'A').features
    expect(feature.geometry).toEqual({ type: 'LineString', coordinates: route('A').geometry })
  })

  it('is empty without routes', () => {
    expect(routeLines([], null).features).toEqual([])
  })
})

describe('riskSegments', () => {
  it('has one line per segment, with its level', () => {
    const r = {
      ...route('A'),
      segments: [
        { level: 'low' as const, coordinates: [[0, 0], [1, 1]] as [number, number][] },
        { level: 'severe' as const, coordinates: [[1, 1], [2, 2]] as [number, number][] },
      ],
    }
    const collection = riskSegments(r)
    expect(collection.features.map((f) => f.properties.level)).toEqual(['low', 'severe'])
    expect(collection.features[1].geometry.coordinates).toEqual([[1, 1], [2, 2]])
  })

  it('is empty when no route is selected', () => {
    expect(riskSegments(undefined).features).toEqual([])
  })
})

describe('checkpointDots', () => {
  it('puts a dot at each checkpoint as (lon, lat) with its index and level', () => {
    const r = route('A', {
      checkpoints: [
        checkpoint({ index: 0, lat: 41.88, lon: -87.63, level: 'low' }),
        checkpoint({ index: 1, lat: 42.5, lon: -88.1, level: 'no_travel' }),
      ],
    })
    const dots = checkpointDots(r)
    expect(dots.features.map((f) => f.properties)).toEqual([
      { index: 0, level: 'low' },
      { index: 1, level: 'no_travel' },
    ])
    expect(dots.features[1].geometry.coordinates).toEqual([-88.1, 42.5])
  })

  it('is empty when no route is selected', () => {
    expect(checkpointDots(undefined).features).toEqual([])
  })
})

describe('placeDots', () => {
  const place = (lat: number, lon: number) => ({ query: 'q', label: 'l', lat, lon })

  it('has an origin and a destination dot', () => {
    const dots = placeDots(place(1, 2), place(3, 4))
    expect(dots.features.map((f) => [f.properties.kind, f.geometry.coordinates])).toEqual([
      ['origin', [2, 1]],
      ['destination', [4, 3]],
    ])
  })

  it('skips a missing place', () => {
    expect(placeDots(null, null).features).toEqual([])
    expect(placeDots(place(1, 2), null).features).toHaveLength(1)
  })
})
