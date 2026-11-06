// The weather pictures in their own flat colors (the style of ref/route_ref_icon.png): a yellow
// sun, a blue drop for rain, a blue snowflake, a teal wind. They are drawn on a 24 x 24 grid with
// fixed colors (no gradients, so the same picture can sit on a page many times without clashing
// ids). Used on the map markers, in the popup and in the checkpoint list.

import { iconInner } from './icons'
import type { WeatherGlyph } from './weatherIcon'

export const GLYPH_COLORS: Record<WeatherGlyph, string> = {
  clear: '#f9b928',
  drizzle: '#6aa8f5',
  rain: '#2f6fe4',
  snow: '#4a90e2',
  wind: '#12a1a8',
}

/** A stroked line icon (snowflake, wind) in the glyph's color. */
const stroked = (glyph: 'snow' | 'wind') =>
  `<g fill="none" stroke="${GLYPH_COLORS[glyph]}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${iconInner(glyph)}</g>`

const DROP = (scale: 'small' | 'large') =>
  scale === 'large'
    ? 'M12 2.5c-3.8 4.6-6.3 8-6.3 11.2a6.3 6.3 0 0 0 12.6 0c0-3.2-2.5-6.6-6.3-11.2z'
    : 'M12 5c-2.9 3.5-4.7 6.1-4.7 8.5a4.7 4.7 0 0 0 9.4 0c0-2.4-1.8-5-4.7-8.5z'

/** The shapes of a glyph (no <svg> around them), on the 24 x 24 grid. */
export function glyphInner(glyph: WeatherGlyph): string {
  switch (glyph) {
    case 'clear':
      return (
        `<circle cx="12" cy="12" r="9.5" fill="${GLYPH_COLORS.clear}"/>` +
        `<circle cx="9.3" cy="9.3" r="5" fill="#ffd66e" opacity="0.85"/>`
      )
    case 'drizzle':
      return `<path d="${DROP('small')}" fill="${GLYPH_COLORS.drizzle}"/>`
    case 'rain':
      return (
        `<path d="${DROP('large')}" fill="${GLYPH_COLORS.rain}"/>` +
        `<path d="M9.2 14.4a3 3 0 0 0 2.2 2.8" fill="none" stroke="#ffffff" stroke-width="1.6" stroke-linecap="round" opacity="0.7"/>`
      )
    case 'snow':
      return stroked('snow')
    case 'wind':
      return stroked('wind')
  }
}

/** A glyph as a standalone SVG string (for the map's popups). */
export function glyphMarkup(glyph: WeatherGlyph, size = 18): string {
  return `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 24 24" aria-hidden="true">${glyphInner(glyph)}</svg>`
}
