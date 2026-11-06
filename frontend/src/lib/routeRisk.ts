// A route's weather risk in one look: how many miles are at each level. The four numbers on a
// route card say how bad the worst parts are; for a calm route they are all zero, so this says
// where the miles are instead ("All Low"), and draws them as a bar.

import type { RiskLevel } from '../types/api'
import { RISK_LABELS, RISK_LEVELS } from './risk'

export interface RiskShare {
  level: RiskLevel
  miles: number
}

/** The levels that have miles, lowest to highest. */
export function riskShares(milesByLevel: Record<RiskLevel, number>): RiskShare[] {
  return RISK_LEVELS.filter((level) => milesByLevel[level] > 0).map((level) => ({ level, miles: milesByLevel[level] }))
}

/**
 * Whole miles per level that add up to the route's whole miles. Rounding each level on its own
 * can be off by a mile or two in total ("113 + 14" next to a 126 mile route), so the total is
 * rounded first and the levels share it, the largest fractions rounding up. A level with miles
 * always keeps at least "<1" (shown for 0 here).
 */
export function wholeMiles(shares: readonly RiskShare[]): number[] {
  const total = Math.round(shares.reduce((sum, share) => sum + share.miles, 0))
  const whole = shares.map((share) => Math.floor(share.miles))
  let left = total - whole.reduce((sum, miles) => sum + miles, 0)
  const byFraction = shares
    .map((share, index) => ({ index, fraction: share.miles - Math.floor(share.miles) }))
    .sort((a, b) => b.fraction - a.fraction)
  for (const { index } of byFraction) {
    if (left <= 0) break
    whole[index] += 1
    left -= 1
  }
  return whole
}

/** "All Low along the route" or "Low 980 mi · Moderate 26 mi"; a level under a mile is "<1 mi". */
export function riskNote(milesByLevel: Record<RiskLevel, number>): string {
  const shares = riskShares(milesByLevel)
  if (shares.length === 1 && shares[0].level === 'low') return 'All Low along the route'
  const miles = wholeMiles(shares)
  return shares.map((share, i) => `${RISK_LABELS[share.level]} ${miles[i] === 0 ? '<1' : miles[i]} mi`).join(' · ')
}
