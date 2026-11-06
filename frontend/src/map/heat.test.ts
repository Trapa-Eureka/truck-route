import { describe, expect, it } from 'vitest'
import { HEAT_OPACITY, RISK_COLORS, RISK_LEVELS } from '../lib/risk'
import { HEAT_RADIUS_SHARE, heatColor, heatOpacity, heatRadius } from './heat'

describe('heatColor', () => {
  it('reads the level from the property of that hour', () => {
    expect(heatColor(7).slice(0, 2)).toEqual(['match', ['get', 'h7']])
    expect(heatColor(0)[1]).toEqual(['get', 'h0'])
    expect(heatColor(48)[1]).toEqual(['get', 'h48'])
  })

  it('maps level 0 to 4 to the palette in order', () => {
    const expression = heatColor(3)
    RISK_LEVELS.forEach((level, index) => {
      expect(expression[2 + index * 2]).toBe(index)
      expect(expression[3 + index * 2]).toBe(RISK_COLORS[level])
    })
  })

  it('has a fallback (Low) for an unexpected value', () => {
    const expression = heatColor(3)
    expect(expression[expression.length - 1]).toBe(RISK_COLORS.low)
  })
})

describe('heatOpacity', () => {
  it('is stronger for higher levels', () => {
    expect([...HEAT_OPACITY]).toEqual([...HEAT_OPACITY].sort((a, b) => a - b))
    expect(new Set(HEAT_OPACITY).size).toBe(5)
    expect(HEAT_OPACITY[0]).toBeGreaterThan(0)
    expect(Math.max(...HEAT_OPACITY)).toBeLessThanOrEqual(0.85)
  })

  it('reads the same property and maps every level', () => {
    const expression = heatOpacity(5)
    expect(expression[1]).toEqual(['get', 'h5'])
    HEAT_OPACITY.forEach((opacity, index) => {
      expect(expression[2 + index * 2]).toBe(index)
      expect(expression[3 + index * 2]).toBe(opacity)
    })
  })
})

describe('heatRadius', () => {
  const radius = heatRadius(0.5, 40) as [string, unknown, unknown, number, number, number, number, number, number]
  const [kind, , , z0, r0, zMax, rMax, zEnd, rEnd] = radius

  it('grows with the map: doubles for every zoom level (exponential base 2)', () => {
    expect(kind).toBe('interpolate')
    expect(radius[1]).toEqual(['exponential', 2])
    expect(radius[2]).toEqual(['zoom'])
    expect(z0).toBe(0)
    expect(rMax / r0).toBeCloseTo(2 ** zMax, 6)
  })

  it('stops growing at high zoom', () => {
    expect(zEnd).toBeGreaterThan(zMax)
    expect(rEnd).toBe(rMax)
  })

  it('is HEAT_RADIUS_SHARE of a grid spacing on the ground', () => {
    // at zoom 5, 40 degrees north: pixel size = 78271.5 * cos(40) / 2^5 meters
    const pixelMeters = (78_271.517 * Math.cos((40 * Math.PI) / 180)) / 2 ** 5
    const radiusAtZoom5 = r0 * 2 ** 5
    expect(radiusAtZoom5 * pixelMeters).toBeCloseTo(HEAT_RADIUS_SHARE * 0.5 * 111_195, -1)
    expect(HEAT_RADIUS_SHARE).toBeGreaterThanOrEqual(0.9)
  })

  it('is bigger for a coarser grid', () => {
    const coarse = heatRadius(2, 40) as unknown[]
    expect(coarse[4] as number).toBeCloseTo((r0 as number) * 4, 6)
  })

  it('is bigger in pixels at higher latitudes (a pixel covers less ground)', () => {
    const north = heatRadius(0.5, 60) as unknown[]
    expect(north[4] as number).toBeGreaterThan(r0)
  })
})
