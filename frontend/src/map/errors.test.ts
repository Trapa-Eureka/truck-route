import { describe, expect, it } from 'vitest'
import { mapErrorMessage } from './errors'

describe('mapErrorMessage', () => {
  it.each([401, 403])('says the key was refused for HTTP %d, even after the map loaded', (status) => {
    expect(mapErrorMessage({ status }, true)).toMatch(/refused.*key/)
    expect(mapErrorMessage({ status }, false)).toMatch(/refused.*key/)
  })

  it('says the map could not be loaded when the style fails to load', () => {
    expect(mapErrorMessage(new Error('Failed to fetch'), false)).toMatch(/could not be loaded/)
    expect(mapErrorMessage({ status: 500 }, false)).toMatch(/could not be loaded/)
    expect(mapErrorMessage(undefined, false)).toMatch(/could not be loaded/)
  })

  it.each([404, 204, 500, 429, undefined])('ignores a single failed tile (status %s) once the map works', (status) => {
    expect(mapErrorMessage({ status }, true)).toBeNull()
  })

  it('ignores errors that are not objects once the map works', () => {
    expect(mapErrorMessage(null, true)).toBeNull()
    expect(mapErrorMessage('boom', true)).toBeNull()
  })

  it('does not take other statuses for a refused key', () => {
    expect(mapErrorMessage({ status: 400 }, true)).toBeNull()
    expect(mapErrorMessage({ status: '403' }, true)).toBeNull()
  })
})
