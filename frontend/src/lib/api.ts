import type { AnalyzeRequest, AnalyzeResponse, ApiError, ApiErrorCode } from '../types/api'

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

function isApiError(body: unknown): body is ApiError {
  const error = (body as ApiError | null)?.error
  return typeof error?.code === 'string' && typeof error?.message === 'string'
}

/** POST /api/analyze. Throws ApiRequestError; an aborted request rethrows the AbortError. */
export async function analyze(request: AnalyzeRequest, signal?: AbortSignal): Promise<AnalyzeResponse> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}/api/analyze`, {
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
    throw new ApiRequestError(
      'UNEXPECTED_RESPONSE',
      `The server sent an unexpected response (HTTP ${response.status}). Please try again.`,
    )
  }

  if (!response.ok) {
    if (isApiError(body)) {
      const { code, message, field, forecast_end } = body.error
      throw new ApiRequestError(code, message, field, forecast_end)
    }
    throw new ApiRequestError(
      'UNEXPECTED_RESPONSE',
      `The server sent an unexpected response (HTTP ${response.status}). Please try again.`,
    )
  }
  return body as AnalyzeResponse
}
