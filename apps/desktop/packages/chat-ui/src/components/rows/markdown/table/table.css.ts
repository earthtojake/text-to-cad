/**
 * table.css.ts — geometry-coupled styles for Table.tsx.
 *
 * CRITICAL: cell padding (6px 10px) + line-height (20px) → TABLE_ROW_H = 32.
 * A parity test in spec.test.ts enforces this invariant.
 * Do NOT move these padding/font values to sprinkles or inline styles.
 */

import { globalStyle, style } from '@vanilla-extract/css';
import { vars } from '@styles/theme.css';

export const pchatTable = style({
  borderCollapse: 'separate',
  borderSpacing: 0,
  // font-size and line-height define TABLE_ROW_H — must stay here.
  fontSize: vars.typeBodyFontSize,
  lineHeight: vars.typeBodyLineHeight,
});

// Cell geometry — padding defines TABLE_ROW_H = 32 (line-height:20 + 6+6 padding).
// Uses globalStyle with the parent class selector to mirror the old
// `.pchat-table th, .pchat-table td` rule without touching Tailwind cascade.
globalStyle(`${pchatTable} th, ${pchatTable} td`, {
  padding: '6px 10px',
  textAlign: 'left',
  // max-width:0 activates text-overflow:ellipsis inside fixed-layout tables
  maxWidth: 0,
});

globalStyle(`${pchatTable} th`, {
  fontWeight: 600,
  // background — applied in Table.tsx via Tailwind / sprinkles
});
