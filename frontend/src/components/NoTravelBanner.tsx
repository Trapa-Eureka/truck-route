import { describeNoTravel, noTravelHeadline, noTravelWarnings } from '../lib/reason'
import type { Route } from '../types/api'

/** Large warning shown whenever any route has a No Travel stretch. */
export default function NoTravelBanner({ routes }: { routes: readonly Route[] }) {
  const headline = noTravelHeadline(routes)
  if (headline === null) return null

  const everyRoute = routes.every((r) => r.summary.has_no_travel)
  return (
    <div className="no-travel-banner" role="alert">
      <p className="no-travel-title">{headline}</p>
      <p>
        {everyRoute
          ? 'No route is recommended. Try a different departure time.'
          : 'Blocked routes are left out of the recommendation.'}
      </p>
      <ul>
        {noTravelWarnings(routes).map((warning) => (
          <li key={warning.routeId}>{describeNoTravel(warning)}</li>
        ))}
      </ul>
    </div>
  )
}
