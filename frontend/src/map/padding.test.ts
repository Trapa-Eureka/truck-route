import { describe, expect, it } from 'vitest'
import { fitPadding, MARGIN, MIN_SHARE, MIN_WIDTH_SHARE, PIN_CARD_HALF_WIDTH, PIN_CARD_HEIGHT, type Box } from './padding'

const box = (left: number, top: number, width: number, height: number): Box => ({ left, top, right: left + width, bottom: top + height })

// A map of 946 x 768 that starts 420 px from the left (the panel), as on a 1366 x 768 laptop.
const map = box(420, 0, 946, 768)
const tripBar = box(736, 16, 558, 56) // top right
const legend = box(436, 580, 150, 162) // bottom left
const forecast = box(660, 566, 466, 176) // bottom middle

describe('fitPadding', () => {
  it('with no overlays leaves room for the label cards only', () => {
    expect(fitPadding(map, [])).toEqual({
      top: PIN_CARD_HEIGHT + MARGIN,
      bottom: MARGIN,
      left: PIN_CARD_HALF_WIDTH,
      right: PIN_CARD_HALF_WIDTH,
    })
  })

  it('keeps the top clear of an overlay in the upper half, plus the label card', () => {
    expect(fitPadding(map, [tripBar]).top).toBe(72 + PIN_CARD_HEIGHT + MARGIN)
    expect(fitPadding(map, [tripBar]).bottom).toBe(MARGIN)
  })

  it('keeps the bottom clear of the overlays in the lower half: the tallest counts', () => {
    const padding = fitPadding(map, [legend, forecast])
    expect(padding.bottom).toBe(768 - 566 + MARGIN) // the forecast card starts higher than the legend
    expect(padding.top).toBe(PIN_CARD_HEIGHT + MARGIN)
  })

  it('does not depend on the order of the overlays', () => {
    expect(fitPadding(map, [forecast, legend, tripBar])).toEqual(fitPadding(map, [tripBar, legend, forecast]))
    const low = box(500, 700, 100, 40)
    expect(fitPadding(map, [forecast, low]).bottom).toBe(768 - 566 + MARGIN)
    const small = box(500, 10, 100, 20)
    expect(fitPadding(map, [tripBar, small]).top).toBe(72 + PIN_CARD_HEIGHT + MARGIN)
  })

  it('handles the real layout: trip bar on top, legend and slider at the bottom', () => {
    expect(fitPadding(map, [tripBar, legend, forecast])).toEqual({ top: 168, bottom: 222, left: 140, right: 140 })
  })

  it('measures from the map, not from the window', () => {
    const lower = box(420, 100, 946, 768)
    const bar = box(736, 116, 558, 56)
    expect(fitPadding(lower, [bar]).top).toBe(72 + PIN_CARD_HEIGHT + MARGIN)
  })

  it('ignores an overlay that is not over the map (under it on a small screen)', () => {
    const phoneMap = box(0, 0, 390, 388)
    const under = box(12, 398, 366, 150)
    const beside = box(-300, 10, 200, 50)
    expect(fitPadding(phoneMap, [under, beside])).toEqual(fitPadding(phoneMap, []))
  })

  it('counts an overlay that only touches the edge of the map as not over it', () => {
    const below = box(420, 768, 946, 50)
    expect(fitPadding(map, [below])).toEqual(fitPadding(map, []))
  })

  it('cuts the padding back on a short map, so the routes keep their share of it', () => {
    const short = box(0, 0, 900, 400)
    const padding = fitPadding(short, [box(300, 10, 500, 100), box(100, 250, 700, 140)])
    // wanted: top 110 + 96 = 206, bottom 150 + 20 = 170, together 376 of 400
    expect(padding.top + padding.bottom).toBeLessThanOrEqual(Math.ceil(400 * (1 - MIN_SHARE)) + 1)
    expect(padding.top / padding.bottom).toBeCloseTo(206 / 170, 1)
    expect(400 - padding.top - padding.bottom).toBeGreaterThanOrEqual(400 * MIN_SHARE - 1)
  })

  it('narrows the sides on a narrow map', () => {
    const narrow = box(0, 0, 390, 388)
    const padding = fitPadding(narrow, [])
    expect(padding.left).toBe(padding.right)
    expect(padding.left).toBe(Math.round((390 * (1 - MIN_WIDTH_SHARE)) / 2))
    expect(390 - padding.left - padding.right).toBeGreaterThanOrEqual(390 * MIN_WIDTH_SHARE - 1)
  })

  it('does not change the sides of a wide map', () => {
    expect(fitPadding(map, [tripBar]).left).toBe(PIN_CARD_HALF_WIDTH)
  })

  it('always gives whole, non-negative pixels', () => {
    for (const m of [map, box(0, 0, 0, 0), box(0, 0, 50, 30), box(0, 0, 390, 388)]) {
      const padding = fitPadding(m, [tripBar, legend, forecast, box(0, 0, 40, 20)])
      for (const value of Object.values(padding)) {
        expect(Number.isInteger(value)).toBe(true)
        expect(value).toBeGreaterThanOrEqual(0)
      }
    }
  })
})
