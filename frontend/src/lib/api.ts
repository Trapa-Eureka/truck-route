import type { AnalyzeRequest, AnalyzeResponse, ApiError, ApiErrorCode, HeatmapResponse } from '../types/api'

// Empty in development (Vite proxies /api to Django). Set VITE_API_BASE_URL for a separate API host.
const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ''

export type RequestErrorCode = ApiErrorCode | 'NETWORK_ERROR' | 'UNEXPECTED_RESPONSE'

/** A failed API call, with the error code and message the backend sent. */
export class ApiRequestError extends Error {
  readonly code: RequestErrorCode
  readonly field?: NonNullable<ApiError['error']['field']>
  readonly forecastEnd?: string

  constructor(code: RequestErrorCode, message: string, field?: ApiRequestError['field'], forecastEnd?: string) {
    super(message)
    this.name = 'ApiRequestError'
    this.code = code
    this.field = field
    this.forecastEnd = forecastEnd
  }
}

const GATEWAY_STATUSES = new Set([502, 503, 504])

/**
 * An answer that is not in our error format. A 502/503/504 here comes from a proxy that cannot
 * reach the API, not from our backend: in development that almost always means Django is not running.
 */
function unexpectedResponse(status: number): ApiRequestError {
  if (GATEWAY_STATUSES.has(status)) {
    const hint = import.meta.env.DEV
      ? ' Is the backend running? Start it with "uv run python manage.py runserver" in the backend folder.'
      : ''
    return new ApiRequestError(
      'UNEXPECTED_RESPONSE',
      `The server is not responding (HTTP ${status}). Please try again in a moment.${hint}`,
    )
  }
  return new ApiRequestError('UNEXPECTED_RESPONSE', `The server sent an unexpected response (HTTP ${status}). Please try again.`)
}

function isApiError(body: unknown): body is ApiError {
  const error = (body as ApiError | null)?.error
  return typeof error?.code === 'string' && typeof error?.message === 'string'
}

/** POST a JSON body. Throws ApiRequestError; an aborted request rethrows the AbortError. */
async function post<T>(path: string, request: AnalyzeRequest, signal?: AbortSignal): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiRequestError('NETWORK_ERROR', 'Could not reach the server. Check your connection and try again.')
  }

  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw unexpectedResponse(response.status)
  }

  if (!response.ok) {
    if (isApiError(body)) {
      const { code, message, field, forecast_end } = body.error
      throw new ApiRequestError(code, message, field, forecast_end)
    }
    throw unexpectedResponse(response.status)
  }
  return body as T
}

/** POST /api/analyze: routes, checkpoints, risk summary and recommendation. */
export function analyze(request: AnalyzeRequest, signal?: AbortSignal): Promise<AnalyzeResponse> {
  return post<AnalyzeResponse>('/api/analyze', request, signal)
}

/** POST /api/heatmap: the risk level on a grid around the routes for hours 0 to 48. */
export function fetchHeatmap(request: AnalyzeRequest, signal?: AbortSignal): Promise<HeatmapResponse> {
  return post<HeatmapResponse>('/api/heatmap', request, signal)
}
