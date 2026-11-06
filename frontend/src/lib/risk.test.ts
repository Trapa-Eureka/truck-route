import { describe, expect, it } from 'vitest'
import { OTHER_ROUTE_COLOR, RISK_COLORS, RISK_LABELS, RISK_LEVELS } from './risk'

describe('risk levels', () => {
  it('are in the PDF order, lowest first', () => {
    expect(RISK_LEVELS).toEqual(['low', 'moderate', 'high', 'severe', 'no_travel'])
  })

  it('use the PDF names', () => {
    expect(RISK_LEVELS.map((level) => RISK_LABELS[level])).toEqual(['Low', 'Moderate', 'High', 'Severe', 'No Travel'])
  })

  it('each have a distinct color, none equal to the gray of other routes', () => {
    const colors = RISK_LEVELS.map((level) => RISK_COLORS[level])
    expect(new Set(colors).size).toBe(5)
    expect(colors).not.toContain(OTHER_ROUTE_COLOR)
  })

  it('colors are 6-digit hex', () => {
    for (const color of Object.values(RISK_COLORS)) expect(color).toMatch(/^#[0-9a-f]{6}$/)
  })

  it('get darker from moderate up, so the order shows without color vision', () => {
    const luminance = (hex: string) => {
      const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
      return 0.2126 * r + 0.7152 * g + 0.0722 * b
    }
    const steps = (['moderate', 'high', 'severe', 'no_travel'] as const).map((l) => luminance(RISK_COLORS[l]))
    expect([...steps].sort((a, b) => b - a)).toEqual(steps)
  })
})
