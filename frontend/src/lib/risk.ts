// The five risk levels: their order, names and colors. One source for the map line, the
// checkpoint dots, the legend and (Step 10) the heatmap, so they always agree.

import type { RiskLevel } from '../types/api'

/** Lowest to highest, as in the PDF. A level's index is its heatmap integer (0 to 4). */
export const RISK_LEVELS: readonly RiskLevel[] = ['low', 'moderate', 'high', 'severe', 'no_travel']

/** The PDF's own terms, used exactly. */
export const RISK_LABELS: Record<RiskLevel, string> = {
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  severe: 'Severe',
  no_travel: 'No Travel',
}

// Green to yellow to orange to red to dark purple. The steps differ in lightness as well as hue
// (yellow is light, purple is dark), so they stay apart for people who cannot tell red from green,
// and the level name always sits next to the color.
export const RISK_COLORS: Record<RiskLevel, string> = {
  low: '#2e9e5f',
  moderate: '#f2c230',
  high: '#f28c28',
  severe: '#d63a2f',
  no_travel: '#4b1d5c',
}

/** Routes that are not selected. */
export const OTHER_ROUTE_COLOR = '#8a949e'
