import { iconMarkup } from '../lib/icons'

export type PinKind = 'origin' | 'destination'

/**
 * The label card above the origin or the destination: a picture, "Origin" or "Destination" in
 * small gray, and the place's name. `element` is what the map positions (it moves it with a CSS
 * transform), so the animation runs on the `card` inside it instead.
 */
export function createPin(kind: PinKind, name: string): { element: HTMLElement; card: HTMLElement } {
  const element = document.createElement('div')
  element.className = `pin pin-${kind}`

  const card = document.createElement('div')
  card.className = 'pin-card'

  const badge = document.createElement('span')
  badge.className = 'pin-icon'
  badge.innerHTML = iconMarkup(kind === 'origin' ? 'circleDot' : 'flag', 16)

  const text = document.createElement('span')
  text.className = 'pin-text'
  const caption = document.createElement('small')
  caption.textContent = kind === 'origin' ? 'Origin' : 'Destination'
  const place = document.createElement('strong')
  place.textContent = name // textContent only: the name comes from the address lookup
  text.append(caption, place)

  card.append(badge, text)
  element.append(card)
  return { element, card }
}
