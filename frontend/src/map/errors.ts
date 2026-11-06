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
  if (!styleLoaded || refused) {
    return refused
      ? 'The map was refused: its key may be missing, expired, or not allowed for this site.'
      : 'The map could not be loaded. Check your connection and reload the page.'
  }
  return null
}
