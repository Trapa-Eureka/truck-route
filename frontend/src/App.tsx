import { useRef, useState } from 'react'
import AnalysisForm, { type FieldErrors } from './components/AnalysisForm'
import MapView from './components/MapView'
import NoTravelBanner from './components/NoTravelBanner'
import RouteCard from './components/RouteCard'
import { analyze, ApiRequestError } from './lib/api'
import { fewerRoutesNotice, recommendationReason } from './lib/reason'
import type { AnalyzeRequest, AnalyzeResponse, Route } from './types/api'

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
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const pending = useRef<AbortController | null>(null)

  async function handleSubmit(request: AnalyzeRequest) {
    pending.current?.abort() // only the latest request counts
    const controller = new AbortController()
    pending.current = controller

    setStatus({ kind: 'loading' })
    setFieldErrors({})
    try {
      const data = await analyze(request, controller.signal)
      setStatus({ kind: 'done', data })
      setSelectedId(data.recommendation.route_id ?? data.routes[0]?.id ?? null)
    } catch (error) {
      if (controller.signal.aborted) return
      const known = error instanceof ApiRequestError ? error : null
      const message = known?.message ?? 'Something went wrong. Please try again.'
      if (known?.field) setFieldErrors({ [known.field]: message })
      setStatus({ kind: 'error', message })
    }
  }

  const data = status.kind === 'done' ? status.data : null
  const routes = data?.routes ?? NO_ROUTES
  const recommendedId = data?.recommendation.route_id ?? null
  const notice = data ? fewerRoutesNotice(data.routes.length) : null

  return (
    <div className="app">
      <aside className="panel">
        <header className="panel-header">
          <h1>Spotter</h1>
          <p>Weather-aware truck routing</p>
        </header>

        <AnalysisForm loading={status.kind === 'loading'} serverErrors={fieldErrors} onSubmit={handleSubmit} />

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

              <NoTravelBanner routes={data.routes} />

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
                    <RouteCard
                      route={route}
                      selected={route.id === selectedId}
                      recommended={route.id === recommendedId}
                      onSelect={setSelectedId}
                    />
                  </li>
                ))}
              </ul>
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
          onSelectRoute={setSelectedId}
        />
      </main>
    </div>
  )
}
