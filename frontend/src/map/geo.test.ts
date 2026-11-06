import { describe, expect, it } from 'vitest'
import { checkpoint, route } from '../lib/testData'
import { checkpointDots, placeDots, riskSegments, routeDots, routeLines, routeToSelect, selectedLine } from './geo'

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
  const cut = (id: string, levels: ('low' | 'severe' | 'high')[]) => ({
    ...route(id),
    segments: levels.map((level, i) => ({ level, coordinates: [[i, i], [i + 1, i + 1]] as [number, number][] })),
  })

  it('has one line per segment, with its level', () => {
    const collection = riskSegments([cut('A', ['low', 'severe'])], 'A')
    expect(collection.features.map((f) => f.properties.level)).toEqual(['low', 'severe'])
    expect(collection.features[1].geometry.coordinates).toEqual([[1, 1], [2, 2]])
    expect(collection.features[1].geometry.type).toBe('LineString')
  })

  it('has the segments of every route, each with its route and whether that route is selected', () => {
    const collection = riskSegments([cut('A', ['low', 'severe']), cut('B', ['high']), cut('C', ['low'])], 'B')
    expect(collection.features.map((f) => [f.properties.id, f.properties.level, f.properties.selected])).toEqual([
      ['A', 'low', false],
      ['A', 'severe', false],
      ['B', 'high', true],
      ['C', 'low', false],
    ])
  })

  it('marks nothing as selected without a selection', () => {
    expect(riskSegments([cut('A', ['low'])], null).features[0].properties.selected).toBe(false)
  })

  it('is empty without routes', () => {
    expect(riskSegments([], null).features).toEqual([])
  })
})

describe('routeDots', () => {
  const a = route('A', {
    checkpoints: [checkpoint({ index: 0, level: 'low' }), checkpoint({ index: 1, level: 'severe', lat: 42.5, lon: -88.1 })],
  })
  const b = route('B', { checkpoints: [checkpoint({ index: 0, level: 'moderate' })] })

  it('has a dot for every checkpoint of every route: none is left out', () => {
    const dots = routeDots([a, b], 'A')
    expect(dots.features.map((f) => [f.properties.id, f.properties.index, f.properties.level, f.properties.selected])).toEqual([
      ['A', 0, 'low', true],
      ['A', 1, 'severe', true],
      ['B', 0, 'moderate', false],
    ])
  })

  it('puts each dot at its checkpoint as (lon, lat)', () => {
    const dots = routeDots([a, b], 'A')
    expect(dots.features[1].geometry).toEqual({ type: 'Point', coordinates: [-88.1, 42.5] })
  })

  it('follows the selection', () => {
    expect(routeDots([a, b], 'B').features.map((f) => f.properties.selected)).toEqual([false, false, true])
    expect(routeDots([a, b], null).features.map((f) => f.properties.selected)).toEqual([false, false, false])
  })

  it('is empty without routes', () => {
    expect(routeDots([], null).features).toEqual([])
  })
})

describe('routeToSelect', () => {
  it('chooses the route that was clicked', () => {
    expect(routeToSelect(['B'], 'A')).toBe('B')
    expect(routeToSelect(['C'], null)).toBe('C')
  })

  it('keeps the selected route where routes share a road and the click hits several', () => {
    expect(routeToSelect(['B', 'A'], 'A')).toBeNull()
    expect(routeToSelect(['A', 'B', 'C'], 'C')).toBeNull()
    expect(routeToSelect(['A'], 'A')).toBeNull()
  })

  it('takes the first route when the selected one is not under the pointer', () => {
    expect(routeToSelect(['B', 'C'], 'A')).toBe('B')
    expect(routeToSelect(['C', 'B'], null)).toBe('C')
  })

  it('changes nothing when no route is under the pointer', () => {
    expect(routeToSelect([], 'A')).toBeNull()
    expect(routeToSelect([undefined, 7, null], 'A')).toBeNull()
  })

  it('skips what is not a route id', () => {
    expect(routeToSelect([undefined, 'B'], 'A')).toBe('B')
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
