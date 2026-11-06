import { describe, expect, it } from 'vitest'
import type { StyleSpecification } from 'maplibre-gl'
import { grayValue, mutedStyle, parseColor, toGray } from './mutedStyle'

describe('parseColor', () => {
  it.each([
    ['#fff', [255, 255, 255, 1]],
    ['#f80', [255, 136, 0, 1]],
    ['#ff8800', [255, 136, 0, 1]],
    ['#FF8800', [255, 136, 0, 1]],
    ['rgb(10, 20, 30)', [10, 20, 30, 1]],
    ['rgba(10, 20, 30, 0.5)', [10, 20, 30, 0.5]],
    ['rgba(246,241,224,1)', [246, 241, 224, 1]],
    ['  rgb( 1 , 2 , 3 ) ', [1, 2, 3, 1]],
  ])('reads %s', (css, expected) => {
    expect(parseColor(css)).toEqual(expected)
  })

  it('reads an 8-digit hex alpha', () => {
    const [, , , alpha] = parseColor('#ff880080')!
    expect(alpha).toBeCloseTo(0.502, 2)
  })

  it.each(['', 'red', 'motorway', 'woody vegetation', '#12', '#12345', 'hsl(0, 0%, 0%)', 'rgb(1,2)', '{name}', 'Open Sans Bold'])(
    'does not read %j',
    (text) => {
      expect(parseColor(text)).toBeNull()
    },
  )
})

describe('toGray', () => {
  const channels = (css: string) => (css.match(/\d+(\.\d+)?/g) ?? []).map(Number)

  it('makes all three channels equal', () => {
    for (const css of ['rgb(170, 211, 223)', '#3a7d44', 'rgba(255, 0, 0, 1)']) {
      const [r, g, b] = channels(toGray(css)!)
      expect(r).toBe(g)
      expect(g).toBe(b)
    }
  })

  it('keeps the order of lightness: white above land above water', () => {
    const gray = (css: string) => channels(toGray(css)!)[0]
    expect(gray('rgb(255, 255, 255)')).toBeGreaterThan(gray('rgb(246, 241, 224)'))
    expect(gray('rgb(246, 241, 224)')).toBeGreaterThan(gray('rgb(170, 211, 223)'))
  })

  it('sees green as lighter than blue, as the eye does (not as a plain average)', () => {
    const gray = (css: string) => channels(toGray(css)!)[0]
    expect(gray('rgb(0, 255, 0)')).toBeGreaterThan(gray('rgb(255, 0, 0)'))
    expect(gray('rgb(255, 0, 0)')).toBeGreaterThan(gray('rgb(0, 0, 255)'))
  })

  it('keeps white lighter than anything but never above 255', () => {
    expect(channels(toGray('#fff')!)[0]).toBeLessThanOrEqual(255)
    expect(channels(toGray('#fff')!)[0]).toBeGreaterThan(240)
  })

  it('keeps the transparency', () => {
    expect(toGray('rgba(100, 150, 200, 0.4)')).toMatch(/^rgba\(\d+, \d+, \d+, 0\.4\)$/)
    expect(toGray('rgba(100, 150, 200, 1)')).toMatch(/^rgb\(/)
  })

  it('keeps text darker than a surface of the same color', () => {
    const color = 'rgb(60, 60, 70)'
    expect(channels(toGray(color, 'text')!)[0]).toBeLessThan(channels(toGray(color, 'surface')!)[0])
    expect(channels(toGray(color, 'text')!)[0]).toBeLessThan(110)
  })

  it('returns null for what is not a color', () => {
    expect(toGray('motorway')).toBeNull()
  })
})

describe('grayValue', () => {
  it('grays a plain color', () => {
    expect(grayValue('rgb(255, 0, 0)', 'surface')).toMatch(/^rgb\((\d+), \1, \1\)$/)
  })

  it('grays colors inside an expression and leaves the rest', () => {
    const out = grayValue(['interpolate', ['linear'], ['zoom'], 5, 'rgb(255, 0, 0)', 10, 'rgba(0, 0, 255, 0.5)'], 'surface') as unknown[]
    expect(out.slice(0, 5)).toEqual(['interpolate', ['linear'], ['zoom'], 5, out[4]])
    expect(out[4]).toMatch(/^rgb\((\d+), \1, \1\)$/)
    expect(out[5]).toBe(10)
    expect(out[6]).toMatch(/^rgba\((\d+), \1, \1, 0\.5\)$/)
  })

  it('grays the colors of an old-style stops function and keeps its categories', () => {
    const out = grayValue(
      { property: 'category', type: 'categorical', stops: [['woody vegetation', 'rgba(195, 224, 192, 1)'], ['sand', '#f8efbd']] },
      'surface',
    ) as { property: string; type: string; stops: [string, string][] }
    expect(out.property).toBe('category')
    expect(out.type).toBe('categorical')
    expect(out.stops.map(([name]) => name)).toEqual(['woody vegetation', 'sand'])
    for (const [, color] of out.stops) expect(color).toMatch(/^rgb\((\d+), \1, \1\)$/)
  })

  it('leaves numbers, booleans and null alone', () => {
    expect(grayValue([1, true, null, 2.5], 'surface')).toEqual([1, true, null, 2.5])
  })
})

describe('mutedStyle', () => {
  const style = {
    version: 8,
    sources: {},
    layers: [
      { id: 'bg', type: 'background', paint: { 'background-color': 'rgba(246, 241, 224, 1)' } },
      { id: 'water', type: 'fill', source: 's', 'source-layer': 'Water', paint: { 'fill-color': 'rgb(170, 211, 223)', 'fill-opacity': 0.8 } },
      { id: 'road', type: 'line', source: 's', 'source-layer': 'Motorway', paint: { 'line-color': 'rgb(250, 200, 80)', 'line-width': 3 } },
      { id: 'label', type: 'symbol', source: 's', 'source-layer': 'Motorway', layout: { 'text-field': '{name}' }, paint: { 'text-color': 'rgb(60, 60, 70)', 'text-halo-color': 'rgb(255, 255, 255)' } },
      { id: 'poi', type: 'symbol', source: 's', 'source-layer': 'Point of Interest', layout: { 'icon-image': 'hospital' }, paint: {} },
      { id: 'shield', type: 'symbol', source: 's', 'source-layer': 'Motorway', layout: { 'icon-image': 'shield' }, paint: {} },
      { id: 'city', type: 'symbol', source: 's', 'source-layer': 'Large city', layout: { 'icon-image': 'dot' }, paint: {} },
      { id: 'noPaint', type: 'symbol', source: 's', 'source-layer': 'X', layout: { 'text-field': 'a' } },
    ],
  } as unknown as StyleSpecification
  const muted = mutedStyle(style)
  const byId = (id: string) => muted.layers.find((l) => l.id === id)!

  it('grays the colors of every layer', () => {
    for (const [id, prop] of [['bg', 'background-color'], ['water', 'fill-color'], ['road', 'line-color']] as const) {
      expect((byId(id).paint as Record<string, string>)[prop]).toMatch(/^rgb\((\d+), \1, \1\)$/)
    }
  })

  it('keeps everything that is not a color', () => {
    expect((byId('water').paint as Record<string, unknown>)['fill-opacity']).toBe(0.8)
    expect((byId('road').paint as Record<string, unknown>)['line-width']).toBe(3)
    expect(byId('label').layout).toEqual({ 'text-field': '{name}' })
  })

  it('keeps labels readable and halos light', () => {
    const paint = byId('label').paint as Record<string, string>
    expect(Number(paint['text-color'].match(/\d+/)![0])).toBeLessThan(110)
    expect(Number(paint['text-halo-color'].match(/\d+/)![0])).toBeGreaterThan(240)
  })

  it('keeps a very dark label dark (labels are not lightened like surfaces are)', () => {
    const dark = mutedStyle({
      ...style,
      layers: [{ id: 't', type: 'symbol', source: 's', paint: { 'text-color': 'rgb(30, 30, 30)', 'fill-color': 'rgb(30, 30, 30)' } }],
    } as unknown as StyleSpecification)
    const paint = dark.layers[0].paint as Record<string, string>
    expect(Number(paint['text-color'].match(/\d+/)![0])).toBeLessThan(50)
    expect(Number(paint['fill-color'].match(/\d+/)![0])).toBeGreaterThan(70) // a dark surface is lightened
  })

  it('removes the points of interest', () => {
    expect(muted.layers.map((l) => l.id)).not.toContain('poi')
  })

  it('fades picture icons but not cities', () => {
    expect((byId('shield').paint as Record<string, unknown>)['icon-opacity']).toBe(0.55)
    expect((byId('city').paint as Record<string, unknown>)['icon-opacity']).toBeUndefined()
  })

  it('handles a layer with no paint', () => {
    expect(byId('noPaint')).toBeDefined()
  })

  it('does not change the style it was given', () => {
    expect((style.layers[0].paint as Record<string, string>)['background-color']).toBe('rgba(246, 241, 224, 1)')
    expect(style.layers).toHaveLength(8)
    expect(muted.layers).toHaveLength(7)
  })

  it('keeps the sprite, glyphs and version of the style', () => {
    const withExtras = mutedStyle({ ...style, sprite: 'x/sprite', glyphs: 'x/{fontstack}' } as StyleSpecification)
    expect(withExtras.sprite).toBe('x/sprite')
    expect(withExtras.glyphs).toBe('x/{fontstack}')
    expect(withExtras.version).toBe(8)
  })
})
