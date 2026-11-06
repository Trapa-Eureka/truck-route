import { useEffect, useRef } from 'react'
import { checkpointTitle, formatShortTime, loadRuleNote, weatherRows } from '../lib/checkpoint'
import { RISK_COLORS, RISK_LABELS } from '../lib/risk'
import { GLYPH_LABELS, weatherGlyph } from '../lib/weatherIcon'
import type { RiskLevel, Route } from '../types/api'
import WeatherGlyph from './WeatherGlyph'

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
      <h2 id="timeline-title">
        Route {route.id} checkpoints <span className="count">{route.checkpoints.length}</span>
      </h2>
      <p className="hint">Estimated arrival times in your time zone ({TIME_ZONE}).</p>
      <ol>
        {route.checkpoints.map((checkpoint, position) => {
          const note = loadRuleNote(checkpoint)
          const active = checkpoint.index === activeIndex
          const glyph = weatherGlyph(checkpoint)
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
                <span
                  className="timeline-badge"
                  style={{ borderColor: RISK_COLORS[checkpoint.level] }}
                  title={GLYPH_LABELS[glyph]}
                >
                  <WeatherGlyph glyph={glyph} size={22} />
                </span>
                <span className="timeline-main">
                  <span className="timeline-title">{checkpointTitle(checkpoint, position === last)}</span>
                  <span className={isSerious(checkpoint.level) ? 'timeline-level serious' : 'timeline-level'}>
                    {RISK_LABELS[checkpoint.level]}
                  </span>
                  <span className="timeline-time">{formatShortTime(checkpoint.eta)}</span>
                </span>
                <span className="timeline-weather">
                  {weatherRows(checkpoint).map((row) => (
                    <span
                      className="wx"
                      key={row.label}
                      data-alert={row.level === 'low' ? 'false' : 'true'}
                      style={{ '--tone': RISK_COLORS[row.level] } as React.CSSProperties}
                      title={`${row.label}: ${RISK_LABELS[row.level]}`}
                    >
                      <WeatherGlyph glyph={row.icon} size={15} />
                      {row.value}
                    </span>
                  ))}
                </span>
                {note && <span className="timeline-note">{note}</span>}
              </button>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
