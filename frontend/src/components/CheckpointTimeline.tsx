import { useEffect, useRef } from 'react'
import { checkpointTitle, formatShortTime, loadRuleNote, weatherLine } from '../lib/checkpoint'
import { RISK_COLORS, RISK_LABELS } from '../lib/risk'
import type { RiskLevel, Route } from '../types/api'

const TIME_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone

const isSerious = (level: RiskLevel) => level === 'severe' || level === 'no_travel'

interface Props {
  route: Route
  activeIndex: number | null
  onSelect: (index: number) => void
}

/** The selected route's checkpoints in driving order: when, how bad, and why. */
export default function CheckpointTimeline({ route, activeIndex, onSelect }: Props) {
  const items = useRef(new Map<number, HTMLButtonElement>())

  // When a checkpoint is chosen on the map, bring it into view in the list.
  useEffect(() => {
    if (activeIndex !== null) items.current.get(activeIndex)?.scrollIntoView({ block: 'nearest' })
  }, [activeIndex])

  const last = route.checkpoints.length - 1
  return (
    <section className="timeline" aria-labelledby="timeline-title">
      <h2 id="timeline-title">Route {route.id} checkpoints</h2>
      <p className="hint">Estimated arrival times in your time zone ({TIME_ZONE}).</p>
      <ol>
        {route.checkpoints.map((checkpoint, position) => {
          const note = loadRuleNote(checkpoint)
          const active = checkpoint.index === activeIndex
          return (
            <li key={checkpoint.index}>
              <button
                type="button"
                className={active ? 'timeline-item active' : 'timeline-item'}
                aria-current={active || undefined}
                onClick={() => onSelect(checkpoint.index)}
                ref={(node) => {
                  if (node) items.current.set(checkpoint.index, node)
                  else items.current.delete(checkpoint.index)
                }}
              >
                <span className="timeline-dot" style={{ background: RISK_COLORS[checkpoint.level] }} />
                <span className="timeline-main">
                  <span className="timeline-title">{checkpointTitle(checkpoint, position === last)}</span>
                  <span className={isSerious(checkpoint.level) ? 'timeline-level serious' : 'timeline-level'}>
                    {RISK_LABELS[checkpoint.level]}
                  </span>
                  <span className="timeline-time">{formatShortTime(checkpoint.eta)}</span>
                </span>
                <span className="timeline-weather">{weatherLine(checkpoint)}</span>
                {note && <span className="timeline-note">{note}</span>}
              </button>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
