import { describe, expect, it } from 'vitest'
import { nextShown, PAGE_SIZE, pageStatus, shownToReach } from './pagination'

describe('nextShown', () => {
  it('adds one page', () => {
    expect(PAGE_SIZE).toBe(10)
    expect(nextShown(10, 104)).toBe(20)
    expect(nextShown(20, 104)).toBe(30)
  })

  it('never goes past the total', () => {
    expect(nextShown(100, 104)).toBe(104)
    expect(nextShown(104, 104)).toBe(104)
    expect(nextShown(10, 14)).toBe(14)
  })
})

describe('shownToReach', () => {
  it('keeps what is shown when the row is already among it', () => {
    expect(shownToReach(30, 0, 104)).toBe(30)
    expect(shownToReach(30, 29, 104)).toBe(30)
  })

  it('opens whole pages up to a row that is further down', () => {
    expect(shownToReach(10, 10, 104)).toBe(20) // the 11th row needs the 2nd page
    expect(shownToReach(10, 19, 104)).toBe(20)
    expect(shownToReach(10, 20, 104)).toBe(30)
    expect(shownToReach(10, 57, 104)).toBe(60)
  })

  it('stops at the total, also for the last, short page', () => {
    expect(shownToReach(10, 103, 104)).toBe(104)
    expect(shownToReach(10, 101, 104)).toBe(104)
  })

  it('never shows fewer than before', () => {
    expect(shownToReach(60, 12, 104)).toBe(60)
  })
})

describe('pageStatus', () => {
  it('says how many of how many', () => {
    expect(pageStatus(20, 104)).toBe('Showing 20 of 104 checkpoints')
    expect(pageStatus(104, 104)).toBe('Showing 104 of 104 checkpoints')
  })
})
