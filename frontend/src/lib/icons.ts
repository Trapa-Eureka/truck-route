// Icons from lucide-static (ISC license), imported as raw SVG text so only the ones listed here
// end up in the bundle. They are drawn with `currentColor`, so CSS colors them.

import arrowRight from 'lucide-static/icons/arrow-right.svg?raw'
import calendarClock from 'lucide-static/icons/calendar-clock.svg?raw'
import check from 'lucide-static/icons/check.svg?raw'
import circleDot from 'lucide-static/icons/circle-dot.svg?raw'
import clock from 'lucide-static/icons/clock.svg?raw'
import cloudDrizzle from 'lucide-static/icons/cloud-drizzle.svg?raw'
import cloudRain from 'lucide-static/icons/cloud-rain.svg?raw'
import flag from 'lucide-static/icons/flag.svg?raw'
import mapPin from 'lucide-static/icons/map-pin.svg?raw'
import route from 'lucide-static/icons/route.svg?raw'
import ruler from 'lucide-static/icons/ruler.svg?raw'
import snowflake from 'lucide-static/icons/snowflake.svg?raw'
import sun from 'lucide-static/icons/sun.svg?raw'
import triangleAlert from 'lucide-static/icons/triangle-alert.svg?raw'
import truck from 'lucide-static/icons/truck.svg?raw'
import weight from 'lucide-static/icons/weight.svg?raw'
import wind from 'lucide-static/icons/wind.svg?raw'

const SVG: Record<string, string> = {
  arrowRight,
  calendarClock,
  check,
  circleDot,
  clock,
  drizzle: cloudDrizzle,
  rain: cloudRain,
  flag,
  mapPin,
  route,
  ruler,
  snow: snowflake,
  clear: sun,
  alert: triangleAlert,
  truck,
  weight,
  wind,
}

export type IconName = keyof typeof SVG

/** The shapes of an icon (its paths, circles ...) without the outer <svg> element. */
export function iconInner(name: IconName): string {
  const match = /<svg[^>]*>([\s\S]*)<\/svg>/.exec(SVG[name])
  if (!match) throw new Error(`icon ${name} is not an SVG`)
  return match[1].trim()
}

/** An icon as an SVG string, for the parts of the screen built without React (the map's popups and pins). */
export function iconMarkup(name: IconName, size = 16): string {
  return (
    `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
    `stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${iconInner(name)}</svg>`
  )
}
