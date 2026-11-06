import { describe, expect, it } from 'vitest'
import {
  checkpointTitle,
  formatAmount,
  formatShortTime,
  loadRuleNote,
  mileLabel,
  weatherLine,
  weatherRows,
} from './checkpoint'
import { checkpoint } from './testData'

describe('formatAmount', () => {
  it.each([
    [0, '0'],
    [0.016, '0.016'],
    [0.1, '0.1'],
    [0.095, '0.095'],
    [0.25, '0.25'],
    [1.02, '1.02'],
    [3, '3'],
    [2.5004, '2.5'],
  ])('%d -> %s', (value, text) => {
    expect(formatAmount(value)).toBe(text)
  })

  it('never shows 0.095 as 0.10 (a Low value must not look like Moderate)', () => {
    expect(formatAmount(0.095)).not.toBe('0.1')
  })
})

describe('weatherRows and weatherLine', () => {
  const cp = checkpoint({
    weather: { wind_mph: 5.94, rain_in_hr: 1.02, snow_in_hr: 0 },
    level_by: { wind: 'low', rain: 'no_travel', snow: 'low' },
  })

  it('gives each condition its value and level', () => {
    expect(weatherRows(cp)).toEqual([
      { label: 'Wind', icon: 'wind', amount: '5.9', unit: 'mph', value: '5.9 mph', level: 'low' },
      { label: 'Rain', icon: 'rain', amount: '1.02', unit: 'in/hr', value: '1.02 in/hr', level: 'no_travel' },
      { label: 'Snow', icon: 'snow', amount: '0', unit: 'in/hr', value: '0 in/hr', level: 'low' },
    ])
  })

  it('writes one line', () => {
    expect(weatherLine(cp)).toBe('Wind 5.9 mph · Rain 1.02 in/hr · Snow 0 in/hr')
  })

  it('shows zero wind with a decimal', () => {
    expect(weatherRows(checkpoint({ weather: { wind_mph: 0, rain_in_hr: 0, snow_in_hr: 0 } }))[0].value).toBe('0.0 mph')
  })
})

describe('loadRuleNote', () => {
  it('is null when no load rule applied', () => {
    expect(loadRuleNote(checkpoint({ level: 'severe', load_escalated: false }))).toBeNull()
  })
  it('names the 30,000 lb rule for No Travel', () => {
    expect(loadRuleNote(checkpoint({ level: 'no_travel', load_escalated: true }))).toBe(
      'Load over 30,000 lb with wind of 45-54 mph',
    )
  })
  it('names the 40,000 lb rule for Severe', () => {
    expect(loadRuleNote(checkpoint({ level: 'severe', load_escalated: true }))).toBe(
      'Load over 40,000 lb with wind of 35-44 mph',
    )
  })
  it('falls back to a general note', () => {
    expect(loadRuleNote(checkpoint({ level: 'high', load_escalated: true }))).toBe('Raised by the load rules')
  })
})

describe('titles and times', () => {
  it('rounds the mile', () => {
    expect(mileLabel(250)).toBe('Mile 250')
    expect(mileLabel(184.64)).toBe('Mile 185')
    expect(mileLabel(0.4)).toBe('Mile 0')
  })

  it('names the first and last checkpoints', () => {
    expect(checkpointTitle(checkpoint({ index: 0, mile: 0 }), false)).toBe('Origin')
    expect(checkpointTitle(checkpoint({ index: 7, mile: 184.64 }), true)).toBe('Destination')
    expect(checkpointTitle(checkpoint({ index: 3, mile: 75 }), false)).toBe('Mile 75')
  })

  it('a route with a single checkpoint index 0 is the origin', () => {
    expect(checkpointTitle(checkpoint({ index: 0 }), true)).toBe('Origin')
  })

  it('formats a short time in the given zone', () => {
    expect(formatShortTime('2026-11-06T19:00:00Z', 'America/Chicago')).toBe('Fri 1:00 PM')
    expect(formatShortTime('2026-11-07T01:30:00Z', 'America/Chicago')).toBe('Fri 7:30 PM')
    expect(formatShortTime('2026-11-07T01:30:00Z', 'UTC')).toBe('Sat 1:30 AM')
  })
})
