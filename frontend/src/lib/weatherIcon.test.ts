import { describe, expect, it } from 'vitest'
import { GLYPH_LABELS, WEATHER_GLYPHS, weatherGlyph } from './weatherIcon'
import type { Checkpoint, RiskLevel } from '../types/api'

type Input = Pick<Checkpoint, 'weather' | 'level_by'>

function at(
  by: { wind?: RiskLevel; rain?: RiskLevel; snow?: RiskLevel },
  weather: Partial<Checkpoint['weather']> = {},
): Input {
  return {
    level_by: { wind: by.wind ?? 'low', rain: by.rain ?? 'low', snow: by.snow ?? 'low' },
    weather: { wind_mph: 3, rain_in_hr: 0, snow_in_hr: 0, ...weather },
  }
}

describe('weatherGlyph above Low: the condition that causes the level', () => {
  it('shows snow, rain or wind when only that one is above Low', () => {
    expect(weatherGlyph(at({ snow: 'moderate' }))).toBe('snow')
    expect(weatherGlyph(at({ rain: 'high' }))).toBe('rain')
    expect(weatherGlyph(at({ wind: 'severe' }))).toBe('wind')
  })

  it('shows the highest of them', () => {
    expect(weatherGlyph(at({ wind: 'severe', rain: 'moderate' }))).toBe('wind')
    expect(weatherGlyph(at({ rain: 'no_travel', wind: 'high', snow: 'moderate' }))).toBe('rain')
    expect(weatherGlyph(at({ snow: 'severe', rain: 'high', wind: 'moderate' }))).toBe('snow')
  })

  it('breaks a tie as snow, then rain, then wind', () => {
    expect(weatherGlyph(at({ snow: 'high', rain: 'high', wind: 'high' }))).toBe('snow')
    expect(weatherGlyph(at({ rain: 'high', wind: 'high' }))).toBe('rain')
    expect(weatherGlyph(at({ snow: 'moderate', wind: 'moderate' }))).toBe('snow')
  })

  it('uses a plain rain picture, not the light-rain one, once rain is above Low', () => {
    expect(weatherGlyph(at({ rain: 'moderate' }, { rain_in_hr: 0.12 }))).toBe('rain')
  })

  it('ignores the numbers once a level says what matters', () => {
    // wind is Moderate, so the picture is wind even though some snow is falling
    expect(weatherGlyph(at({ wind: 'moderate' }, { wind_mph: 30, snow_in_hr: 0.2 }))).toBe('wind')
  })
})

describe('weatherGlyph when everything is Low', () => {
  it('is clear for calm weather', () => {
    expect(weatherGlyph(at({}))).toBe('clear')
    expect(weatherGlyph(at({}, { wind_mph: 14.9, rain_in_hr: 0.0099, snow_in_hr: 0.049 }))).toBe('clear')
  })

  it('shows light snow from 0.05 in/hr', () => {
    expect(weatherGlyph(at({}, { snow_in_hr: 0.05 }))).toBe('snow')
  })

  it('shows light rain (drizzle) from 0.01 in/hr', () => {
    expect(weatherGlyph(at({}, { rain_in_hr: 0.01 }))).toBe('drizzle')
    expect(weatherGlyph(at({}, { rain_in_hr: 0.09 }))).toBe('drizzle')
  })

  it('shows a breeze from 15 mph', () => {
    expect(weatherGlyph(at({}, { wind_mph: 15 }))).toBe('wind')
    expect(weatherGlyph(at({}, { wind_mph: 24 }))).toBe('wind')
  })

  it('prefers snow, then rain, then wind', () => {
    expect(weatherGlyph(at({}, { snow_in_hr: 0.1, rain_in_hr: 0.05, wind_mph: 20 }))).toBe('snow')
    expect(weatherGlyph(at({}, { rain_in_hr: 0.05, wind_mph: 20 }))).toBe('drizzle')
  })
})

describe('weatherGlyph when a load rule raised the level', () => {
  it('shows wind, because the load rules are about wind', () => {
    // wind 40 mph is High; with a 45,000 lb load it is Severe. Snow alone is High too.
    expect(weatherGlyph({ ...at({ wind: 'high', snow: 'high' }), load_escalated: true })).toBe('wind')
    // wind 50 mph is Severe; over 30,000 lb it is No Travel. Snow alone is Severe.
    expect(weatherGlyph({ ...at({ wind: 'severe', snow: 'severe', rain: 'high' }), load_escalated: true })).toBe('wind')
  })

  it('keeps the usual rule when the load did not raise anything', () => {
    expect(weatherGlyph({ ...at({ wind: 'high', snow: 'high' }), load_escalated: false })).toBe('snow')
  })
})

describe('glyph names', () => {
  it('names each picture as it is shown', () => {
    expect(GLYPH_LABELS).toEqual({ clear: 'Calm', drizzle: 'Light rain', rain: 'Rain', snow: 'Snow', wind: 'Wind' })
  })

  it('every glyph has a label', () => {
    for (const glyph of WEATHER_GLYPHS) expect(GLYPH_LABELS[glyph]).toMatch(/\S/)
    expect(WEATHER_GLYPHS).toHaveLength(5)
  })
})
