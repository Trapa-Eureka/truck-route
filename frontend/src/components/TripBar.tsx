import { formatShortTime } from '../lib/checkpoint'
import { formatDuration } from '../lib/format'
import type { IconName } from '../lib/icons'
import type { Route } from '../types/api'
import Icon from './Icon'

/** The selected route at a glance, floating over the top of the map. */
export default function TripBar({ route, recommended }: { route: Route | undefined; recommended: boolean }) {
  if (!route) return null
  const { summary } = route
  const items: { icon: IconName; label: string; value: string }[] = [
    { icon: 'route', label: 'Selected route', value: `Route ${route.id}${recommended ? ' · Recommended' : ''}` },
    { icon: 'ruler', label: 'Distance', value: `${summary.distance_miles} mi` },
    { icon: 'clock', label: 'Duration', value: formatDuration(summary.duration_minutes) },
    { icon: 'calendarClock', label: 'Arrival', value: formatShortTime(summary.arrival) },
  ]
  return (
    <dl className="trip-bar" aria-label="Selected route">
      {items.map((item) => (
        <div className="trip-item" key={item.label}>
          <Icon name={item.icon} size={17} />
          <div>
            <dt>{item.label}</dt>
            <dd>{item.value}</dd>
          </div>
        </div>
      ))}
    </dl>
  )
}
