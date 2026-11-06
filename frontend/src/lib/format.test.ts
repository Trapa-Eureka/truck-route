import { describe, expect, it } from 'vitest'
import {
  dateTimeFormat,
  defaultDeparture,
  departureToIso,
  formatAvgRisk,
  formatDateTime,
  formatDuration,
  plural,
  routeNames,
  toLocalInputValue,
  currentDeparture,
  distinctPair,
  formatMiles,
  toNearestMinute,
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


describe('dateTimeFormat', () => {
  const options = { hour: 'numeric', minute: '2-digit' } as const

  it('reuses one formatter for the same options and zone (building one is slow)', () => {
    expect(dateTimeFormat(options, 'UTC')).toBe(dateTimeFormat(options, 'UTC'))
    expect(dateTimeFormat(options)).toBe(dateTimeFormat(options))
  })

  it('does not mix zones or options up', () => {
    expect(dateTimeFormat(options, 'UTC')).not.toBe(dateTimeFormat(options, 'America/Chicago'))
    expect(dateTimeFormat(options, 'UTC')).not.toBe(dateTimeFormat({ hour: 'numeric' }, 'UTC'))
    expect(dateTimeFormat(options, 'UTC').format(new Date('2026-11-09T20:30:00Z'))).toBe('8:30 PM')
    expect(dateTimeFormat(options, 'America/Chicago').format(new Date('2026-11-09T20:30:00Z'))).toBe('2:30 PM')
  })

  it('keeps zone and no-zone apart', () => {
    expect(dateTimeFormat(options)).not.toBe(dateTimeFormat(options, 'UTC'))
  })
})

describe('formatAvgRisk for an average that is above zero', () => {
  it('never shows a risk above zero as 0.00', () => {
    expect(formatAvgRisk(0.0001)).toBe('<0.01')
    expect(formatAvgRisk(0.0049)).toBe('<0.01')
    expect(formatAvgRisk(0.005)).toBe('0.01')
    expect(formatAvgRisk(0.0051)).toBe('0.01')
  })
})

describe('formatMiles', () => {
  it('shows whole miles', () => {
    expect(formatMiles(0)).toBe('0')
    expect(formatMiles(25)).toBe('25')
    expect(formatMiles(24.6)).toBe('25')
    expect(formatMiles(25.4)).toBe('25')
    expect(formatMiles(1004.49)).toBe('1004')
  })

  it('shows an amount above zero that would round to 0 as "<1"', () => {
    expect(formatMiles(0.01)).toBe('<1')
    expect(formatMiles(0.2)).toBe('<1')
    expect(formatMiles(0.49)).toBe('<1')
    expect(formatMiles(0.5)).toBe('1')
  })
})

describe('distinctPair', () => {
  it('uses the fewest decimals that tell the two apart', () => {
    expect(distinctPair(0, 25, 0, 2)).toEqual(['0', '25'])
    expect(distinctPair(24.6, 25.4, 0, 2)).toEqual(['24.6', '25.4'])
    expect(distinctPair(25.41, 25.44, 0, 2)).toEqual(['25.41', '25.44'])
    expect(distinctPair(0.1, 0.11, 2, 4)).toEqual(['0.10', '0.11'])
    expect(distinctPair(0.0051, 0.0149, 2, 4)).toEqual(['0.005', '0.015'])
  })

  it('stops at the most decimals allowed', () => {
    expect(distinctPair(25.44, 25.44, 0, 2)).toEqual(['25.44', '25.44'])
    expect(distinctPair(0.3301, 0.3301, 2, 4)).toEqual(['0.3301', '0.3301'])
  })

  it('never starts below the fewest decimals asked for', () => {
    expect(distinctPair(0, 1, 2, 4)).toEqual(['0.00', '1.00'])
  })
})

describe('toNearestMinute', () => {
  const iso = (date: Date) => date.toISOString()

  it('rounds the seconds, half up, instead of cutting them off', () => {
    expect(iso(toNearestMinute('2026-11-10T14:35:29Z'))).toBe('2026-11-10T14:35:00.000Z')
    expect(iso(toNearestMinute('2026-11-10T14:35:30Z'))).toBe('2026-11-10T14:36:00.000Z')
    expect(iso(toNearestMinute('2026-11-10T14:35:59Z'))).toBe('2026-11-10T14:36:00.000Z')
    expect(iso(toNearestMinute('2026-11-10T14:35:00Z'))).toBe('2026-11-10T14:35:00.000Z')
  })

  it('carries over the hour and the day', () => {
    expect(iso(toNearestMinute('2026-11-10T23:59:45Z'))).toBe('2026-11-11T00:00:00.000Z')
  })

  it('makes the arrival agree with the duration next to it', () => {
    // Leaves 12:00, travel time 9,330 s = 155.5 min: the card says "2 h 36 min".
    expect(formatDuration(Math.floor(9330 / 60 + 0.5))).toBe('2 h 36 min')
    expect(formatDateTime('2026-11-10T14:35:30Z', 'UTC')).toBe('Tue, Nov 10, 2:36 PM UTC')
  })
})

describe('currentDeparture', () => {
  const filledIn = '2026-11-09T10:15'

  it('keeps the filled-in time while it is still ahead', () => {
    expect(currentDeparture(filledIn, filledIn, new Date(2026, 10, 9, 10, 2))).toBe(filledIn)
    expect(currentDeparture(filledIn, filledIn, new Date(2026, 10, 9, 10, 15))).toBe(filledIn)
  })

  it('moves a filled-in time that has passed to the next quarter hour from now', () => {
    // page opened at 10:02 (default 10:15), Analyze pressed again at 10:21
    expect(currentDeparture(filledIn, filledIn, new Date(2026, 10, 9, 10, 21))).toBe('2026-11-09T10:30')
    expect(currentDeparture(filledIn, filledIn, new Date(2026, 10, 9, 10, 15, 1))).toBe('2026-11-09T10:30')
    expect(currentDeparture(filledIn, filledIn, new Date(2026, 10, 10, 7, 44))).toBe('2026-11-10T07:45')
  })

  it('keeps a filled-in time that is ahead by more than a quarter hour (a clock that was set back)', () => {
    expect(currentDeparture(filledIn, filledIn, new Date(2026, 10, 9, 9, 40))).toBe(filledIn)
  })

  it('never touches a time the user chose, even one in the past', () => {
    expect(currentDeparture('2026-11-09T09:00', filledIn, new Date(2026, 10, 9, 10, 21))).toBe('2026-11-09T09:00')
    expect(currentDeparture('2026-11-12T08:00', filledIn, new Date(2026, 10, 9, 10, 21))).toBe('2026-11-12T08:00')
    expect(currentDeparture('', filledIn, new Date(2026, 10, 9, 10, 21))).toBe('')
  })
})
