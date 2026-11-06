import { memo, useCallback, useRef, useState } from 'react'
import AnalysisForm, { type FieldErrors } from './components/AnalysisForm'
import CheckpointTimeline from './components/CheckpointTimeline'
import ForecastSlider from './components/ForecastSlider'
import Legend from './components/Legend'
import MapView, { type CheckpointFocus } from './components/MapView'
import NoTravelBanner from './components/NoTravelBanner'
import RouteCard from './components/RouteCard'
import { analyze, ApiRequestError, fetchHeatmap } from './lib/api'
import { hourTime, truckDescription, truckPosition, type HeatmapStatus } from './lib/heatmap'
import { fewerRoutesNotice, recommendationReason } from './lib/reason'
import type { AnalyzeRequest, AnalyzeResponse, Route } from './types/api'

// The slider changes `hour` many times a second. These children do not depend on it, so they are
// kept from re-rendering (the checkpoint list can have over a hundred items).
const Timeline = memo(CheckpointTimeline)
const Card = memo(RouteCard)
const Banner = memo(NoTravelBanner)
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
  const notice = data ? fewerRoutesNotice(data.routes.length) : null

  return (
    <div className="app">
      <aside className="panel">
        <header className="panel-header">
          <h1>Spotter</h1>
          <p>Weather-aware truck routing</p>
        </header>

        <Form loading={status.kind === 'loading'} serverErrors={fieldErrors} onSubmit={handleSubmit} />

        <section className="results" aria-live="polite">
          {status.kind === 'loading' && (
            <p className="loading">Finding routes and checking the weather along them. This can take up to 10 seconds.</p>
          )}

          {status.kind === 'error' && !Object.keys(fieldErrors).length && (
            <p className="error-box" role="alert">
              {status.message}
            </p>
          )}

          {data && (
            <>
              <p className="trip">
                {data.origin.label} <span aria-hidden="true">→</span>
                <span className="sr-only"> to </span> {data.destination.label}
              </p>

              <Banner routes={data.routes} />

              {notice && <p className="notice">{notice}</p>}

              {recommendedId && (
                <p className="recommendation">
                  <strong>Recommended: Route {recommendedId}.</strong>{' '}
                  {recommendationReason(data.recommendation, data.routes)}
                </p>
              )}

              <ul className="route-list">
                {data.routes.map((route) => (
                  <li key={route.id}>
                    <Card
                      route={route}
                      selected={route.id === selectedId}
                      recommended={route.id === recommendedId}
                      onSelect={selectRoute}
                    />
                  </li>
                ))}
              </ul>

              {selectedRoute && (
                <Timeline route={selectedRoute} activeIndex={focus?.index ?? null} onSelect={focusCheckpoint} />
              )}
            </>
          )}
        </section>

        <footer className="credits">
          Weather data by{' '}
          <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">
            Open-Meteo.com
          </a>{' '}
          (
          <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">
            CC BY 4.0
          </a>
          ). Map © TomTom.
        </footer>
      </aside>

      <main className="map-area">
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
