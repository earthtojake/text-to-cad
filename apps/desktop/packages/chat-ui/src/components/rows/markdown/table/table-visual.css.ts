/**
 * table-visual.css.ts — visual styles for Table.tsx cells.
 *
 * Geometry rules (font-size, line-height, cell padding) stay in table.css.ts.
 * This file covers overflow/truncation, border, and background decoration.
 */

import { style } from '@vanilla-extract/css';
import { vars } from '@styles/theme.css';

/** Scroll wrapper around the table. */
export const tableScroll = style({
  border: `1px solid ${vars.border}`,
  borderRadius: vars.radiusLg,
  width: '100%',
  height: '100%',
  overflowX: 'auto',
  boxSizing: 'border-box',
});

/** Applied to <th> cells for visual decoration. */
export const thCell = style({
  background: vars.tableHeaderBg,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  borderRight: `1px solid ${vars.border}`,
  borderBottom: `1px solid ${vars.border}`,
  selectors: {
    '&:last-child': { borderRight: 'none' },
  },
});

/** Applied to <td> cells for visual decoration. */
export const tdCell = style({
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  borderRight: `1px solid ${vars.border}`,
  borderBottom: `1px solid ${vars.border}`,
  selectors: {
    '&:last-child': { borderRight: 'none' },
  },
});

/** Remove bottom border from the last row's td cells. */
export const tdCellLastRow = style({
  borderBottom: 'none',
});
