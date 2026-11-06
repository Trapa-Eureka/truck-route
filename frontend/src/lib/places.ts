// The logic of the From / To fields that does not need a screen: when to search, how the keys move
// through the list, what to send, and what to say when "my location" fails. Kept apart from the
// component so it can be tested.

import type { IconName } from './icons'
import type { PickedPlace, PlaceInput, PlaceSuggestion } from '../types/api'

/** Fewer characters than this match too much to be worth a search. */
export const MIN_SEARCH_CHARS = 3
/** Wait this long after the last key before searching, so typing does not make a search per letter. */
export const SEARCH_DELAY_MS = 250

/** Whether a typed text is long enough to search for. */
export const worthSearching = (text: string) => text.trim().length >= MIN_SEARCH_CHARS

/** What the request carries for one end: the chosen place if the text still is that place, else the text. */
export function placeInput(text: string, picked: PickedPlace | null): PlaceInput {
  const typed = text.trim()
  if (picked !== null && picked.label === typed) return { label: picked.label, lat: picked.lat, lon: picked.lon }
  return typed
}

export type ListKey = 'ArrowDown' | 'ArrowUp'

/**
 * The highlighted row after an arrow key. -1 is "none" (the text itself). Down from the last row
 * and up from the first row wrap around; up from "none" goes to the last row.
 */
export function nextIndex(current: number, count: number, key: ListKey): number {
  if (count <= 0) return -1
  if (key === 'ArrowDown') return current >= count - 1 ? 0 : current + 1
  return current <= 0 ? count - 1 : current - 1
}

const KIND_ICONS: Record<PlaceSuggestion['kind'], IconName> = {
  place: 'building',
  address: 'mapPin',
  area: 'map',
}

export const suggestionIcon = (kind: PlaceSuggestion['kind']): IconName => KIND_ICONS[kind]

/** The numbers of GeolocationPositionError.code. */
const PERMISSION_DENIED = 1
const TIMEOUT = 3

/** What to tell the user when the browser could not give a position. */
export function locationMessage(code: number): string {
  if (code === PERMISSION_DENIED) {
    return 'Location access is blocked. Allow it in your browser’s site settings, or type an address.'
  }
  if (code === TIMEOUT) return 'Finding your location took too long. Try again, or type an address.'
  return 'Your location could not be found. Type an address instead.'
}
