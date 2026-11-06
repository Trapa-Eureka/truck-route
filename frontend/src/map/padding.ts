// How much room the map leaves around the routes when it zooms to them. The trip bar, the legend
// and the forecast slider float over the map, and the origin and the destination each carry a
// label card above their dot: a route that runs to the edge of the map would put its ends (often
// the destination, which is what the driver looks for first) under one of them. So the padding is
// taken from where those overlays really are on screen, not from fixed numbers that are right for
// one window size only.

export interface Box {
  left: number
  top: number
  right: number
  bottom: number
}

export interface Padding {
  top: number
  bottom: number
  left: number
  right: number
}

/** The label card above an end point: its height with the pointer and the gap to the dot. */
export const PIN_CARD_HEIGHT = 76
/** Half the width of the widest label card (it is centered on its dot). */
export const PIN_CARD_HALF_WIDTH = 140
/** Free space between an overlay and the nearest part of a route. */
export const MARGIN = 20
/** The routes always keep at least this share of the map's height ... */
export const MIN_SHARE = 0.35
/** ... and of its width (more: on a phone the map is narrow, and a label card may reach past its edge). */
export const MIN_WIDTH_SHARE = 0.5

const overlaps = (a: Box, b: Box) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom

/**
 * Padding for `fitBounds`, from the map's box and the boxes of the overlays (all in the same
 * coordinates, for example from getBoundingClientRect).
 *
 * An overlay in the upper half of the map pushes the top edge down to its bottom, one in the
 * lower half pushes the bottom edge up to its top; an overlay that does not touch the map (on a
 * small screen they sit under it) counts for nothing. The top also leaves room for the label card
 * of an end point, the sides for half its width. If that leaves too little of the map (a small
 * window), every side is cut back in proportion, so the map never ends up with no room at all
 * (in which case the map library gives up and does not move).
 */
export function fitPadding(map: Box, overlays: readonly Box[]): Padding {
  const width = Math.max(0, map.right - map.left)
  const height = Math.max(0, map.bottom - map.top)
  const middle = (map.top + map.bottom) / 2

  let top = 0
  let bottom = 0
  for (const overlay of overlays) {
    if (!overlaps(map, overlay)) continue
    if ((overlay.top + overlay.bottom) / 2 < middle) top = Math.max(top, overlay.bottom - map.top)
    else bottom = Math.max(bottom, map.bottom - overlay.top)
  }
  top += PIN_CARD_HEIGHT + MARGIN
  bottom += MARGIN
  let side = PIN_CARD_HALF_WIDTH

  const maxVertical = height * (1 - MIN_SHARE)
  if (top + bottom > maxVertical) {
    const scale = maxVertical / (top + bottom)
    top *= scale
    bottom *= scale
  }
  side = Math.min(side, (width * (1 - MIN_WIDTH_SHARE)) / 2)

  return { top: Math.round(top), bottom: Math.round(bottom), left: Math.round(side), right: Math.round(side) }
}
