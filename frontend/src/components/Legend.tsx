import { RISK_COLORS, RISK_LABELS, RISK_LEVELS } from '../lib/risk'

/**
 * The color key for the routes and the checkpoints. Always on screen. It is small on purpose: it
 * sits in a corner of the map and must not cover the routes (the scale of the weather shading is
 * with the forecast slider, which it belongs to).
 */
export default function Legend() {
  return (
    <div className="legend" role="group" aria-label="Risk levels" data-map-overlay>
      <p className="legend-title">Risk at arrival time</p>
      <ul>
        {RISK_LEVELS.map((level) => (
          <li key={level}>
            <span className="swatch" style={{ background: RISK_COLORS[level] }} />
            {RISK_LABELS[level]}
          </li>
        ))}
      </ul>
      <p className="legend-note">Other routes: thinner, paler</p>
    </div>
  )
}
