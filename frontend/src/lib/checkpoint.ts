// Text for one checkpoint: where it is, when the truck gets there, the weather then, and why the
// level is what it is. Used by the map popup and the timeline, so both say the same thing.

import type { Checkpoint, RiskLevel } from '../types/api'
import { dateTimeFormat, toNearestMinute } from './format'

/** 0 -> "0", 0.016 -> "0.016", 1.02 -> "1.02". Rain and snow keep three decimals because the
 *  thresholds sit at values like 0.10 and 0.25: rounding 0.095 to "0.10" would look like Moderate. */
export function formatAmount(value: number): string {
  if (value === 0) return '0'
  return value.toFixed(3).replace(/0+$/, '').replace(/\.$/, '')
}

export interface WeatherRow {
  label: 'Wind' | 'Rain' | 'Snow'
  /** The picture for this condition. */
  icon: 'wind' | 'rain' | 'snow'
  /** "5.9", "0.016": the number alone. */
  amount: string
  /** "mph" or "in/hr". */
  unit: string
  /** "5.9 mph": number and unit together. */
  value: string
  /** The level this condition alone would give (before the load rules). */
  level: RiskLevel
}

export function weatherRows(checkpoint: Checkpoint): WeatherRow[] {
  const { weather, level_by } = checkpoint
  const row = (
    label: WeatherRow['label'],
    icon: WeatherRow['icon'],
    amount: string,
    unit: string,
    level: RiskLevel,
  ): WeatherRow => ({ label, icon, amount, unit, value: `${amount} ${unit}`, level })
  return [
    row('Wind', 'wind', weather.wind_mph.toFixed(1), 'mph', level_by.wind),
    row('Rain', 'rain', formatAmount(weather.rain_in_hr), 'in/hr', level_by.rain),
    row('Snow', 'snow', formatAmount(weather.snow_in_hr), 'in/hr', level_by.snow),
  ]
}

/** "Wind 5.9 mph · Rain 1.02 in/hr · Snow 0 in/hr" */
export function weatherLine(checkpoint: Checkpoint): string {
  return weatherRows(checkpoint)
    .map((row) => `${row.label} ${row.value}`)
    .join(' · ')
}

/**
 * Which load rule raised the level, or null when none did. The rules (CLAUDE.md section 4) are
 * "45-54 mph and over 30,000 lb is No Travel" and "35-44 mph and over 40,000 lb is Severe", and a
 * wind of 55 or more is No Travel on its own, so the final level tells which rule it was.
 */
export function loadRuleNote(checkpoint: Checkpoint): string | null {
  if (!checkpoint.load_escalated) return null
  if (checkpoint.level === 'no_travel') return 'Load over 30,000 lb with wind of 45-54 mph'
  if (checkpoint.level === 'severe') return 'Load over 40,000 lb with wind of 35-44 mph'
  return 'Raised by the load rules'
}

/** "Mile 250", rounded to a whole mile. */
export function mileLabel(mile: number): string {
  return `Mile ${Math.round(mile)}`
}

/** "Origin", "Destination" or "Mile 250". */
export function checkpointTitle(checkpoint: Checkpoint, isLast: boolean): string {
  if (checkpoint.index === 0) return 'Origin'
  if (isLast) return 'Destination'
  return mileLabel(checkpoint.mile)
}

const SHORT_TIME: Intl.DateTimeFormatOptions = { weekday: 'short', hour: 'numeric', minute: '2-digit' }

/** "Fri 2:00 PM": short enough for a list of many checkpoints. Pass a zone for tests. */
export function formatShortTime(iso: string, timeZone?: string): string {
  return dateTimeFormat(SHORT_TIME, timeZone).format(toNearestMinute(iso))
}
