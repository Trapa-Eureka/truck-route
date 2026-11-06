// How much of the checkpoint list is shown. A route can have a thousand checkpoints; the list
// starts with the first page and grows by one page at a time.

export const PAGE_SIZE = 10

/** How many rows are shown after "Load more". */
export const nextShown = (shown: number, total: number) => Math.min(total, shown + PAGE_SIZE)

/**
 * How many rows must be shown for the row at `position` (0-based) to be among them: the rows
 * already shown, or whole pages up to it. A checkpoint chosen on the map may lie further down.
 */
export function shownToReach(shown: number, position: number, total: number): number {
  if (position < shown) return shown
  return Math.min(total, Math.ceil((position + 1) / PAGE_SIZE) * PAGE_SIZE)
}

/** "Showing 20 of 104 checkpoints". */
export const pageStatus = (shown: number, total: number) => `Showing ${shown} of ${total} checkpoints`
