// The animation that shows a route: a dark line is drawn from the origin to the destination, then
// the risk colors, the white outline, the checkpoint dots and the weather markers fade in, and the
// other routes appear.
//
// How the drawing works. This version of MapLibre has no "trim" for lines, so the drawn line uses a
// `line-gradient`: a color for the part of the line before `progress` and a transparent one after
// it. Moving `progress` from 0 to 1 draws the line. The gradient's color ramp is only 256 steps
// wide, which is fine for a single cut but too coarse for the risk colors (a 3,000 mile route would
// move a color boundary by up to 12 miles), so the real colors are never taken from it: they come
// from the exact segments, which fade in as the dark line finishes.

import gsap from 'gsap'
import type { Map as MapLibreMap } from 'maplibre-gl'
import { FADE_MS, LAYER } from './ids'

export const DRAW_COLOR = '#1a2530'
/** The white outline under the route is slightly see-through. */
export const OUTLINE_OPACITY = 0.9
/** The routes that are not selected keep their risk colors but are paler (and thinner). */
export const OTHER_OPACITY = 0.6
export const OTHER_OUTLINE_OPACITY = 0.75
export const OTHER_DOT_OPACITY = 0.8
const CLEAR = 'rgba(26, 37, 48, 0)'

/**
 * `line-gradient` expression: the draw color up to `progress` (0 to 1) of the way along the line,
 * transparent after it.
 */
export function drawGradient(progress: number): unknown[] {
  if (!(progress > 0)) return ['step', ['line-progress'], CLEAR, 1.01, CLEAR]
  if (progress >= 1) return ['step', ['line-progress'], DRAW_COLOR, 1.01, CLEAR]
  return ['step', ['line-progress'], DRAW_COLOR, progress, CLEAR]
}

export const prefersReducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

export interface Reveal {
  /** Hides the route and draws it again over `duration` seconds, after `delay` seconds. */
  play(options: { duration: number; delay?: number }): void
  /** Shows everything at once, as at the end of the animation. */
  showAll(): void
  stop(): void
}

export function createReveal(map: MapLibreMap): Reveal {
  let timeline: gsap.core.Timeline | null = null

  // Each fade is a map "transition". Its duration must be set before the value changes: 0 hides at
  // once, FADE_MS fades.
  // The property names here are built at run time, so the map's typed signature is widened.
  const paint = map as unknown as { setPaintProperty(layer: string, property: string, value: unknown): void }
  const set = (layer: string, property: string, value: number, ms: number) => {
    if (!map.getLayer(layer)) return
    paint.setPaintProperty(layer, `${property}-transition`, { duration: ms, delay: 0 })
    paint.setPaintProperty(layer, property, value)
  }
  const setProgress = (progress: number) => {
    if (map.getLayer(LAYER.routeDraw)) paint.setPaintProperty(LAYER.routeDraw, 'line-gradient', drawGradient(progress))
  }
  const stop = () => {
    timeline?.kill()
    timeline = null
  }

  // The layers of the selected route (without the dark line) and of the other routes, with the
  // opacity each one has when it is showing.
  const selectedLayers: [string, string, number][] = [
    [LAYER.routeCasing, 'line-opacity', OUTLINE_OPACITY],
    [LAYER.riskLine, 'line-opacity', 1],
    [LAYER.checkpointDots, 'circle-opacity', 1],
    [LAYER.checkpointDots, 'circle-stroke-opacity', 1],
  ]
  const otherLayers: [string, string, number][] = [
    [LAYER.otherCasing, 'line-opacity', OTHER_OUTLINE_OPACITY],
    [LAYER.riskOther, 'line-opacity', OTHER_OPACITY],
    [LAYER.otherDots, 'circle-opacity', OTHER_DOT_OPACITY],
    [LAYER.otherDots, 'circle-stroke-opacity', OTHER_DOT_OPACITY],
  ]
  const show = (layers: [string, string, number][], ms: number) => {
    for (const [layer, property, opacity] of layers) set(layer, property, opacity, ms)
  }
  const hide = (layers: [string, string, number][]) => {
    for (const [layer, property] of layers) set(layer, property, 0, 0)
  }

  return {
    stop,
    showAll() {
      stop()
      show(selectedLayers, 0)
      show(otherLayers, 0)
      set(LAYER.routeDraw, 'line-opacity', 0, 0)
      set(LAYER.checkpoints, 'icon-opacity', 1, 0)
    },
    play({ duration, delay = 0 }) {
      stop()
      // Hide at once, before the delay, so the new route never shows in full first.
      hide(selectedLayers)
      hide(otherLayers)
      set(LAYER.checkpoints, 'icon-opacity', 0, 0)
      set(LAYER.routeDraw, 'line-opacity', 1, 0)
      setProgress(0)

      const state = { progress: 0 }
      timeline = gsap
        .timeline({ delay })
        .call(() => show(otherLayers, FADE_MS))
        .to(state, { progress: 1, duration, ease: 'power2.inOut', onUpdate: () => setProgress(state.progress) })
        .call(
          () => {
            // The dark line has reached the destination: swap it for the real colors.
            show(selectedLayers, FADE_MS)
            set(LAYER.routeDraw, 'line-opacity', 0, FADE_MS)
          },
          [],
          '-=0.05',
        )
        .call(() => set(LAYER.checkpoints, 'icon-opacity', 1, FADE_MS), [], '+=0.15')
    },
  }
}
