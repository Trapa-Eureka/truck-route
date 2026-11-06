import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { ApiRequestError, fetchPlaceAt, fetchSuggestions } from '../lib/api'
import type { IconName } from '../lib/icons'
import {
  locationMessage,
  nextIndex,
  SEARCH_DELAY_MS,
  suggestionIcon,
  worthSearching,
  type ListKey,
} from '../lib/places'
import type { PickedPlace, PlaceSuggestion } from '../types/api'
import Icon from './Icon'

interface Props {
  label: string
  icon: IconName
  /** The text in the input. */
  value: string
  /** What the user typed or what a choice put there; a choice is reported with `onPick`. */
  onType: (text: string) => void
  onPick: (place: PickedPlace) => void
  /** True while `value` is a chosen place: no search is needed for it. */
  picked: boolean
  error?: string
  errorId: string
  ariaInvalid?: boolean
}

const hasGeolocation = typeof navigator !== 'undefined' && 'geolocation' in navigator

/**
 * A From / To field. As you type it lists matching places, addresses and cities (the server asks
 * TomTom); choosing one fixes the exact position. The target button fills the field with where you
 * are. Typing without choosing still works: the server then takes the best match for the text.
 */
export default function PlaceField({ label, icon, value, onType, onPick, picked, error, errorId, ariaInvalid }: Props) {
  const inputId = useId()
  const listId = useId()
  const [focused, setFocused] = useState(false)
  // The answer of a search, with the text it was for: an answer for older text is never shown.
  const [found, setFound] = useState<{ text: string; rows: PlaceSuggestion[]; failed: boolean } | null>(null)
  // The highlighted row, with the text it belongs to (a new text starts with none highlighted).
  const [highlight, setHighlight] = useState<{ text: string; index: number }>({ text: '', index: -1 })
  const [dismissedFor, setDismissedFor] = useState<string | null>(null) // Escape closes the list for this text
  const [locating, setLocating] = useState(false)
  const [locationError, setLocationError] = useState<string | null>(null)
  const locateRun = useRef(0)

  const text = value.trim()
  const searching = focused && !picked && worthSearching(text)

  // Search while typing: after a short pause, and only for the latest text.
  useEffect(() => {
    if (!searching) return
    const controller = new AbortController()
    const timer = setTimeout(() => {
      fetchSuggestions(text, controller.signal)
        .then((rows) => setFound({ text, rows, failed: false }))
        .catch((error: unknown) => {
          if (error instanceof DOMException && error.name === 'AbortError') return
          setFound({ text, rows: [], failed: true })
        })
    }, SEARCH_DELAY_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [searching, text])

  // The list is open while there is an answer for the text being typed.
  const answer = searching && found?.text === text && dismissedFor !== text ? found : null
  const open = answer !== null
  const rows = answer?.rows ?? []
  const active = highlight.text === text ? highlight.index : -1
  const setActive = (index: number) => setHighlight({ text, index })

  const choose = useCallback(
    (place: PickedPlace) => {
      setLocationError(null)
      onPick({ label: place.label, lat: place.lat, lon: place.lon })
    },
    [onPick],
  )

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    // While a Korean, Japanese or Chinese syllable is being composed, Enter and the arrows belong
    // to the input method: acting on them here would choose a row (or send the form) mid-word.
    if (event.nativeEvent.isComposing) return
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (rows.length === 0) return
      event.preventDefault()
      setActive(nextIndex(active, rows.length, event.key as ListKey))
    } else if (event.key === 'Enter' && active >= 0 && rows[active]) {
      event.preventDefault() // choose the row instead of sending the form
      choose(rows[active])
    } else if (event.key === 'Escape' && open) {
      event.stopPropagation()
      setDismissedFor(text) // closes the list until the text changes
    }
  }

  function locate() {
    const run = ++locateRun.current
    setLocationError(null)
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (position) => {
        fetchPlaceAt(position.coords.latitude, position.coords.longitude)
          .then((place) => {
            if (run !== locateRun.current) return
            choose(place)
          })
          .catch((error: unknown) => {
            if (run !== locateRun.current) return
            setLocationError(
              error instanceof ApiRequestError ? error.message : 'Your address could not be looked up. Type an address instead.',
            )
          })
          .finally(() => {
            if (run === locateRun.current) setLocating(false)
          })
      },
      (failure) => {
        if (run !== locateRun.current) return
        setLocationError(locationMessage(failure.code))
        setLocating(false)
      },
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 60_000 },
    )
  }

  // A pending location request must not fill the field after the component is gone.
  useEffect(
    () => () => {
      locateRun.current++
    },
    [],
  )

  const shownError = error ?? locationError ?? undefined
  const errorElementId = shownError ? errorId : undefined

  return (
    <div className="field">
      <label className="field-label" htmlFor={inputId}>
        {label}
      </label>
      <div className="combo">
        <span className="input" data-invalid={shownError ? 'true' : undefined}>
          <Icon name={icon} size={17} />
          <input
            id={inputId}
            type="text"
            role="combobox"
            aria-expanded={open}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
            aria-invalid={ariaInvalid || shownError ? true : undefined}
            aria-describedby={errorElementId}
            value={value}
            onChange={(event) => {
              // Typing while "my location" is still being looked up: the typed text wins, and the
              // late answer must not replace it.
              if (locating) {
                locateRun.current++
                setLocating(false)
              }
              onType(event.target.value)
            }}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            onKeyDown={handleKeyDown}
            placeholder="City, address or place name"
            autoComplete="off"
            spellCheck={false}
          />
          {hasGeolocation && (
            <button
              type="button"
              className="locate"
              onClick={locate}
              disabled={locating}
              aria-label={`Use my current location for ${label.toLowerCase()}`}
              title="Use my current location"
            >
              <Icon name={locating ? 'loader' : 'locate'} size={17} className={locating ? 'spin' : undefined} />
            </button>
          )}
        </span>

        {open && (
          <ul className="suggestions" role="listbox" id={listId} aria-label={`${label} suggestions`}>
            {rows.map((row, index) => (
              <li
                key={row.id}
                id={`${listId}-${index}`}
                role="option"
                aria-selected={index === active}
                data-active={index === active ? 'true' : undefined}
                // mousedown, not click: the input must not lose focus (which would close the list) first
                onMouseDown={(event) => {
                  event.preventDefault()
                  choose(row)
                }}
                onMouseEnter={() => setActive(index)}
              >
                <Icon name={suggestionIcon(row.kind)} size={16} />
                <span className="suggestion-text">
                  <span className="suggestion-name">{row.name}</span>
                  {row.detail && <span className="suggestion-detail">{row.detail}</span>}
                </span>
              </li>
            ))}
            {rows.length === 0 && (
              <li className="suggestion-empty" role="status">
                {answer?.failed
                  ? 'Suggestions are unavailable right now. You can still type the address.'
                  : 'No matches in the US. Try a city, an address or a place name.'}
              </li>
            )}
          </ul>
        )}
      </div>
      {shownError && (
        <span className="field-error" id={errorId} role="alert">
          {shownError}
        </span>
      )}
    </div>
  )
}
