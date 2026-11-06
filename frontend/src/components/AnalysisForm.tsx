import { useState, type FormEvent, type ReactNode } from 'react'
import { defaultDeparture, departureToIso } from '../lib/format'
import type { IconName } from '../lib/icons'
import type { AnalyzeRequest, ApiError, IntervalMiles } from '../types/api'
import Icon from './Icon'

export type FieldName = NonNullable<ApiError['error']['field']>
export type FieldErrors = Partial<Record<FieldName, string>>

const INTERVALS: IntervalMiles[] = [10, 25, 50]
const TIME_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone

interface Props {
  loading: boolean
  /** Errors the server reported for a specific field. */
  serverErrors: FieldErrors
  onSubmit: (request: AnalyzeRequest) => void
}

/** Checks the form before anything is sent. Returns the request, or the problems. */
function readForm(values: {
  origin: string
  destination: string
  departure: string
  load: string
  interval: IntervalMiles
}): { request: AnalyzeRequest } | { errors: FieldErrors } {
  const errors: FieldErrors = {}
  if (!values.origin.trim()) errors.origin = 'Enter the origin.'
  if (!values.destination.trim()) errors.destination = 'Enter the destination.'

  const departure = departureToIso(values.departure)
  if (departure === null) errors.departure = 'Enter the departure date and time.'

  const load = values.load.trim() === '' ? Number.NaN : Number(values.load)
  if (!Number.isFinite(load)) errors.load_weight_lb = 'Enter the load weight in pounds.'
  else if (load < 0) errors.load_weight_lb = 'The load weight cannot be negative.'

  if (Object.keys(errors).length > 0 || departure === null) return { errors }
  return {
    request: {
      origin: values.origin.trim(),
      destination: values.destination.trim(),
      departure,
      load_weight_lb: load,
      interval_miles: values.interval,
    },
  }
}

/** A labelled input with its icon inside, and the field's error under it. */
function Field({ label, icon, error, name, children }: { label: string; icon: IconName; error?: string; name: FieldName; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      <span className="input" data-invalid={error ? 'true' : undefined}>
        <Icon name={icon} size={17} />
        {children}
      </span>
      {error && (
        <span className="field-error" id={`${name}-error`} role="alert">
          {error}
        </span>
      )}
    </label>
  )
}

export default function AnalysisForm({ loading, serverErrors, onSubmit }: Props) {
  const [origin, setOrigin] = useState('Chicago, IL')
  const [destination, setDestination] = useState('Denver, CO')
  const [departure, setDeparture] = useState(() => defaultDeparture())
  const [load, setLoad] = useState('42000')
  const [interval, setInterval] = useState<IntervalMiles>(25)
  const [localErrors, setLocalErrors] = useState<FieldErrors>({})

  // A local problem is shown first; otherwise whatever the server said about that field.
  const errors: FieldErrors = { ...serverErrors, ...localErrors }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const result = readForm({ origin, destination, departure, load, interval })
    if ('errors' in result) {
      setLocalErrors(result.errors)
      return
    }
    setLocalErrors({})
    onSubmit(result.request)
  }

  const aria = (name: FieldName) => ({
    'aria-invalid': errors[name] ? true : undefined,
    'aria-describedby': errors[name] ? `${name}-error` : undefined,
  })

  return (
    <form className="form" onSubmit={handleSubmit} noValidate>
      <Field label="From" icon="circleDot" name="origin" error={errors.origin}>
        <input
          type="text"
          value={origin}
          onChange={(e) => setOrigin(e.target.value)}
          placeholder="City, state or address"
          autoComplete="off"
          {...aria('origin')}
        />
      </Field>

      <Field label="To" icon="flag" name="destination" error={errors.destination}>
        <input
          type="text"
          value={destination}
          onChange={(e) => setDestination(e.target.value)}
          placeholder="City, state or address"
          autoComplete="off"
          {...aria('destination')}
        />
      </Field>

      <div className="field-row">
        <Field label="Departure" icon="calendarClock" name="departure" error={errors.departure}>
          <input type="datetime-local" value={departure} onChange={(e) => setDeparture(e.target.value)} {...aria('departure')} />
        </Field>

        <Field label="Load (lb)" icon="weight" name="load_weight_lb" error={errors.load_weight_lb}>
          <input
            type="number"
            inputMode="numeric"
            min={0}
            step={100}
            value={load}
            onChange={(e) => setLoad(e.target.value)}
            {...aria('load_weight_lb')}
          />
        </Field>
      </div>
      <p className="hint">Departure is in your time zone ({TIME_ZONE}).</p>

      <fieldset className="field interval">
        <legend className="field-label">Weather checkpoint every</legend>
        <div className="segmented">
          {INTERVALS.map((miles) => (
            <label key={miles} className={interval === miles ? 'selected' : undefined}>
              <input
                type="radio"
                name="interval"
                value={miles}
                checked={interval === miles}
                onChange={() => setInterval(miles)}
              />
              {miles} mi
            </label>
          ))}
        </div>
        {errors.interval_miles && (
          <span className="field-error" id="interval_miles-error" role="alert">
            {errors.interval_miles}
          </span>
        )}
      </fieldset>

      <button type="submit" className="primary" disabled={loading}>
        {loading ? 'Analyzing…' : 'Analyze routes'}
        {!loading && <Icon name="arrowRight" size={17} />}
      </button>
    </form>
  )
}
