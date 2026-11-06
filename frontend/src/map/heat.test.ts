import { describe, expect, it } from 'vitest'
import { RISK_COLORS, RISK_LEVELS } from '../lib/risk'
import { HEAT_RADIUS_SHARE, HEAT_STOPS, heatColor, heatLayerId, heatRadius, heatRampCss } from './heat'

describe('HEAT_STOPS', () => {
  it('start at 0 and end at 4, in increasing order', () => {
    expect(HEAT_STOPS[0].score).toBe(0)
    expect(HEAT_STOPS[HEAT_STOPS.length - 1].score).toBe(4)
    const scores = HEAT_STOPS.map((s) => s.score)
    expect([...scores].sort((a, b) => a - b)).toEqual(scores)
    expect(new Set(scores).size).toBe(scores.length)
  })

  it('start with blue for the calmest visible weather, then turn green (not green from the start)', () => {
    const [, calm, , green] = HEAT_STOPS
    expect(calm.rgb[2]).toBeGreaterThan(calm.rgb[1]) // blue is the strongest channel
    expect(green.rgb[1]).toBeGreaterThan(green.rgb[2]) // green is
    expect(green.rgb[1]).toBeGreaterThan(green.rgb[0] + 40) // clearly green, not teal or gray
    expect(calm.rgb).not.toEqual(green.rgb)
  })

  it('give the Low range (a calm day) at least five visible steps', () => {
    expect(HEAT_STOPS.filter((s) => s.score > 0 && s.score < 1).length).toBeGreaterThanOrEqual(5)
  })

  it('are visible on a calm day: Low weather above a light breeze is at least 35% opaque', () => {
    for (const stop of HEAT_STOPS.filter((s) => s.score >= 0.15)) expect(stop.alpha).toBeGreaterThanOrEqual(0.35)
  })

  it('show nothing for calm weather', () => {
    expect(HEAT_STOPS[0].alpha).toBe(0)
  })

  it('get stronger as the weather gets worse', () => {
    const alphas = HEAT_STOPS.map((s) => s.alpha)
    expect([...alphas].sort((a, b) => a - b)).toEqual(alphas)
    expect(Math.max(...alphas)).toBeLessThanOrEqual(0.85)
  })

  it('reach each level color exactly where the level starts (1 to 4), the same colors as the route', () => {
    const hexOf = ([r, g, b]: number[]) => '#' + [r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('')
    RISK_LEVELS.forEach((level, index) => {
      if (index === 0) return
      const stop = HEAT_STOPS.find((s) => s.score === index)!
      expect(hexOf(stop.rgb)).toBe(RISK_COLORS[level])
    })
  })

  it('show different colors for different Low weather, not just a different strength', () => {
    const colorAt = (score: number) => {
      const stops = HEAT_STOPS
      const i = stops.findIndex((s) => s.score >= score)
      const [a, b] = [stops[Math.max(0, i - 1)], stops[i]]
      const t = a.score === b.score ? 0 : (score - a.score) / (b.score - a.score)
      return a.rgb.map((v, k) => v + (b.rgb[k] - v) * t)
    }
    const breeze = colorAt(0.3), brisk = colorAt(0.9)
    expect(breeze).not.toEqual(brisk)
    expect(Math.abs(breeze[0] - brisk[0]) + Math.abs(breeze[1] - brisk[1]) + Math.abs(breeze[2] - brisk[2])).toBeGreaterThan(60)
  })
})

describe('heatColor', () => {
  it('is an interpolation over the score of that hour', () => {
    expect(heatColor(7).slice(0, 3)).toEqual(['interpolate', ['linear'], ['get', 'h7']])
    expect((heatColor(0)[2] as unknown[])[1]).toBe('h0')
    expect((heatColor(48)[2] as unknown[])[1]).toBe('h48')
  })

  it('has one stop per HEAT_STOPS entry, with the score first and then its color', () => {
    const expression = heatColor(3)
    HEAT_STOPS.forEach((stop, i) => {
      expect(expression[3 + i * 2]).toBe(stop.score)
      expect(expression[4 + i * 2]).toMatch(/^rgba\(\d+, \d+, \d+, [\d.]+\)$/)
    })
    expect(expression).toHaveLength(3 + HEAT_STOPS.length * 2)
  })

  it('writes the color and the alpha of each stop', () => {
    expect(heatColor(0)[4]).toBe('rgba(111, 168, 220, 0)') // calm: transparent
    expect(heatColor(0)[heatColor(0).length - 1]).toBe('rgba(75, 29, 92, 0.76)') // No Travel
  })
})

describe('heatRampCss', () => {
  it('is a left-to-right gradient with every stop at its place on the 0 to 4 scale', () => {
    const css = heatRampCss()
    expect(css).toMatch(/^linear-gradient\(to right, /)
    expect(css).toContain(' 0%')
    expect(css).toContain(' 25%') // score 1: where Moderate starts
    expect(css).toContain(' 50%')
    expect(css).toContain(' 75%')
    expect(css).toContain(' 100%')
  })

  it('is stronger with a larger strength (the legend is more saturated than the map)', () => {
    expect(heatRampCss(2)).toContain('rgba(75, 29, 92, 1)')
    expect(heatRampCss(1)).toContain('rgba(75, 29, 92, 0.76)')
  })

  it('never goes above full opacity', () => {
    expect(heatRampCss(10)).not.toMatch(/, (1\.\d+|[2-9])\)/)
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
