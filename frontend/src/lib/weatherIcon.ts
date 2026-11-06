// Which weather picture to show for a checkpoint. Only for display: the risk level and its rules
// are the backend's.

import type { Checkpoint, RiskLevel } from '../types/api'
import { RISK_LEVELS } from './risk'

export type WeatherGlyph = 'clear' | 'drizzle' | 'rain' | 'snow' | 'wind'

export const WEATHER_GLYPHS: readonly WeatherGlyph[] = ['clear', 'drizzle', 'rain', 'snow', 'wind']

/** When every condition is Low, weather this strong is still worth a picture (a little rain, a breeze). */
const NOTICEABLE = { snow_in_hr: 0.05, rain_in_hr: 0.01, wind_mph: 15 }

const rank = (level: RiskLevel) => RISK_LEVELS.indexOf(level)

/**
 * The condition that matters most at a checkpoint:
 * - if a load rule raised the level, wind: the load rules are about wind, and the marker's ring
 *   has the raised level's color, so a snow or rain picture would name the wrong cause;
 * - if some condition is above Low, the highest one (snow before rain before wind when they tie);
 * - if all are Low, whatever is noticeable: snow, light rain (drizzle), a breeze;
 * - otherwise calm (a sun: it means "nothing to slow the truck", the app knows no cloud cover).
 */
export function weatherGlyph(
  checkpoint: Pick<Checkpoint, 'weather' | 'level_by'> & Partial<Pick<Checkpoint, 'load_escalated'>>,
): WeatherGlyph {
  const { level_by: by, weather } = checkpoint
  if (checkpoint.load_escalated) return 'wind'
  const top = Math.max(rank(by.snow), rank(by.rain), rank(by.wind))
  if (top > 0) {
    if (rank(by.snow) === top) return 'snow'
    if (rank(by.rain) === top) return 'rain'
    return 'wind'
  }
  if (weather.snow_in_hr >= NOTICEABLE.snow_in_hr) return 'snow'
  if (weather.rain_in_hr >= NOTICEABLE.rain_in_hr) return 'drizzle'
  if (weather.wind_mph >= NOTICEABLE.wind_mph) return 'wind'
  return 'clear'
}

/** What each picture is called on screen (for the screen-reader label and the legend). */
export const GLYPH_LABELS: Record<WeatherGlyph, string> = {
  clear: 'Calm',
  drizzle: 'Light rain',
  rain: 'Rain',
  snow: 'Snow',
  wind: 'Wind',
}
