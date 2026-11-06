import { describe, expect, it } from 'vitest'
import { DRAW_COLOR, drawGradient } from './reveal'

describe('drawGradient', () => {
  const clear = 'rgba(26, 37, 48, 0)'

  it('reads the position along the line', () => {
    expect((drawGradient(0.5) as unknown[]).slice(0, 2)).toEqual(['step', ['line-progress']])
  })

  it('draws the color up to the progress and nothing after it', () => {
    expect(drawGradient(0.4)).toEqual(['step', ['line-progress'], DRAW_COLOR, 0.4, clear])
    expect(drawGradient(0.9)).toEqual(['step', ['line-progress'], DRAW_COLOR, 0.9, clear])
  })

  it('draws nothing at the start', () => {
    expect(drawGradient(0)).toEqual(['step', ['line-progress'], clear, 1.01, clear])
    expect(drawGradient(-1)).toEqual(['step', ['line-progress'], clear, 1.01, clear])
    expect(drawGradient(Number.NaN)).toEqual(['step', ['line-progress'], clear, 1.01, clear])
  })

  it('draws the whole line at the end, including its last point', () => {
    expect(drawGradient(1)).toEqual(['step', ['line-progress'], DRAW_COLOR, 1.01, clear])
    expect(drawGradient(3)).toEqual(['step', ['line-progress'], DRAW_COLOR, 1.01, clear])
  })

  it('keeps the stops in ascending order, as a step expression needs', () => {
    for (const progress of [0, 0.001, 0.25, 0.5, 0.999, 1, 2]) {
      const stops = (drawGradient(progress) as unknown[]).filter((_, i) => i >= 3 && i % 2 === 1) as number[]
      expect([...stops].sort((a, b) => a - b)).toEqual(stops)
    }
  })
})
