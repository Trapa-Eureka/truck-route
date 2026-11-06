import { useGSAP } from '@gsap/react'
import gsap from 'gsap'
import { memo, useRef } from 'react'
import { fewerRoutesNotice, recommendationReason } from '../lib/reason'
import { prefersReducedMotion } from '../map/reveal'
import type { AnalyzeResponse } from '../types/api'
import CheckpointTimeline from './CheckpointTimeline'
import Icon from './Icon'
import NoTravelBanner from './NoTravelBanner'
import RouteCard from './RouteCard'

interface Props {
  data: AnalyzeResponse
  selectedId: string | null
  activeCheckpoint: number | null
  onSelectRoute: (id: string) => void
  onSelectCheckpoint: (index: number) => void
}

/**
 * Everything the panel shows after an analysis: the warning, the recommendation, the route cards
 * and the checkpoint list. Each new analysis plays a short entrance (the cards slide in one after
 * the other); choosing another route only changes the selection and does not replay it.
 */
function Results({ data, selectedId, activeCheckpoint, onSelectRoute, onSelectCheckpoint }: Props) {
  const root = useRef<HTMLDivElement>(null)
  const recommendedId = data.recommendation.route_id
  const selectedRoute = data.routes.find((route) => route.id === selectedId)
  const notice = fewerRoutesNotice(data.routes.length)

  useGSAP(
    () => {
      if (prefersReducedMotion()) return
      gsap.from('.enter', { opacity: 0, y: 16, duration: 0.5, ease: 'power2.out', stagger: 0.08, clearProps: 'all' })
    },
    { scope: root, dependencies: [data] },
  )

  return (
    <div className="results" ref={root}>
      <div className="enter">
        <NoTravelBanner routes={data.routes} />
      </div>

      {notice && <p className="notice enter">{notice}</p>}

      {recommendedId && (
        <div className="recommendation enter">
          <span className="recommendation-icon">
            <Icon name="check" size={18} />
          </span>
          <p>
            <strong>Recommended: Route {recommendedId}</strong>
            <span>{recommendationReason(data.recommendation, data.routes)}</span>
          </p>
        </div>
      )}

      <h2 className="section-title enter">
        Routes <span className="count">{data.routes.length}</span>
      </h2>
      <ul className="route-list">
        {data.routes.map((route) => (
          <li key={route.id} className="enter">
            <RouteCard
              route={route}
              originLabel={data.origin.label}
              destinationLabel={data.destination.label}
              selected={route.id === selectedId}
              recommended={route.id === recommendedId}
              onSelect={onSelectRoute}
            />
          </li>
        ))}
      </ul>

      {selectedRoute && (
        <div className="enter">
          <CheckpointTimeline route={selectedRoute} activeIndex={activeCheckpoint} onSelect={onSelectCheckpoint} />
        </div>
      )}
    </div>
  )
}

export default memo(Results)
