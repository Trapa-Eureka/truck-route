import { glyphInner } from '../lib/weatherGlyphs'
import type { WeatherGlyph as Glyph } from '../lib/weatherIcon'

/** A weather picture in its own colors. The markup is fixed shapes from weatherGlyphs.ts. */
export default function WeatherGlyph({ glyph, size = 18 }: { glyph: Glyph; size?: number }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: glyphInner(glyph) }}
    />
  )
}
