import { afterEach, describe, expect, it, vi } from 'vitest'
import { analyze, ApiRequestError, fetchHeatmap } from './api'
import type { AnalyzeRequest } from '../types/api'

const REQUEST: AnalyzeRequest = {
  origin: 'Chicago, IL',
  destination: 'Denver, CO',
  departure: '2026-11-09T20:00:00Z',
  load_weight_lb: 42000,
  interval_miles: 25,
}

function respond(status: number, body: unknown) {
  return vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }))
}

afterEach(() => vi.unstubAllGlobals())

describe('analyze', () => {
  it('posts the request as JSON and returns the body', async () => {
    const fetchMock = respond(200, { routes: [] })
    vi.stubGlobal('fetch', fetchMock)
    const result = await analyze(REQUEST)
    expect(result).toEqual({ routes: [] })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/analyze')
    expect(init.method).toBe('POST')
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' })
    expect(JSON.parse(init.body)).toEqual(REQUEST)
  })

  it('passes the abort signal on', async () => {
    const fetchMock = respond(200, {})
    vi.stubGlobal('fetch', fetchMock)
    const controller = new AbortController()
    await analyze(REQUEST, controller.signal)
    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal)
  })

  it('turns an API error into an ApiRequestError with code, message and field', async () => {
    vi.stubGlobal(
      'fetch',
      respond(422, { error: { code: 'GEOCODE_NOT_FOUND', message: 'Could not find "x".', field: 'origin' } }),
    )
    const error = await analyze(REQUEST).catch((e) => e)
    expect(error).toBeInstanceOf(ApiRequestError)
    expect(error).toMatchObject({ code: 'GEOCODE_NOT_FOUND', message: 'Could not find "x".', field: 'origin' })
  })

  it('keeps forecast_end', async () => {
    vi.stubGlobal(
      'fetch',
      respond(422, { error: { code: 'FORECAST_OUT_OF_RANGE', message: 'm', forecast_end: '2026-11-21T18:00:00Z' } }),
    )
    const error = await analyze(REQUEST).catch((e) => e)
    expect(error.forecastEnd).toBe('2026-11-21T18:00:00Z')
    expect(error.field).toBeUndefined()
  })

  it('reports a network failure in plain words', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const error = await analyze(REQUEST).catch((e) => e)
    expect(error).toMatchObject({ code: 'NETWORK_ERROR' })
    expect(error.message).toMatch(/Could not reach the server/)
  })

  it('rethrows an abort so the caller can ignore it', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('aborted', 'AbortError')))
    const error = await analyze(REQUEST).catch((e) => e)
    expect(error).toBeInstanceOf(DOMException)
    expect(error.name).toBe('AbortError')
  })

  it('handles an HTML error page (a proxy or server crash)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>Bad gateway</html>', { status: 502 })))
    const error = await analyze(REQUEST).catch((e) => e)
    expect(error).toMatchObject({ code: 'UNEXPECTED_RESPONSE' })
    expect(error.message).toMatch(/HTTP 502/)
  })

  it.each([502, 503, 504])('says the server is not responding for a proxy error (HTTP %d)', async (status) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status })))
    const error = await analyze(REQUEST).catch((e) => e)
    expect(error).toMatchObject({ code: 'UNEXPECTED_RESPONSE' })
    expect(error.message).toContain(`The server is not responding (HTTP ${status})`)
  })

  it('tells a developer to start the backend, but not a visitor of the hosted app', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 502 })))
    vi.stubEnv('DEV', true)
    expect((await analyze(REQUEST).catch((e) => e)).message).toContain('runserver')
    vi.stubEnv('DEV', false)
    expect((await analyze(REQUEST).catch((e) => e)).message).not.toContain('runserver')
    vi.unstubAllEnvs()
  })

  it('keeps the plain wording for other unexpected statuses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>oops</html>', { status: 500 })))
    const error = await analyze(REQUEST).catch((e) => e)
    expect(error.message).toBe('The server sent an unexpected response (HTTP 500). Please try again.')
  })

  it('does not treat our own 502 (an API error body) as a proxy error', async () => {
    vi.stubGlobal(
      'fetch',
      respond(502, { error: { code: 'WEATHER_UNAVAILABLE', message: 'The weather service is not available right now.' } }),
    )
    const error = await analyze(REQUEST).catch((e) => e)
    expect(error).toMatchObject({ code: 'WEATHER_UNAVAILABLE' })
  })

  it('handles a JSON error body that is not ours', async () => {
    vi.stubGlobal('fetch', respond(500, { detail: 'oops' }))
    const error = await analyze(REQUEST).catch((e) => e)
    expect(error).toMatchObject({ code: 'UNEXPECTED_RESPONSE' })
  })

  it('handles a 200 that is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('hello', { status: 200 })))
    const error = await analyze(REQUEST).catch((e) => e)
    expect(error).toMatchObject({ code: 'UNEXPECTED_RESPONSE' })
  })
})


describe('fetchHeatmap', () => {
  it('posts the same body to /api/heatmap and returns the grid', async () => {
    const fetchMock = respond(200, { hours: 49, points: [], levels: [] })
    vi.stubGlobal('fetch', fetchMock)
    expect(await fetchHeatmap(REQUEST)).toEqual({ hours: 49, points: [], levels: [] })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/heatmap')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual(REQUEST)
  })

  it('reports API errors the same way as analyze', async () => {
    vi.stubGlobal(
      'fetch',
      respond(422, { error: { code: 'FORECAST_OUT_OF_RANGE', message: 'No forecast.', forecast_end: '2026-11-21T18:00:00Z' } }),
    )
    const error = await fetchHeatmap(REQUEST).catch((e) => e)
    expect(error).toBeInstanceOf(ApiRequestError)
    expect(error).toMatchObject({ code: 'FORECAST_OUT_OF_RANGE', forecastEnd: '2026-11-21T18:00:00Z' })
  })

  it('reports a network failure and rethrows an abort', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    expect(await fetchHeatmap(REQUEST).catch((e) => e)).toMatchObject({ code: 'NETWORK_ERROR' })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('aborted', 'AbortError')))
    expect((await fetchHeatmap(REQUEST).catch((e) => e)).name).toBe('AbortError')
  })
})
