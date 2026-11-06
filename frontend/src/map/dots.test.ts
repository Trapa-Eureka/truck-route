import { describe, expect, it } from 'vitest'
import { checkpoint, route } from '../lib/testData'
import { checkpointSpacing, dotPaint, dotRadiusAt, MIN_RADIUS, OTHER_DOT, SELECTED_DOT, spacingPixels } from './dots'

describe('spacingPixels', () => {
  it('is the distance on the ground over the meters one pixel covers', () => {
    // zoom 0 at the equator: one pixel is 78,271.517 m, so 48.6 miles (78,271.5 m) is one pixel
    expect(spacingPixels(78271.517 / 1609.344, 0, 0)).toBeCloseTo(1, 6)
  })

  it('doubles with every zoom level', () => {
    expect(spacingPixels(10, 6, 40) / spacingPixels(10, 5, 40)).toBeCloseTo(2, 9)
  })

  it('is larger away from the equator (the map stretches there)', () => {
    expect(spacingPixels(10, 5, 60)).toBeCloseTo(2 * spacingPixels(10, 5, 0), 6)
  })

  it('grows with the distance', () => {
    expect(spacingPixels(50, 5, 40)).toBeCloseTo(5 * spacingPixels(10, 5, 40), 9)
  })

  it('gives the numbers the sizes were chosen for: 10 miles at zoom 4.5 and latitude 40 is about 6 px', () => {
    expect(spacingPixels(10, 4.5, 40)).toBeGreaterThan(5.5)
    expect(spacingPixels(10, 4.5, 40)).toBeLessThan(6.5)
  })
})

describe('dotRadiusAt', () => {
  it('is the full size where the checkpoints are far apart', () => {
    expect(dotRadiusAt(SELECTED_DOT, 50, 7, 40)).toBe(4)
    expect(dotRadiusAt(SELECTED_DOT, 50, 12, 40)).toBe(6)
    expect(dotRadiusAt(OTHER_DOT, 50, 12, 40)).toBe(4.2)
  })

  it('follows the zoom between the three sizes', () => {
    expect(dotRadiusAt(SELECTED_DOT, null, 3, 40)).toBeCloseTo(2.6, 9)
    expect(dotRadiusAt(SELECTED_DOT, null, 5, 40)).toBeCloseTo(3.3, 9)
    expect(dotRadiusAt(SELECTED_DOT, null, 9.5, 40)).toBeCloseTo(5, 9)
    expect(dotRadiusAt(SELECTED_DOT, null, 7, 40)).toBeCloseTo(4, 9)
    expect(dotRadiusAt(SELECTED_DOT, null, 8, 40)).toBeCloseTo(4.4, 9)
  })

  it('is smaller where the checkpoints are close, so that dots never touch', () => {
    for (const miles of [10, 25, 50]) {
      for (let zoom = 3; zoom <= 12; zoom += 0.5) {
        for (const size of [SELECTED_DOT, OTHER_DOT]) {
          const radius = dotRadiusAt(size, miles, zoom, 40)
          const width = 2 * (radius + Math.min(size.stroke, radius * 0.4))
          // at least a third of the way to the next checkpoint stays free: a line with beads, not a chain
          expect(width).toBeLessThanOrEqual(spacingPixels(miles, zoom, 40) * 0.67)
        }
      }
    }
  })

  it('is a share of the distance to the next checkpoint when that is the smaller', () => {
    const spacing = spacingPixels(10, 5, 40) // about 8.5 px
    expect(dotRadiusAt(SELECTED_DOT, 10, 5, 40)).toBeCloseTo(0.22 * spacing, 1)
    expect(dotRadiusAt(OTHER_DOT, 10, 5, 40)).toBeCloseTo(0.17 * spacing, 1)
  })

  it('leaves the dots out when they would be too small to see as dots', () => {
    expect(dotRadiusAt(SELECTED_DOT, 10, 3, 40)).toBe(0) // 2.1 px apart
    expect(dotRadiusAt(OTHER_DOT, 10, 4, 40)).toBe(0)
    expect(dotRadiusAt(SELECTED_DOT, 10, 4, 40)).toBeGreaterThanOrEqual(MIN_RADIUS)
  })

  it('never is between 0 and the smallest radius', () => {
    for (let zoom = 3; zoom <= 12; zoom += 0.25) {
      const radius = dotRadiusAt(SELECTED_DOT, 10, zoom, 40)
      expect(radius === 0 || radius >= MIN_RADIUS).toBe(true)
    }
  })

  it('never shrinks as the map zooms in', () => {
    for (const miles of [10, 25, 50, null]) {
      let last = 0
      for (let zoom = 3; zoom <= 12; zoom++) {
        const radius = dotRadiusAt(SELECTED_DOT, miles, zoom, 40)
        expect(radius).toBeGreaterThanOrEqual(last)
        last = radius
      }
    }
  })
})

describe('dotPaint', () => {
  it('gives one stop for every zoom level from 3 to 12, in order', () => {
    const { radius, stroke } = dotPaint(SELECTED_DOT, 25, 40)
    expect(radius.slice(0, 3)).toEqual(['interpolate', ['linear'], ['zoom']])
    expect(stroke.slice(0, 3)).toEqual(['interpolate', ['linear'], ['zoom']])
    const zooms = radius.slice(3).filter((_, i) => i % 2 === 0)
    expect(zooms).toEqual([3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
    expect(stroke.slice(3).filter((_, i) => i % 2 === 0)).toEqual(zooms)
  })

  it('uses the radius of each zoom level', () => {
    const { radius } = dotPaint(SELECTED_DOT, 10, 40)
    const values = radius.slice(3).filter((_, i) => i % 2 === 1)
    expect(values).toEqual([3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((zoom) => dotRadiusAt(SELECTED_DOT, 10, zoom, 40)))
  })

  it('gives a full-size dot its full white edge and a small dot a thinner one, none for no dot', () => {
    const value = (stops: unknown[], zoom: number) => stops[3 + (zoom - 3) * 2 + 1]
    const { radius, stroke } = dotPaint(SELECTED_DOT, 10, 40)
    expect(value(stroke, 12)).toBe(1.5)
    expect(value(radius, 3)).toBe(0)
    expect(value(stroke, 3)).toBe(0)
    expect(value(stroke, 5)).toBeCloseTo((value(radius, 5) as number) * 0.4, 1)
    expect(value(stroke, 5) as number).toBeLessThan(1.5)
    expect(value(dotPaint(OTHER_DOT, null, 40).stroke, 12)).toBe(1)
  })
})

describe('checkpointSpacing', () => {
  const at = (mile: number, lat = 40) => checkpoint({ mile, lat })

  it('is the distance between the first two checkpoints: the interval', () => {
    const routes = [route('A', { checkpoints: [at(0), at(25), at(50), at(61)] }), route('B', { checkpoints: [at(0), at(25), at(33)] })]
    expect(checkpointSpacing(routes).miles).toBe(25)
  })

  it('takes the smallest gap if the routes differ, so no route gets dots that touch', () => {
    const routes = [route('A', { checkpoints: [at(0), at(25), at(50)] }), route('B', { checkpoints: [at(0), at(10), at(20)] })]
    expect(checkpointSpacing(routes).miles).toBe(10)
  })

  it('ignores a route shorter than the interval (origin and destination only)', () => {
    const routes = [route('A', { checkpoints: [at(0), at(8)] }), route('B', { checkpoints: [at(0), at(10), at(12)] })]
    expect(checkpointSpacing(routes).miles).toBe(10)
  })

  it('has no spacing when no route has a checkpoint between its ends', () => {
    expect(checkpointSpacing([route('A', { checkpoints: [at(0), at(8)] })]).miles).toBeNull()
    expect(checkpointSpacing([]).miles).toBeNull()
  })

  it('gives the mean latitude of the checkpoints', () => {
    const routes = [route('A', { checkpoints: [at(0, 30), at(10, 40), at(20, 50)] }), route('B', { checkpoints: [at(0, 40)] })]
    expect(checkpointSpacing(routes).latitude).toBe(40)
    expect(checkpointSpacing([]).latitude).toBe(0)
  })
})
