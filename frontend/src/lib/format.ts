// Pure formatting helpers. Times from the API are ISO 8601 UTC; the browser's time zone is
// used for everything the user types and reads.

const QUARTER_HOUR_MS = 15 * 60 * 1000

const pad = (n: number) => String(n).padStart(2, '0')

/** "2026-11-09T14:30": the value format of <input type="datetime-local">, in local time. */
export function toLocalInputValue(date: Date): string {
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

/** The next quarter hour (never in the past), as a datetime-local value. */
export function defaultDeparture(now: Date = new Date()): string {
  const next = new Date(Math.ceil(now.getTime() / QUARTER_HOUR_MS) * QUARTER_HOUR_MS)
  return toLocalInputValue(next)
}

/**
 * The departure to send. A value the user chose is kept as it is. The value the form filled in by
 * itself ("the next quarter hour" when the page opened) goes stale while the page stays open, and
 * the server refuses a departure in the past; as long as the user has not changed it, it moves on
 * to the next quarter hour from now.
 */
export function currentDeparture(value: string, filledIn: string, now: Date = new Date()): string {
  if (value !== filledIn) return value
  return new Date(value).getTime() < now.getTime() ? defaultDeparture(now) : value
}

/**
 * Turns a datetime-local value (local time) into an ISO 8601 UTC string for the API,
 * for example "2026-11-09T20:00:00Z". Returns null when the value is empty or invalid.
 */
export function departureToIso(local: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/.test(local)) return null
  const date = new Date(local)
  if (Number.isNaN(date.getTime())) return null
  return date.toISOString().replace(/\.\d{3}Z$/, 'Z')
}

/** "45 min", "2 h", "14 h 06 min". */
export function formatDuration(minutes: number): string {
  const total = Math.round(minutes)
  const hours = Math.floor(total / 60)
  const rest = total % 60
  if (hours === 0) return `${rest} min`
  if (rest === 0) return `${hours} h`
  return `${hours} h ${pad(rest)} min`
}

export function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : pluralForm}`
}

const formatters = new Map<string, Intl.DateTimeFormat>()

/**
 * An Intl.DateTimeFormat for these options, made once and reused. Building one is slow enough to
 * matter when the forecast slider asks for a few labels on every step.
 */
export function dateTimeFormat(options: Intl.DateTimeFormatOptions, timeZone?: string): Intl.DateTimeFormat {
  const key = `${JSON.stringify(options)}|${timeZone ?? ''}`
  let formatter = formatters.get(key)
  if (!formatter) {
    formatter = new Intl.DateTimeFormat('en-US', { ...options, timeZone })
    formatters.set(key, formatter)
  }
  return formatter
}

const LONG_TIME: Intl.DateTimeFormatOptions = {
  weekday: 'short',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  timeZoneName: 'short',
}

/** "Fri, Nov 6, 2:00 PM CST". Pass a time zone for tests; the default is the browser's. */
export function formatDateTime(iso: string, timeZone?: string): string {
  return dateTimeFormat(LONG_TIME, timeZone).format(toNearestMinute(iso))
}

/** "Route C", "Routes B and C", "Routes A, B and C". */
export function routeNames(ids: readonly string[]): string {
  if (ids.length === 1) return `Route ${ids[0]}`
  return `Routes ${ids.slice(0, -1).join(', ')} and ${ids[ids.length - 1]}`
}

/**
 * The average risk as a card shows it: two decimals. An average above zero is never shown as
 * "0.00", which would read as "no risk at all" for a route that has some.
 */
export function formatAvgRisk(value: number): string {
  if (value > 0 && value < 0.005) return '<0.01'
  return value.toFixed(2)
}

/**
 * Miles as a card shows them: whole miles. An amount above zero that would round to 0 is "<1",
 * so a route with a short Severe stretch never reads "0 severe miles".
 */
export function formatMiles(value: number): string {
  if (value > 0 && value < 0.5) return '<1'
  return String(Math.round(value))
}

/**
 * Two values that the recommendation told apart, written with as few decimals as it takes to see
 * the difference: "25 vs 30", else "24.6 vs 25.4", up to `maxDecimals` (what the API sends). The
 * comparison itself is made on the server at full precision; if the two still read alike here,
 * the caller says so in words.
 */
export function distinctPair(a: number, b: number, minDecimals: number, maxDecimals: number): [string, string] {
  for (let decimals = minDecimals; decimals <= maxDecimals; decimals++) {
    const pair: [string, string] = [a.toFixed(decimals), b.toFixed(decimals)]
    if (pair[0] !== pair[1] || decimals === maxDecimals) return pair
  }
  return [a.toFixed(maxDecimals), b.toFixed(maxDecimals)]
}

const MINUTE_MS = 60_000

/**
 * The time rounded to the nearest minute (half up). The API gives times to the second and the
 * screen shows minutes; cutting the seconds off would show an arrival of 2:35 next to a duration
 * of "2 h 36 min" for a trip of 2 h 35 min 30 s.
 */
export function toNearestMinute(iso: string): Date {
  return new Date(Math.floor(new Date(iso).getTime() / MINUTE_MS + 0.5) * MINUTE_MS)
}
