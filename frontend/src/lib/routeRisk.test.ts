import { describe, expect, it } from 'vitest'
import { riskNote, riskShares, wholeMiles } from './routeRisk'
import type { RiskLevel } from '../types/api'

const miles = (partial: Partial<Record<RiskLevel, number>>): Record<RiskLevel, number> => ({
  low: 0,
  moderate: 0,
  high: 0,
  severe: 0,
  no_travel: 0,
  ...partial,
})

describe('riskShares', () => {
  it('lists only the levels that have miles, lowest to highest', () => {
    expect(riskShares(miles({ low: 980, severe: 4, moderate: 22 }))).toEqual([
      { level: 'low', miles: 980 },
      { level: 'moderate', miles: 22 },
      { level: 'severe', miles: 4 },
    ])
  })

  it('is empty when there are no miles', () => {
    expect(riskShares(miles({}))).toEqual([])
  })

  it('keeps a level with a fraction of a mile', () => {
    expect(riskShares(miles({ low: 100, high: 0.2 })).map((s) => s.level)).toEqual(['low', 'high'])
  })
})

describe('riskNote', () => {
  it('says "All Low" when every mile is Low', () => {
    expect(riskNote(miles({ low: 1006 }))).toBe('All Low along the route')
  })

  it('names each level with its miles, joined by a middle dot', () => {
    expect(riskNote(miles({ low: 980.4, moderate: 25.6 }))).toBe('Low 980 mi · Moderate 26 mi')
  })

  it('does not say "All" when another level is present, however small', () => {
    expect(riskNote(miles({ low: 1000, high: 0.3 }))).toBe('Low 1000 mi · High <1 mi')
  })

  it('shows a route that is only Moderate or worse as itself, not as "All Low"', () => {
    expect(riskNote(miles({ moderate: 50 }))).toBe('Moderate 50 mi')
    expect(riskNote(miles({ no_travel: 12 }))).toBe('No Travel 12 mi')
  })

  it('shows less than half a mile as "<1" and half a mile or more as 1', () => {
    expect(riskNote(miles({ low: 10, high: 0.49 }))).toBe('Low 10 mi \u00b7 High <1 mi')
    expect(riskNote(miles({ low: 10, high: 0.5 }))).toBe('Low 10 mi \u00b7 High 1 mi')
    expect(riskNote(miles({ low: 10, high: 0.9 }))).toBe('Low 10 mi \u00b7 High 1 mi')
  })

  it('rounds half up', () => {
    expect(riskNote(miles({ low: 10, moderate: 24.5 }))).toBe('Low 10 mi · Moderate 25 mi')
  })

  it('adds up to the distance shown on the card', () => {
    // Each level rounded on its own would say 113 + 14 = 127 for a 126 mile route.
    expect(riskNote(miles({ low: 112.51, high: 13.52 }))).toBe('Low 112 mi · High 14 mi')
    // Four levels of 100.5: 4 x 101 = 404 for a 402 mile route.
    expect(riskNote(miles({ low: 100.5, moderate: 100.5, high: 100.5, severe: 100.5 }))).toBe(
      'Low 101 mi · Moderate 101 mi · High 100 mi · Severe 100 mi',
    )
  })

  it('reads what the server sends for a short stub: two decimals, never 0', () => {
    expect(riskNote(miles({ low: 190.2, severe: 0.2 }))).toBe('Low 190 mi · Severe <1 mi')
    expect(riskNote(miles({ low: 99.99, no_travel: 0.01 }))).toBe('Low 100 mi · No Travel <1 mi')
  })

  it('is empty with no miles at all', () => {
    expect(riskNote(miles({}))).toBe('')
  })
})

describe('wholeMiles', () => {
  const shares = (...values: number[]) => values.map((value) => ({ level: 'low' as RiskLevel, miles: value }))

  it('gives whole miles that add up to the rounded total', () => {
    for (const values of [[112.51, 13.52], [100.5, 100.5, 100.5, 100.5], [0.4, 0.4, 0.4], [33.3, 33.3, 33.4], [980.4, 25.6]]) {
      const total = Math.round(values.reduce((a, b) => a + b, 0))
      expect(wholeMiles(shares(...values)).reduce((a, b) => a + b, 0)).toBe(total)
    }
  })

  it('rounds the largest fractions up first', () => {
    expect(wholeMiles(shares(10.2, 10.7, 10.6))).toEqual([10, 11, 11]) // total 31.5 -> 32
    expect(wholeMiles(shares(1.9, 1.1))).toEqual([2, 1])
  })

  it('never moves a level by more than a mile', () => {
    for (const values of [[5.5, 5.5, 5.5], [0.9, 0.9, 0.9, 0.9], [120.49, 3.49, 0.02]]) {
      wholeMiles(shares(...values)).forEach((whole, i) => expect(Math.abs(whole - values[i])).toBeLessThan(1))
    }
  })

  it('is empty for no levels', () => {
    expect(wholeMiles([])).toEqual([])
  })
})
