import { useEffect, useRef, useState } from 'react'
import { checkpointTitle, formatShortTime, loadRuleNote, weatherRows } from '../lib/checkpoint'
import { nextShown, PAGE_SIZE, pageStatus, shownToReach } from '../lib/pagination'
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
  const heading = useRef<HTMLHeadingElement>(null)
  const total = route.checkpoints.length
  const [shown, setShown] = useState(PAGE_SIZE)
  const [seenActive, setSeenActive] = useState<number | null>(null)

  // A checkpoint chosen on the map may lie below the rows shown: open pages down to it. (Done while
  // rendering, when the choice changes, so "back to the first 10" is not undone by it afterwards.)
  if (activeIndex !== seenActive) {
    setSeenActive(activeIndex)
    const position = route.checkpoints.findIndex((checkpoint) => checkpoint.index === activeIndex)
    if (position >= 0) setShown((current) => shownToReach(current, position, total))
  }
  const visible = Math.min(shown, total)

  // When a checkpoint is chosen on the map, bring it into view in the list.
  useEffect(() => {
    if (activeIndex !== null) items.current.get(activeIndex)?.scrollIntoView({ block: 'nearest' })
  }, [activeIndex])

  function backToFirstPage() {
    setShown(PAGE_SIZE)
    heading.current?.scrollIntoView({ block: 'start' }) // the list gets short: do not leave the reader far below it
  }

  const last = total - 1
  return (
    <section className="timeline" aria-labelledby="timeline-title">
      <h2 id="timeline-title" ref={heading}>
        Route {route.id} checkpoints <span className="count">{total}</span>
      </h2>
      <p className="hint">Estimated arrival times in your time zone ({TIME_ZONE}).</p>
      <ol>
        {route.checkpoints.slice(0, visible).map((checkpoint, position) => {
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

      {total > PAGE_SIZE && (
        <div className="timeline-more">
          <p className="timeline-more-status" aria-live="polite">
            {pageStatus(visible, total)}
          </p>
          <div className="timeline-more-buttons">
            {visible < total && (
              <>
                <button type="button" className="more-button primary-soft" onClick={() => setShown(nextShown(visible, total))}>
                  Load more
                </button>
                <button type="button" className="more-button" onClick={() => setShown(total)}>
                  Show all {total}
                </button>
              </>
            )}
            {visible > PAGE_SIZE && (
              <button type="button" className="more-button" onClick={backToFirstPage}>
                Back to first {PAGE_SIZE}
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
