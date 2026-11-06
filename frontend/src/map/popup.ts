import { checkpointTitle, loadRuleNote, weatherRows } from '../lib/checkpoint'
import { formatDateTime } from '../lib/format'
import { iconMarkup, type IconName } from '../lib/icons'
import { glyphMarkup } from '../lib/weatherGlyphs'
import { RISK_COLORS, RISK_LABELS } from '../lib/risk'
import { GLYPH_LABELS, weatherGlyph, type WeatherGlyph } from '../lib/weatherIcon'
import type { Checkpoint, RiskLevel } from '../types/api'

function element<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string, text?: string) {
  const node = document.createElement(tag)
  if (className) node.className = className
  if (text !== undefined) node.textContent = text // textContent only: nothing here is parsed as HTML
  return node
}

/** A span holding an icon. The markup is from the icon package, never from the data. */
function icon(name: IconName, size: number, className?: string): HTMLElement {
  const holder = element('span', className)
  holder.innerHTML = iconMarkup(name, size)
  return holder
}

/** A span holding a weather picture in its own colors. */
function glyph(name: WeatherGlyph, size: number, className?: string): HTMLElement {
  const holder = element('span', className)
  holder.innerHTML = glyphMarkup(name, size)
  return holder
}

function levelPill(level: RiskLevel): HTMLElement {
  const pill = element('span', 'cp-pill')
  const dot = element('span', 'swatch')
  dot.style.background = RISK_COLORS[level]
  pill.append(dot, RISK_LABELS[level])
  return pill
}

/**
 * The popup for one checkpoint: when the truck gets there, the weather then as three picture tiles
 * (wind, rain, snow), each with its own level, and the final level.
 */
export function checkpointPopupContent(checkpoint: Checkpoint, isLast: boolean): HTMLElement {
  const root = element('div', 'cp-popup')

  const shown = weatherGlyph(checkpoint)
  const badge = glyph(shown, 26, 'cp-badge')
  badge.style.borderColor = RISK_COLORS[checkpoint.level] // the ring says how risky it is
  badge.title = GLYPH_LABELS[shown]

  const heading = element('div', 'cp-heading')
  const when = element('span', 'cp-time')
  when.append(icon('clock', 13), formatDateTime(checkpoint.eta))
  heading.append(element('strong', 'cp-title', checkpointTitle(checkpoint, isLast)), when)

  const head = element('div', 'cp-head')
  head.append(badge, heading, levelPill(checkpoint.level))
  root.append(head)

  const tiles = element('div', 'cp-tiles')
  for (const row of weatherRows(checkpoint)) {
    const tile = element('div', 'cp-tile')
    tile.dataset.alert = row.level === 'low' ? 'false' : 'true'
    tile.style.setProperty('--tone', RISK_COLORS[row.level])
    const value = element('span', 'cp-tile-value')
    value.append(element('strong', undefined, row.amount), element('small', undefined, row.unit))
    tile.append(
      glyph(row.icon, 26, 'cp-tile-icon'),
      value,
      element('span', 'cp-tile-label', `${row.label} · ${RISK_LABELS[row.level]}`),
    )
    tiles.append(tile)
  }
  root.append(tiles)

  const note = loadRuleNote(checkpoint)
  if (note) {
    const warning = element('p', 'cp-note')
    warning.append(icon('alert', 15), `${RISK_LABELS[checkpoint.level]} because of the load: ${note}.`)
    root.append(warning)
  }
  return root
}
