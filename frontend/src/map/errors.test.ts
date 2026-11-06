import { describe, expect, it } from 'vitest'
import { MAP_NOT_LOADED, MAP_REFUSED, mapErrorMessage, messageAfterLoad } from './errors'

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

describe('messageAfterLoad', () => {
  it('takes "could not be loaded" down once the map has loaded after all', () => {
    expect(messageAfterLoad(MAP_NOT_LOADED)).toBeNull()
    expect(messageAfterLoad(mapErrorMessage(new Error('Failed to fetch'), false))).toBeNull()
  })

  it('keeps a refused key on screen: loading again does not fix that', () => {
    expect(messageAfterLoad(MAP_REFUSED)).toBe(MAP_REFUSED)
    expect(messageAfterLoad(mapErrorMessage({ status: 403 }, true))).toBe(MAP_REFUSED)
  })

  it('has nothing to do when there is no message', () => {
    expect(messageAfterLoad(null)).toBeNull()
  })
})
