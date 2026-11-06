import { formatAvgRisk, formatDuration } from '../lib/format'
import type { Route } from '../types/api'

interface Props {
  route: Route
  selected: boolean
  recommended: boolean
  onSelect: (id: string) => void
}

/** One route with the four numbers that matter: severe miles, high miles, average risk, duration. */
export default function RouteCard({ route, selected, recommended, onSelect }: Props) {
  const { summary } = route
  const blocked = summary.has_no_travel
  const className = ['route-card', selected && 'selected', blocked && 'blocked'].filter(Boolean).join(' ')

  return (
    <button type="button" className={className} aria-pressed={selected} onClick={() => onSelect(route.id)}>
      <span className="route-head">
        <span className="route-name">Route {route.id}</span>
        <span className="route-distance">{summary.distance_miles} mi</span>
        {recommended && <span className="badge recommended">Recommended</span>}
        {blocked && <span className="badge no-travel">No Travel</span>}
      </span>
      <span className="stats">
        <span className="stat">
          <span className="stat-value">{summary.severe_miles}</span>
          <span className="stat-label">Severe mi</span>
        </span>
        <span className="stat">
          <span className="stat-value">{summary.high_miles}</span>
          <span className="stat-label">High mi</span>
        </span>
        <span className="stat">
          <span className="stat-value">{formatAvgRisk(summary.avg_risk)}</span>
          <span className="stat-label">Avg risk</span>
        </span>
        <span className="stat">
          <span className="stat-value">{formatDuration(summary.duration_minutes)}</span>
          <span className="stat-label">Duration</span>
        </span>
      </span>
    </button>
  )
}
