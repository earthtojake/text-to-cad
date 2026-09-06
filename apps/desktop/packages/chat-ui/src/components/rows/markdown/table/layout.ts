/**
 * layoutTable — pure geometry for a TableBlock.
 *
 * Column widths are distributed equally across the available contentWidth,
 * but each column is floored at TABLE_MIN_COL_W. When the floor kicks in the
 * tableWidth exceeds contentWidth — the wrapper handles horizontal scroll.
 *
 * Height is fully deterministic: every row (header + data) is exactly
 * TABLE_ROW_H tall because cells are single-line truncated.
 */

import type { TableLaidOut } from '@core/layout/layout-types';
import { reserveHeight } from '@core/layout/reserve-height';
import type { TableBlock } from '@core/markdown/document';
import { DEFAULT_FONT_CONFIG } from '@core/measure/fonts';

const TABLE_ROW_H = DEFAULT_FONT_CONFIG.body.lineHeight + 12;
const TABLE_BORDER = 1;
const TABLE_MIN_COL_W = 80;

export function layoutTable(
  block: TableBlock,
  blockTop: number,
  contentWidth: number
): TableLaidOut {
  const colCount = Math.max(1, block.header.length);
  // The visible table sits inside a 1px-bordered wrapper, so the usable inner
  // width is contentWidth minus the left+right border. Distributing columns over
  // the full contentWidth would make the table 2px wider than its container and
  // trigger a spurious horizontal scrollbar.
  const available = contentWidth - 2 * TABLE_BORDER;
  const target = Math.floor(available / colCount);
  const colW = Math.max(TABLE_MIN_COL_W, target);
  const colWidths = Array<number>(colCount).fill(colW);
  const tableWidth = colW * colCount;
  // +1 for the header row; border-collapse draws rowCount+1 horizontal grid lines
  const rowCount = block.rows.length + 1;
  const height = reserveHeight({
    content: rowCount * TABLE_ROW_H,
    border: TABLE_BORDER,
    borderLines: rowCount + 1,
  });

  return {
    kind: 'table',
    id: block.id,
    top: blockTop,
    height,
    contentWidth: tableWidth,
    colWidths,
    tableWidth,
    header: block.header,
    rows: block.rows,
  };
}
