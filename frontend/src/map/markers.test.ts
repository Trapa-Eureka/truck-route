import { describe, expect, it } from 'vitest'
import { RISK_COLORS, RISK_LEVELS } from '../lib/risk'
import { glyphInner } from '../lib/weatherGlyphs'
import { WEATHER_GLYPHS } from '../lib/weatherIcon'
import { MARKER_PX, markerImageName, markerSvg } from './markers'

describe('markerImageName', () => {
  it('is unique for every level and picture', () => {
    const names = RISK_LEVELS.flatMap((level) => WEATHER_GLYPHS.map((glyph) => markerImageName(level, glyph)))
    expect(names).toHaveLength(25)
    expect(new Set(names).size).toBe(25)
    expect(markerImageName('no_travel', 'rain')).toBe('wx-no_travel-rain')
  })
})

describe('markerSvg', () => {
  it('draws a white circle with a ring in the color of the level', () => {
    for (const level of RISK_LEVELS) {
      const svg = markerSvg(level, 'clear')
      expect(svg).toContain('fill="#ffffff"')
      expect(svg).toContain(`stroke="${RISK_COLORS[level]}"`)
    }
  })

  it('draws the weather picture in its own colors inside, and a different one for each glyph', () => {
    const drawings = WEATHER_GLYPHS.map((glyph) => markerSvg('low', glyph))
    expect(new Set(drawings).size).toBe(5)
    for (const glyph of WEATHER_GLYPHS) expect(markerSvg('low', glyph)).toContain(glyphInner(glyph))
  })

  it('does not change the picture with the level (only the ring)', () => {
    const lowRain = markerSvg('low', 'rain').replace(RISK_COLORS.low, 'RING')
    const severeRain = markerSvg('severe', 'rain').replace(RISK_COLORS.severe, 'RING')
    expect(lowRain).toBe(severeRain)
  })

  it('is a standalone SVG with a size (an image needs one to be drawn)', () => {
    const svg = markerSvg('high', 'snow')
    expect(svg).toMatch(/^<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg" width="\d+" height="\d+"/)
    expect(svg.endsWith('</svg>')).toBe(true)
  })

  it('keeps the picture inside the ring', () => {
    // the circle is 38 wide, the picture 24 wide: the picture sits well inside it
    expect(MARKER_PX).toBeGreaterThan(24 + 2 * 4)
  })
})
