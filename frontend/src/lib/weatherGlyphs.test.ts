import { describe, expect, it } from 'vitest'
import { GLYPH_COLORS, glyphInner, glyphMarkup } from './weatherGlyphs'
import { WEATHER_GLYPHS } from './weatherIcon'

describe('glyphInner', () => {
  it('draws a different picture for every glyph', () => {
    const drawings = WEATHER_GLYPHS.map((glyph) => glyphInner(glyph))
    expect(new Set(drawings).size).toBe(WEATHER_GLYPHS.length)
  })

  it('uses the glyph\'s own color', () => {
    for (const glyph of WEATHER_GLYPHS) expect(glyphInner(glyph)).toContain(GLYPH_COLORS[glyph])
  })

  it('has fixed colors only: nothing inherits the text color and no gradient ids', () => {
    for (const glyph of WEATHER_GLYPHS) {
      const markup = glyphInner(glyph)
      expect(markup).not.toContain('currentColor')
      expect(markup).not.toContain('url(#')
      expect(markup).not.toContain('<defs')
    }
  })

  it('the sun is a yellow disc, rain and drizzle are drops, snow and wind are lines', () => {
    expect(glyphInner('clear')).toContain('<circle')
    expect(glyphInner('clear')).not.toContain('stroke="')
    expect(glyphInner('rain')).toContain('<path')
    expect(glyphInner('drizzle')).toContain('fill="' + GLYPH_COLORS.drizzle + '"')
    expect(glyphInner('snow')).toContain('fill="none"')
    expect(glyphInner('wind')).toContain('stroke="' + GLYPH_COLORS.wind + '"')
  })

  it('rain is a bigger drop than drizzle, and rain is the darker blue', () => {
    expect(glyphInner('rain')).not.toEqual(glyphInner('drizzle'))
    const channel = (hex: string, i: number) => parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16)
    expect(channel(GLYPH_COLORS.rain, 0)).toBeLessThan(channel(GLYPH_COLORS.drizzle, 0)) // less red = deeper blue
  })

  it('keeps the colors apart: sun warm, rain and snow blue, wind teal', () => {
    const channel = (hex: string, i: number) => parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16)
    expect(channel(GLYPH_COLORS.clear, 0)).toBeGreaterThan(channel(GLYPH_COLORS.clear, 2))
    for (const blue of ['rain', 'snow', 'drizzle'] as const) {
      expect(channel(GLYPH_COLORS[blue], 2)).toBeGreaterThan(channel(GLYPH_COLORS[blue], 0))
    }
    expect(new Set(Object.values(GLYPH_COLORS)).size).toBe(5)
  })
})

describe('glyphMarkup', () => {
  it('is a standalone svg of the given size', () => {
    const svg = glyphMarkup('rain', 22)
    expect(svg).toMatch(/^<svg class="icon" width="22" height="22" viewBox="0 0 24 24"/)
    expect(svg.endsWith('</svg>')).toBe(true)
    expect(svg).toContain(glyphInner('rain'))
  })

  it('defaults to 18 px', () => {
    expect(glyphMarkup('clear')).toContain('width="18"')
  })
})
