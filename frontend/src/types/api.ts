// Mirrors docs/api-contract.md. If the two disagree, the contract document wins.

export type RiskLevel = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel'

/** Heatmap levels are integers in the same order as RiskLevel (0 = low ... 4 = no_travel). */
export type RiskLevelIndex = 0 | 1 | 2 | 3 | 4

export type IntervalMiles = 10 | 25 | 50

/** [lon, lat] (GeoJSON order). */
export type Coordinate = [number, number]

export interface AnalyzeRequest {
  origin: string
  destination: string
  /** ISO 8601, must not be in the past. */
  departure: string
  load_weight_lb: number
  interval_miles: IntervalMiles
}

export interface ResolvedPlace {
  query: string
  label: string
  lat: number
  lon: number
}

export interface WeatherValues {
  wind_mph: number
  rain_in_hr: number
  snow_in_hr: number
}

export interface Checkpoint {
  index: number
  /** Cumulative miles from the origin. */
  mile: number
  lat: number
  lon: number
  /** ISO 8601 UTC. */
  eta: string
  /** Miles of route this checkpoint stands for (midpoint to midpoint). */
  represents_miles: number
  weather: WeatherValues
  /** Base level per condition, before the load rules. */
  level_by: { wind: RiskLevel; rain: RiskLevel; snow: RiskLevel }
  /** Final level: highest condition level, then load rules applied. */
  level: RiskLevel
  /** True when a load rule raised the level. */
  load_escalated: boolean
}

export interface RouteSummary {
  distance_miles: number
  duration_minutes: number
  /** ISO 8601 UTC. */
  arrival: string
  miles_by_level: Record<RiskLevel, number>
  severe_miles: number
  high_miles: number
  /** Distance-weighted average of low=0 ... no_travel=4, two decimals. */
  avg_risk: number
  has_no_travel: boolean
}

export interface RouteSegment {
  level: RiskLevel
  coordinates: Coordinate[]
}

export interface Route {
  id: string
  summary: RouteSummary
  /** Simplified polyline for display. */
  geometry: Coordinate[]
  segments: RouteSegment[]
  checkpoints: Checkpoint[]
}

export type DecidedBy = 'severe_miles' | 'high_miles' | 'avg_risk' | 'duration' | 'only_candidate'

export interface Recommendation {
  /** null when every route contains a No Travel checkpoint. */
  route_id: string | null
  decided_by: DecidedBy | null
  versus_route_id: string | null
  /** Recommended route duration minus the compared route's; positive means slower. */
  duration_delta_minutes: number | null
  excluded_route_ids: string[]
  ranking: string[]
}

export interface AnalyzeResponse {
  origin: ResolvedPlace
  destination: ResolvedPlace
  /** 1 to 3 routes, exactly as many as the routing API returned. */
  routes: Route[]
  recommendation: Recommendation
}

export interface HeatmapResponse {
  /** ISO 8601 UTC, slider hour 0 (departure floored to the hour). */
  start: string
  /** Always 49 (hours 0 to 48). */
  hours: number
  points: Coordinate[]
  /** levels[hour][pointIndex] */
  levels: RiskLevelIndex[][]
}

export type ApiErrorCode =
  | 'INVALID_INPUT'
  | 'DEPARTURE_IN_PAST'
  | 'GEOCODE_NOT_FOUND'
  | 'NO_ROUTE'
  | 'FORECAST_OUT_OF_RANGE'
  | 'ROUTING_UNAVAILABLE'
  | 'WEATHER_UNAVAILABLE'

export interface ApiError {
  error: {
    code: ApiErrorCode
    message: string
    field?: 'origin' | 'destination' | 'departure' | 'load_weight_lb' | 'interval_miles'
    /** ISO 8601, only for FORECAST_OUT_OF_RANGE: the last hour with a forecast (omitted when unknown). */
    forecast_end?: string
  }
}
