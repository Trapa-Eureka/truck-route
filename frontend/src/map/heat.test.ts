import { describe, expect, it } from 'vitest'
import { HEAT_OPACITY, RISK_COLORS, RISK_LEVELS } from '../lib/risk'
import { HEAT_RADIUS_SHARE, heatColor, heatLayerId, heatRadius } from './heat'

describe('heatColor', () => {
  const rgbaOf = (hex: string, alpha: number) => {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16))
    return `rgba(${r}, ${g}, ${b}, ${alpha})`
  }

  it('reads the level from the property of that hour', () => {
    expect(heatColor(7).slice(0, 2)).toEqual(['match', ['get', 'h7']])
    expect(heatColor(0)[1]).toEqual(['get', 'h0'])
    expect(heatColor(48)[1]).toEqual(['get', 'h48'])
  })

  it('maps level 0 to 4 to the palette colour with that level\'s strength as alpha', () => {
    const expression = heatColor(3)
    RISK_LEVELS.forEach((level, index) => {
      expect(expression[2 + index * 2]).toBe(index)
      expect(expression[3 + index * 2]).toBe(rgbaOf(RISK_COLORS[level], HEAT_OPACITY[index]))
    })
  })

  it('has a fallback (Low) for an unexpected value', () => {
    const expression = heatColor(3)
    expect(expression[expression.length - 1]).toBe(rgbaOf(RISK_COLORS.low, HEAT_OPACITY[0]))
  })

  it('is stronger for higher levels', () => {
    expect([...HEAT_OPACITY]).toEqual([...HEAT_OPACITY].sort((a, b) => a - b))
    expect(new Set(HEAT_OPACITY).size).toBe(5)
    expect(HEAT_OPACITY[0]).toBeGreaterThan(0)
    expect(Math.max(...HEAT_OPACITY)).toBeLessThanOrEqual(0.85)
  })

  it('parses each hex colour into its own red, green and blue', () => {
    expect(heatColor(0)[3]).toBe('rgba(46, 158, 95, 0.16)') // #2e9e5f, Low
    expect(heatColor(0)[11]).toBe('rgba(75, 29, 92, 0.66)') // #4b1d5c, No Travel
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


describe('heatLayerId', () => {
  it('gives every hour its own layer id', () => {
    const ids = Array.from({ length: 49 }, (_, hour) => heatLayerId(hour))
    expect(new Set(ids).size).toBe(49)
    expect(ids[0]).toBe('heat-0')
    expect(ids[48]).toBe('heat-48')
  })
})
