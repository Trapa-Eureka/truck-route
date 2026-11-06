import { describe, expect, it } from 'vitest'
import {
  defaultDeparture,
  departureToIso,
  formatAvgRisk,
  formatDateTime,
  formatDuration,
  plural,
  routeNames,
  toLocalInputValue,
} from './format'

// vite.config.ts fixes TZ to America/Chicago for the tests.

describe('toLocalInputValue', () => {
  it('formats local time for a datetime-local input', () => {
    expect(toLocalInputValue(new Date(2026, 10, 9, 8, 5))).toBe('2026-11-09T08:05')
  })
  it('pads single digits', () => {
    expect(toLocalInputValue(new Date(2026, 0, 2, 3, 4))).toBe('2026-01-02T03:04')
  })
})

describe('defaultDeparture', () => {
  it('rounds up to the next quarter hour', () => {
    expect(defaultDeparture(new Date(2026, 10, 9, 8, 1))).toBe('2026-11-09T08:15')
    expect(defaultDeparture(new Date(2026, 10, 9, 8, 14, 59))).toBe('2026-11-09T08:15')
    expect(defaultDeparture(new Date(2026, 10, 9, 8, 16))).toBe('2026-11-09T08:30')
    expect(defaultDeparture(new Date(2026, 10, 9, 8, 46))).toBe('2026-11-09T09:00')
  })
  it('keeps a time that is already on a quarter hour', () => {
    expect(defaultDeparture(new Date(2026, 10, 9, 8, 30))).toBe('2026-11-09T08:30')
  })
  it('is never in the past', () => {
    const now = new Date(2026, 10, 9, 8, 7, 31)
    expect(new Date(defaultDeparture(now)).getTime()).toBeGreaterThanOrEqual(now.getTime())
  })
  it('rolls over midnight', () => {
    expect(defaultDeparture(new Date(2026, 10, 9, 23, 50))).toBe('2026-11-10T00:00')
  })
})

describe('departureToIso', () => {
  it('converts local time (CST, UTC-6) to UTC', () => {
    expect(departureToIso('2026-11-09T14:00')).toBe('2026-11-09T20:00:00Z')
  })
  it('uses the offset in force on that date (CDT, UTC-5, before the November change)', () => {
    expect(departureToIso('2026-10-31T14:00')).toBe('2026-10-31T19:00:00Z')
  })
  it('crosses the fall-back date', () => {
    expect(departureToIso('2026-11-01T12:00')).toBe('2026-11-01T18:00:00Z')
  })
  it('crosses midnight in UTC', () => {
    expect(departureToIso('2026-11-09T20:30')).toBe('2026-11-10T02:30:00Z')
  })
  it('accepts seconds', () => {
    expect(departureToIso('2026-11-09T14:00:30')).toBe('2026-11-09T20:00:30Z')
  })
  it('has no milliseconds (the API takes plain ISO 8601)', () => {
    expect(departureToIso('2026-11-09T14:00')).not.toMatch(/\./)
  })
  it.each(['', 'tomorrow', '2026-11-09', '2026-13-40T10:00', '2026-11-09T25:00', '2026-11-09 14:00'])(
    'rejects %j',
    (value) => {
      expect(departureToIso(value)).toBeNull()
    },
  )
  it('round-trips with defaultDeparture', () => {
    const local = defaultDeparture(new Date(2026, 10, 9, 8, 1))
    expect(departureToIso(local)).toBe('2026-11-09T14:15:00Z')
  })
})

describe('formatDuration', () => {
  it.each([
    [0, '0 min'],
    [45, '45 min'],
    [60, '1 h'],
    [61, '1 h 01 min'],
    [179, '2 h 59 min'],
    [846, '14 h 06 min'],
    [1440, '24 h'],
  ])('%d minutes is %s', (minutes, text) => {
    expect(formatDuration(minutes)).toBe(text)
  })
  it('rounds fractions', () => {
    expect(formatDuration(59.6)).toBe('1 h')
  })
})

describe('plural', () => {
  it('uses the singular only for 1', () => {
    expect(plural(1, 'mile')).toBe('1 mile')
    expect(plural(0, 'mile')).toBe('0 miles')
    expect(plural(2, 'mile')).toBe('2 miles')
  })
  it('accepts an irregular plural', () => {
    expect(plural(2, 'person', 'people')).toBe('2 people')
  })
})

describe('formatDateTime', () => {
  it('shows the weekday, date, time and zone', () => {
    expect(formatDateTime('2026-11-09T20:00:00Z', 'America/Chicago')).toBe('Mon, Nov 9, 2:00 PM CST')
  })
  it('follows the given zone', () => {
    expect(formatDateTime('2026-11-09T20:00:00Z', 'UTC')).toBe('Mon, Nov 9, 8:00 PM UTC')
  })
  it('crosses the date line of the zone', () => {
    expect(formatDateTime('2026-11-10T02:30:00Z', 'America/Chicago')).toBe('Mon, Nov 9, 8:30 PM CST')
  })
})

describe('routeNames', () => {
  it('joins ids', () => {
    expect(routeNames(['C'])).toBe('Route C')
    expect(routeNames(['B', 'C'])).toBe('Routes B and C')
    expect(routeNames(['A', 'B', 'C'])).toBe('Routes A, B and C')
  })
})

describe('formatAvgRisk', () => {
  it('always shows two decimals', () => {
    expect(formatAvgRisk(0)).toBe('0.00')
    expect(formatAvgRisk(0.1)).toBe('0.10')
    expect(formatAvgRisk(0.33)).toBe('0.33')
    expect(formatAvgRisk(2)).toBe('2.00')
  })
})
