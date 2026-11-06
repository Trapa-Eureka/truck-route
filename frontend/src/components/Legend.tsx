import { OTHER_ROUTE_COLOR, RISK_COLORS, RISK_LABELS, RISK_LEVELS } from '../lib/risk'

/** The color key. Always on screen, on top of the map. */
export default function Legend() {
  return (
    <div className="legend" role="group" aria-label="Risk levels">
      <p className="legend-title">Risk level</p>
      <ul>
        {RISK_LEVELS.map((level) => (
          <li key={level}>
            <span className="swatch" style={{ background: RISK_COLORS[level] }} />
            {RISK_LABELS[level]}
          </li>
        ))}
        <li>
          <span className="swatch" style={{ background: OTHER_ROUTE_COLOR }} />
          Other routes
        </li>
      </ul>
      <p className="legend-note">Route and dots: when the truck gets there. Shading: the forecast at the slider's hour.</p>
    </div>
  )
}
