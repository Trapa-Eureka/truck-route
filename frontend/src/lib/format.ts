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

/** "Fri, Nov 6, 2:00 PM CST". Pass a time zone for tests; the default is the browser's. */
export function formatDateTime(iso: string, timeZone?: string): string {
  return new Intl.DateTimeFormat('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
    timeZone,
  }).format(new Date(iso))
}

/** "Route C", "Routes B and C", "Routes A, B and C". */
export function routeNames(ids: readonly string[]): string {
  if (ids.length === 1) return `Route ${ids[0]}`
  return `Routes ${ids.slice(0, -1).join(', ')} and ${ids[ids.length - 1]}`
}

export function formatAvgRisk(value: number): string {
  return value.toFixed(2)
}
