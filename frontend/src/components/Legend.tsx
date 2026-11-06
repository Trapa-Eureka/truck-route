import { OTHER_ROUTE_COLOR, RISK_COLORS, RISK_LABELS, RISK_LEVELS } from '../lib/risk'
import { heatRampCss } from '../map/heat'

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
      <p className="legend-note">Route and markers: when the truck gets there.</p>

      <p className="legend-title legend-shading">Shading: forecast at the slider's hour</p>
      <div className="legend-ramp-row">
        <div className="legend-ramp" style={{ background: heatRampCss(1.7) }} />
        <span className="legend-end">
          <span className="swatch" style={{ background: RISK_COLORS.no_travel }} />
          No Travel
        </span>
      </div>
      <div className="legend-bands" aria-hidden="true">
        <span>Low</span>
        <span>Moderate</span>
        <span>High</span>
        <span>Severe</span>
      </div>
      <p className="legend-note">Calm is clear; the color deepens as wind, rain or snow gets stronger.</p>
    </div>
  )
}
