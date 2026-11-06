// Mirrors docs/api-contract.md. If the two disagree, the contract document wins.

export type RiskLevel = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel'

export type IntervalMiles = 10 | 25 | 50

/** [lon, lat] (GeoJSON order). */
export type Coordinate = [number, number]

/** A place the user chose from the list, or "my location": sent as it is, no address lookup. */
export interface PickedPlace {
  label: string
  lat: number
  lon: number
}

/** What the user typed, or a place they chose. */
export type PlaceInput = string | PickedPlace

/** One choice in the From / To list (GET /api/places). */
export interface PlaceSuggestion extends PickedPlace {
  id: string
  /** `place` (a building, a station ...), `address`, or `area` (a city, a neighbourhood). */
  kind: 'place' | 'address' | 'area'
  /** The main line ("Willis Tower"). */
  name: string
  /** The line under it (the address). */
  detail: string
}

export interface AnalyzeRequest {
  origin: PlaceInput
  destination: PlaceInput
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
  /** Miles at each level, two decimals. A level that has any miles is never 0. */
  miles_by_level: Record<RiskLevel, number>
  /** Two decimals; above 0 whenever the route has a Severe (High) stretch, however short. */
  severe_miles: number
  high_miles: number
  /** Distance-weighted average of low=0 ... no_travel=4, four decimals; never 0 unless all Low. */
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
  /** ISO 8601 UTC, slider hour 0 (the departure rounded to the nearest hour). */
  start: string
  /** Always 49 (hours 0 to 48). */
  hours: number
  /** Grid spacing in degrees (0.5, or coarser for very large trips). */
  spacing_deg: number
  points: Coordinate[]
  /**
   * scores[hour][pointIndex]: how bad the weather is, from 0 (calm) to 4 (No Travel), with two
   * decimals. The whole part is the risk level (0 low ... 4 no_travel); the decimals say how far
   * through the level the weather is, so 5 mph and 20 mph of wind (both Low) differ.
   */
  scores: number[][]
}

export type ApiErrorCode =
  | 'INVALID_INPUT'
  | 'DEPARTURE_IN_PAST'
  | 'GEOCODE_NOT_FOUND'
  | 'NO_ROUTE'
  | 'FORECAST_OUT_OF_RANGE'
  | 'ROUTING_UNAVAILABLE'
  | 'WEATHER_UNAVAILABLE'
  | 'RATE_LIMITED'
  | 'NOT_FOUND'
  | 'INTERNAL_ERROR'

export interface ApiError {
  error: {
    code: ApiErrorCode
    message: string
    field?: 'origin' | 'destination' | 'departure' | 'load_weight_lb' | 'interval_miles'
    /** ISO 8601, only for FORECAST_OUT_OF_RANGE: the last hour with a forecast (omitted when unknown). */
    forecast_end?: string
    /** Only for RATE_LIMITED: how long to wait before the next request. */
    retry_after_seconds?: number
  }
}
