// The weather markers on the route: a white circle with the weather picture in its own colors (a
// yellow sun, a blue drop, a snowflake: ref/route_ref_icon.png) and a ring in the risk level's
// color, so the level is still readable at a glance. They are drawn once into small images and
// handed to the map, which then places them like labels (and leaves some out where they would
// overlap, so a long route stays readable when zoomed out). One image per level and picture: 5 x 5.

import type { Map as MapLibreMap } from 'maplibre-gl'
import { RISK_COLORS, RISK_LEVELS } from '../lib/risk'
import { glyphInner } from '../lib/weatherGlyphs'
import { WEATHER_GLYPHS, type WeatherGlyph } from '../lib/weatherIcon'
import type { RiskLevel } from '../types/api'

/** Width of the white circle with its ring, in screen pixels at icon-size 1. */
export const MARKER_PX = 38
const RING = 4
const PAD = 5 // room around the circle for its shadow
const SIZE = MARKER_PX + 2 * PAD
const RATIO = 2 // drawn at twice the size for sharp edges on high-density screens

export const markerImageName = (level: RiskLevel, glyph: WeatherGlyph) => `wx-${level}-${glyph}`

/** The SVG of one marker. */
export function markerSvg(level: RiskLevel, glyph: WeatherGlyph): string {
  const center = SIZE / 2
  const picture = 24 // glyph size in px; the pictures are drawn on a 24-unit grid
  const scale = picture / 24
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${SIZE}" height="${SIZE}" viewBox="0 0 ${SIZE} ${SIZE}">` +
    `<circle cx="${center}" cy="${center}" r="${MARKER_PX / 2 - RING / 2}" fill="#ffffff" stroke="${RISK_COLORS[level]}" stroke-width="${RING}"/>` +
    `<g transform="translate(${center - picture / 2} ${center - picture / 2}) scale(${scale})">${glyphInner(glyph)}</g></svg>`
  )
}

async function drawMarker(level: RiskLevel, glyph: WeatherGlyph): Promise<ImageData> {
  const image = new Image()
  image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markerSvg(level, glyph))}`
  await image.decode()
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = SIZE * RATIO
  const context = canvas.getContext('2d')!
  context.shadowColor = 'rgba(26, 37, 48, 0.28)'
  context.shadowBlur = 3 * RATIO
  context.shadowOffsetY = 1 * RATIO
  context.drawImage(image, 0, 0, SIZE * RATIO, SIZE * RATIO)
  return context.getImageData(0, 0, SIZE * RATIO, SIZE * RATIO)
}

/** Draws every marker image and adds it to the map. Call before the layer that uses them. */
export async function addWeatherMarkers(map: MapLibreMap): Promise<void> {
  const images = await Promise.all(
    RISK_LEVELS.flatMap((level) =>
      WEATHER_GLYPHS.map(async (glyph) => ({ name: markerImageName(level, glyph), data: await drawMarker(level, glyph) })),
    ),
  )
  for (const { name, data } of images) {
    if (!map.hasImage(name)) map.addImage(name, data, { pixelRatio: RATIO })
  }
}
