/**
 * Tells a map that cannot be used from the many small errors a map reports. MapLibre fires an
 * 'error' event for every failed tile or sprite, and an empty ocean tile or a cancelled request is
 * normal. A reason to show a message: the style could not be loaded at all (wrong URL, no
 * network), or the server refuses the key (401/403), which is what an expired key or a site that is
 * not on the key's list looks like.
 */
export function mapErrorMessage(error: unknown, styleLoaded: boolean): string | null {
  const status = (error as { status?: unknown } | null | undefined)?.status
  const refused = status === 401 || status === 403
  if (!styleLoaded || refused) return refused ? MAP_REFUSED : MAP_NOT_LOADED
  return null
}

export const MAP_REFUSED = 'The map was refused: its key may be missing, expired, or not allowed for this site.'
export const MAP_NOT_LOADED = 'The map could not be loaded. Check your connection and reload the page.'

/**
 * The message to keep once the map has finished loading. "Could not be loaded" was about a slow
 * or failed first request that has since worked, so it goes; a refused key stays refused.
 */
export function messageAfterLoad(current: string | null): string | null {
  return current === MAP_REFUSED ? current : null
}
