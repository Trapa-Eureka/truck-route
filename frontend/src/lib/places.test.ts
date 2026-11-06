import { describe, expect, it } from 'vitest'
import { locationMessage, MIN_SEARCH_CHARS, nextIndex, placeInput, SEARCH_DELAY_MS, suggestionIcon, worthSearching } from './places'

describe('worthSearching', () => {
  it('needs the minimum number of characters, not counting the spaces around', () => {
    expect(MIN_SEARCH_CHARS).toBe(3)
    expect(worthSearching('ch')).toBe(false)
    expect(worthSearching('chi')).toBe(true)
    expect(worthSearching('  ch  ')).toBe(false)
    expect(worthSearching('  chi ')).toBe(true)
    expect(worthSearching('')).toBe(false)
  })

  it('counts the middle spaces', () => {
    expect(worthSearching('a b')).toBe(true)
  })
})

describe('SEARCH_DELAY_MS', () => {
  it('waits long enough that fast typing is not a search per letter, but not so long that the list feels slow', () => {
    expect(SEARCH_DELAY_MS).toBeGreaterThanOrEqual(150)
    expect(SEARCH_DELAY_MS).toBeLessThanOrEqual(500)
  })
})

describe('placeInput', () => {
  const picked = { label: 'Willis Tower, 233 South Wacker Drive, Chicago, IL 60606', lat: 41.8789, lon: -87.6359 }

  it('is the typed text, trimmed, when nothing was chosen', () => {
    expect(placeInput('  Chicago, IL ', null)).toBe('Chicago, IL')
  })

  it('is the chosen place while the text still is its label', () => {
    expect(placeInput(picked.label, picked)).toEqual(picked)
    expect(placeInput(`  ${picked.label} `, picked)).toEqual(picked)
  })

  it('is the text again once it was edited, even if a place is still remembered', () => {
    expect(placeInput('Willis Tower, Denver', picked)).toBe('Willis Tower, Denver')
    expect(placeInput('', picked)).toBe('')
  })

  it('sends only label, lat and lon of a chosen place', () => {
    const extra = { ...picked, id: 'x', kind: 'place', name: 'Willis Tower', detail: 'd' }
    expect(placeInput(picked.label, extra as typeof picked)).toEqual(picked)
  })
})

describe('nextIndex', () => {
  it('goes down one row at a time and wraps from the last row to the first', () => {
    expect(nextIndex(-1, 3, 'ArrowDown')).toBe(0)
    expect(nextIndex(0, 3, 'ArrowDown')).toBe(1)
    expect(nextIndex(1, 3, 'ArrowDown')).toBe(2)
    expect(nextIndex(2, 3, 'ArrowDown')).toBe(0)
  })

  it('goes up one row at a time, from "none" to the last row, and wraps from the first to the last', () => {
    expect(nextIndex(2, 3, 'ArrowUp')).toBe(1)
    expect(nextIndex(1, 3, 'ArrowUp')).toBe(0)
    expect(nextIndex(0, 3, 'ArrowUp')).toBe(2)
    expect(nextIndex(-1, 3, 'ArrowUp')).toBe(2)
  })

  it('stays on "none" when there are no rows', () => {
    expect(nextIndex(-1, 0, 'ArrowDown')).toBe(-1)
    expect(nextIndex(2, 0, 'ArrowUp')).toBe(-1)
  })

  it('works with a single row', () => {
    expect(nextIndex(-1, 1, 'ArrowDown')).toBe(0)
    expect(nextIndex(0, 1, 'ArrowDown')).toBe(0)
    expect(nextIndex(0, 1, 'ArrowUp')).toBe(0)
  })
})

describe('suggestionIcon', () => {
  it('has a different picture for a place, an address and an area', () => {
    const icons = (['place', 'address', 'area'] as const).map(suggestionIcon)
    expect(new Set(icons).size).toBe(3)
  })
})

describe('locationMessage', () => {
  it('tells a blocked permission apart from a timeout and from anything else', () => {
    const denied = locationMessage(1)
    const timeout = locationMessage(3)
    const other = locationMessage(2)
    expect(new Set([denied, timeout, other]).size).toBe(3)
    expect(denied).toMatch(/blocked/i)
    expect(timeout).toMatch(/too long/i)
    expect(other).toMatch(/could not be found/i)
  })

  it('always offers typing an address', () => {
    for (const code of [0, 1, 2, 3, 99]) expect(locationMessage(code)).toMatch(/type an address/i)
  })
})
