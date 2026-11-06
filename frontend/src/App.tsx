import { lazy, memo, Suspense, useCallback, useRef, useState } from 'react'
import AnalysisForm, { type FieldErrors } from './components/AnalysisForm'
import ForecastSlider from './components/ForecastSlider'
import Legend from './components/Legend'
import Results from './components/Results'
import TripBar from './components/TripBar'
import { analyze, ApiRequestError, fetchHeatmap } from './lib/api'
import { hourTime, truckDescription, truckPosition, type HeatmapStatus } from './lib/heatmap'
import type { CheckpointFocus } from './map/focus'
import type { AnalyzeRequest, AnalyzeResponse, Route } from './types/api'

// The map library is about a megabyte. Loading it on demand lets the form appear first, and the
// map chunk downloads while the person types.
const MapView = lazy(() => import('./components/MapView'))

// The slider changes `hour` many times a second. The form and the results do not depend on it, so
// they are kept from re-rendering (the checkpoint list can have over a hundred items).
const Form = memo(AnalysisForm)

// A stable empty list, so the map does not see a "new" routes value on every render.
const NO_ROUTES: readonly Route[] = []

type Status =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'done'; data: AnalyzeResponse }

export default function App() {
  const [status, setStatus] = useState<Status>({ kind: 'idle' })
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [focus, setFocus] = useState<CheckpointFocus | null>(null)
  const [heatmap, setHeatmap] = useState<HeatmapStatus>({ kind: 'idle' })
  const [hour, setHour] = useState(0)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const pending = useRef<AbortController | null>(null)
  const pendingHeatmap = useRef<AbortController | null>(null)

  const selectRoute = useCallback((id: string) => {
    setSelectedId(id)
    setFocus(null) // a checkpoint belongs to one route
  }, [])

  const focusCheckpoint = useCallback((index: number) => setFocus({ index, fly: true }), [])
  const selectCheckpointOnMap = useCallback(
    (index: number | null) => setFocus(index === null ? null : { index, fly: false }),
    [],
  )

  // The forecast heatmap arrives after the routes, so the routes can be read while it loads.
  const loadHeatmap = useCallback(async (request: AnalyzeRequest) => {
    pendingHeatmap.current?.abort()
    const controller = new AbortController()
    pendingHeatmap.current = controller

    setHeatmap({ kind: 'loading' })
    setHour(0)
    try {
      const data = await fetchHeatmap(request, controller.signal)
      setHeatmap({ kind: 'done', data })
    } catch (error) {
      if (controller.signal.aborted) return
      const message = error instanceof ApiRequestError ? error.message : 'Something went wrong. Please try again.'
      setHeatmap({ kind: 'error', message })
    }
  }, [])

  const handleSubmit = useCallback(async (request: AnalyzeRequest) => {
    pending.current?.abort() // only the latest request counts
    pendingHeatmap.current?.abort()
    const controller = new AbortController()
    pending.current = controller

    setStatus({ kind: 'loading' })
    setFieldErrors({})
    setFocus(null)
    setHeatmap({ kind: 'idle' })
    try {
      const data = await analyze(request, controller.signal)
      setStatus({ kind: 'done', data })
      setSelectedId(data.recommendation.route_id ?? data.routes[0]?.id ?? null)
      void loadHeatmap(request)
    } catch (error) {
      if (controller.signal.aborted) return
      const known = error instanceof ApiRequestError ? error : null
      const message = known?.message ?? 'Something went wrong. Please try again.'
      if (known?.field) setFieldErrors({ [known.field]: message })
      setStatus({ kind: 'error', message })
    }
  }, [loadHeatmap])

  const data = status.kind === 'done' ? status.data : null
  const routes = data?.routes ?? NO_ROUTES
  const recommendedId = data?.recommendation.route_id ?? null
  const selectedRoute = routes.find((route) => route.id === selectedId)

  // Where the truck is on the selected route at the slider's hour.
  const heatmapData = heatmap.kind === 'done' ? heatmap.data : null
  const truck =
    heatmapData && selectedRoute ? truckPosition(selectedRoute, hourTime(heatmapData.start, hour)) : null

  return (
    <div className="app">
      <aside className="panel">
        <header className="panel-header">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" width="34" height="34">
              <rect width="32" height="32" rx="10" fill="currentColor" />
              <path d="M7 22c4.5 0 4-12 9-12s4.500 12 9 12" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" />
              <circle cx="7" cy="22" r="2.4" fill="#fff" />
              <circle cx="25" cy="22" r="2.4" fill="#fff" />
            </svg>
          </span>
          <div>
            <h1>Spotter</h1>
            <p>Weather-aware truck routing</p>
          </div>
        </header>

        <Form loading={status.kind === 'loading'} serverErrors={fieldErrors} onSubmit={handleSubmit} />

        <section className="results-area" aria-live="polite">
          {status.kind === 'loading' && (
            <p className="loading">
              <span className="spinner" aria-hidden="true" />
              Finding routes and checking the weather along them. This takes 5 to 10 seconds, and up to 30 for a very long trip.
            </p>
          )}

          {status.kind === 'error' && !Object.keys(fieldErrors).length && (
            <p className="error-box" role="alert">
              {status.message}
            </p>
          )}

          {data && (
            <Results
              data={data}
              selectedId={selectedId}
              activeCheckpoint={focus?.index ?? null}
              onSelectRoute={selectRoute}
              onSelectCheckpoint={focusCheckpoint}
            />
          )}
        </section>

        <footer className="credits">
          Weather forecast by{' '}
          <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">
            Open-Meteo.com
          </a>{' '}
          (
          <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">
            CC BY 4.0
          </a>
          ), hourly model data, cached up to an hour. Map © TomTom.
        </footer>
      </aside>

      <main className="map-area">
        <Suspense fallback={<p className="map-loading">Loading map…</p>}>
          <MapView
            routes={routes}
            selectedId={selectedId}
            origin={data?.origin ?? null}
            destination={data?.destination ?? null}
            focus={focus}
            heatmap={heatmapData}
            hour={hour}
            truck={truck?.position ?? null}
            onSelectRoute={selectRoute}
            onSelectCheckpoint={selectCheckpointOnMap}
          />
        </Suspense>
        <TripBar route={selectedRoute} recommended={selectedRoute?.id === recommendedId} />
        <ForecastSlider
          status={heatmap}
          hour={hour}
          onHourChange={setHour}
          truckText={truck && selectedRoute ? truckDescription(truck, selectedRoute.id) : null}
        />
        <Legend />
      </main>
    </div>
  )
}
