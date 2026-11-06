import type { CSSProperties } from 'react'
import { forecastHourLabel, type HeatmapStatus } from '../lib/heatmap'
import Icon from './Icon'

interface Props {
  status: HeatmapStatus
  hour: number
  onHourChange: (hour: number) => void
  /** Where the truck is at this hour, already worded, or null. */
  truckText: string | null
}

/** The 0 to 48 hour forecast slider, over the bottom of the map. */
export default function ForecastSlider({ status, hour, onHourChange, truckText }: Props) {
  if (status.kind === 'idle') return null

  return (
    <section className="forecast" aria-label="Forecast time">
      {status.kind === 'loading' && <p className="forecast-message">Loading the 48-hour forecast…</p>}

      {status.kind === 'error' && (
        <p className="forecast-message error" role="alert">
          Forecast heatmap unavailable. {status.message}
        </p>
      )}

      {status.kind === 'done' && (
        <>
          <label className="forecast-label" htmlFor="forecast-hour">
            <span className="forecast-title">
              <Icon name="clock" size={16} />
              Forecast hour
            </span>
            <output htmlFor="forecast-hour">{forecastHourLabel(status.data.start, hour)}</output>
          </label>
          <input
            id="forecast-hour"
            type="range"
            min={0}
            max={status.data.hours - 1}
            step={1}
            value={hour}
            style={{ '--fill': `${(hour / (status.data.hours - 1)) * 100}%` } as CSSProperties}
            onChange={(event) => onHourChange(Number(event.target.value))}
            aria-valuetext={forecastHourLabel(status.data.start, hour)}
          />
          <div className="forecast-scale" aria-hidden="true">
            <span>Departure</span>
            <span>+24 h</span>
            <span>+48 h</span>
          </div>
          {truckText && (
            <p className="forecast-truck">
              <Icon name="truck" size={16} />
              {truckText}
            </p>
          )}
        </>
      )}
    </section>
  )
}
