// A quiet, gray base map, so the route and the weather are what you see.
//
// The TomTom style is in full color (green fields, blue water, yellow highways). This reads the
// style once after it is fetched and turns every color into a gray, then takes out the picture
// icons (points of interest) that cannot be recolored. Nothing is stored; it runs on each load.

import type { StyleSpecification } from 'maplibre-gl'

type Rgba = [number, number, number, number]

/** Parses `#rgb`, `#rrggbb`, `#rrggbbaa`, `rgb(r, g, b)` and `rgba(r, g, b, a)`; null for anything else. */
export function parseColor(css: string): Rgba | null {
  const text = css.trim().toLowerCase()
  const hex = /^#([0-9a-f]{3,8})$/.exec(text)
  if (hex) {
    const h = hex[1]
    if (h.length === 3 || h.length === 4) {
      const [r, g, b, a = 'f'] = h
      return [parseInt(r + r, 16), parseInt(g + g, 16), parseInt(b + b, 16), parseInt(a + a, 16) / 255]
    }
    if (h.length === 6 || h.length === 8) {
      return [
        parseInt(h.slice(0, 2), 16),
        parseInt(h.slice(2, 4), 16),
        parseInt(h.slice(4, 6), 16),
        h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1,
      ]
    }
    return null
  }
  const fn = /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)$/.exec(text)
  if (fn) return [Number(fn[1]), Number(fn[2]), Number(fn[3]), fn[4] === undefined ? 1 : Number(fn[4])]
  return null
}

// How a surface (land, water, roads, buildings) is mapped to a gray: lighter and with less contrast
// than the original, so white stays the lightest thing and the land sits just below it.
const SURFACE_SLOPE = 0.75
const SURFACE_SHIFT = 5
// Labels stay dark enough to read.
const TEXT_SLOPE = 0.7
const TEXT_SHIFT = 10

export type ColorKind = 'surface' | 'text'

const clamp = (value: number) => Math.max(0, Math.min(255, Math.round(value)))

/** The gray for a color, keeping its transparency. Returns null if `css` is not a color we read. */
export function toGray(css: string, kind: ColorKind = 'surface'): string | null {
  const color = parseColor(css)
  if (!color) return null
  const [r, g, b, a] = color
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
  const gray = clamp(
    kind === 'text' ? luminance * TEXT_SLOPE + TEXT_SHIFT : 255 - (255 - luminance) * SURFACE_SLOPE - SURFACE_SHIFT,
  )
  return a >= 1 ? `rgb(${gray}, ${gray}, ${gray})` : `rgba(${gray}, ${gray}, ${gray}, ${a})`
}

/** Grays every color string inside a style value (a plain color, an expression, or an old-style stops function). */
export function grayValue(value: unknown, kind: ColorKind): unknown {
  if (typeof value === 'string') return toGray(value, kind) ?? value
  if (Array.isArray(value)) return value.map((item) => grayValue(item, kind))
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, grayValue(item, kind)]))
  }
  return value
}

const COLOR_PROPERTIES = new Set([
  'background-color',
  'fill-color',
  'fill-outline-color',
  'line-color',
  'fill-extrusion-color',
  'text-color',
  'text-halo-color',
  'icon-color',
  'icon-halo-color',
  'circle-color',
  'circle-stroke-color',
])

/** Picture icons (points of interest) cannot be recolored. */
const isPointOfInterest = (layer: { 'source-layer'?: string }) => layer['source-layer'] === 'Point of Interest'

/** Road numbers and direction arrows are pictures too: kept, but faded so they do not shout. */
const ICON_OPACITY = 0.55

export function mutedStyle(style: StyleSpecification): StyleSpecification {
  const layers = style.layers
    .filter((layer) => !isPointOfInterest(layer as { 'source-layer'?: string }))
    .map((layer) => {
      const paint = { ...(layer.paint ?? {}) } as Record<string, unknown>
      for (const [name, value] of Object.entries(paint)) {
        if (COLOR_PROPERTIES.has(name)) paint[name] = grayValue(value, name === 'text-color' ? 'text' : 'surface')
      }
      const hasIcon = layer.type === 'symbol' && layer.layout && 'icon-image' in layer.layout
      const isCity = /city/i.test((layer as { 'source-layer'?: string })['source-layer'] ?? '')
      if (hasIcon && !isCity) paint['icon-opacity'] = ICON_OPACITY
      return { ...layer, paint } as typeof layer
    })
  return { ...style, layers }
}
