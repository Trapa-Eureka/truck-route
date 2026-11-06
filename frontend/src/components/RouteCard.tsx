import { formatShortTime } from '../lib/checkpoint'
import { formatAvgRisk, formatDuration, formatMiles } from '../lib/format'
import { RISK_COLORS } from '../lib/risk'
import { riskNote, riskShares } from '../lib/routeRisk'
import type { Route } from '../types/api'

interface Props {
  route: Route
  originLabel: string
  destinationLabel: string
  selected: boolean
  recommended: boolean
  onSelect: (id: string) => void
}

/** One route: its status, when and where it starts and ends, and the four numbers that matter. */
export default function RouteCard({ route, originLabel, destinationLabel, selected, recommended, onSelect }: Props) {
  const { summary, checkpoints } = route
  const blocked = summary.has_no_travel
  const className = ['route-card', selected && 'selected', blocked && 'blocked'].filter(Boolean).join(' ')
  const status = blocked ? { text: 'No Travel', tone: 'dark' } : recommended ? { text: 'Recommended', tone: 'green' } : { text: 'Alternative', tone: 'gray' }

  return (
    <button type="button" className={className} aria-pressed={selected} onClick={() => onSelect(route.id)}>
      <span className="rc-top">
        <span className="rc-name">Route {route.id}</span>
        <span className="rc-distance">{summary.distance_miles} mi</span>
        <span className={`pill pill-${status.tone}`}>{status.text}</span>
      </span>

      <span className="rc-trip">
        <span className="rc-stop">
          <span className="rc-time">{formatShortTime(checkpoints[0].eta)}</span>
          <span className="rc-dot" />
          <span className="rc-place">{originLabel}</span>
        </span>
        <span className="rc-stop">
          <span className="rc-time">{formatShortTime(summary.arrival)}</span>
          <span className="rc-dot" />
          <span className="rc-place">{destinationLabel}</span>
        </span>
      </span>

      <span className="stats">
        <span className="stat">
          <span className="stat-value">{formatMiles(summary.severe_miles)}</span>
          <span className="stat-label">Severe mi</span>
        </span>
        <span className="stat">
          <span className="stat-value">{formatMiles(summary.high_miles)}</span>
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

      {/* Where the miles are, so that 0 / 0 / 0.00 reads as "all Low" and not as "not calculated". */}
      <span className="rc-risk">
        <span className="risk-bar" aria-hidden="true">
          {riskShares(summary.miles_by_level).map((share) => (
            <span key={share.level} style={{ flex: share.miles, background: RISK_COLORS[share.level] }} />
          ))}
        </span>
        <span className="risk-note">{riskNote(summary.miles_by_level)}</span>
      </span>
    </button>
  )
}
