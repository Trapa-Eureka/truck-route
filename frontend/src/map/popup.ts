import { loadRuleNote, checkpointTitle, weatherRows } from '../lib/checkpoint'
import { formatDateTime } from '../lib/format'
import { RISK_COLORS, RISK_LABELS } from '../lib/risk'
import type { Checkpoint, RiskLevel } from '../types/api'

function element<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string, text?: string) {
  const node = document.createElement(tag)
  if (className) node.className = className
  if (text !== undefined) node.textContent = text // textContent only: nothing here is parsed as HTML
  return node
}

function levelTag(level: RiskLevel): HTMLElement {
  const tag = element('span', 'cp-level')
  const swatch = element('span', 'swatch')
  swatch.style.background = RISK_COLORS[level]
  tag.append(swatch, RISK_LABELS[level])
  return tag
}

/** The popup for one checkpoint: when the truck gets there, the weather then, and the level. */
export function checkpointPopupContent(checkpoint: Checkpoint, isLast: boolean): HTMLElement {
  const root = element('div', 'cp-popup')

  const head = element('div', 'cp-head')
  head.append(element('strong', 'cp-title', checkpointTitle(checkpoint, isLast)), levelTag(checkpoint.level))
  root.append(head, element('p', 'cp-time', `Arrives ${formatDateTime(checkpoint.eta)}`))

  const rows = element('ul', 'cp-rows')
  for (const row of weatherRows(checkpoint)) {
    const item = element('li')
    item.append(element('span', 'cp-row-label', row.label), element('span', 'cp-row-value', row.value), levelTag(row.level))
    rows.append(item)
  }
  root.append(rows)

  const note = loadRuleNote(checkpoint)
  if (note) root.append(element('p', 'cp-note', `${RISK_LABELS[checkpoint.level]} because of the load: ${note}.`))
  return root
}
