import { describe, expect, it } from 'vitest'
import { checkpoint, route } from '../lib/testData'
import { checkpointDots, placeDots, riskSegments, routeLines, selectedLine } from './geo'

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

describe('selectedLine', () => {
  it('is one line with the route geometry', () => {
    const line = selectedLine(route('B'))
    expect(line.features).toHaveLength(1)
    expect(line.features[0].properties.id).toBe('B')
    expect(line.features[0].geometry.coordinates).toEqual(route('B').geometry)
  })

  it('is empty when no route is selected', () => {
    expect(selectedLine(undefined).features).toEqual([])
  })
})

describe('checkpointDots', () => {
  const rainy = checkpoint({
    index: 1,
    lat: 42.5,
    lon: -88.1,
    level: 'no_travel',
    level_by: { wind: 'low', rain: 'no_travel', snow: 'low' },
    weather: { wind_mph: 5, rain_in_hr: 1.2, snow_in_hr: 0 },
  })
  const calm = checkpoint({ index: 0, lat: 41.88, lon: -87.63, level: 'low' })

  it('puts a marker at each checkpoint as (lon, lat) with its index, level and weather picture', () => {
    const dots = checkpointDots(route('A', { checkpoints: [calm, rainy] }))
    expect(dots.features.map((f) => [f.properties.index, f.properties.level, f.properties.glyph])).toEqual([
      [0, 'low', 'clear'],
      [1, 'no_travel', 'rain'],
    ])
    expect(dots.features[1].geometry.coordinates).toEqual([-88.1, 42.5])
  })

  it('ranks the worst level first, so it is the last to be hidden when markers overlap', () => {
    const levels = ['low', 'moderate', 'high', 'severe', 'no_travel'] as const
    const dots = checkpointDots(route('A', { checkpoints: levels.map((level, index) => checkpoint({ index, level })) }))
    expect(dots.features.map((f) => f.properties.rank)).toEqual([4, 3, 2, 1, 0])
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
