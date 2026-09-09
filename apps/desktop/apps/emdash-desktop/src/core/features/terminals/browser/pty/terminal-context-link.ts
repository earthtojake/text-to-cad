import type { ILink, Terminal } from '@xterm/xterm';
import { getCellMetrics } from '@core/features/terminals/api/browser/pty/xterm-cell-metrics';
import { findFileLinks, type BufferLike } from './file-link-detection';

const URL_PATTERN = /https?:\/\/[^\s"'<>`]+/gi;

type CellLike = {
  getChars(): string;
  getWidth(): number;
};

type BufferLineWithCells = {
  length: number;
  getCell(index: number): CellLike | undefined;
};

type BufferLineWithOptionalCells = NonNullable<ReturnType<BufferLike['getLine']>> &
  BufferLineWithCells;

type LineTextWithColumns = {
  text: string;
  columnForOffset(offset: number): number;
};

export function getTerminalContextLink(terminal: Terminal, event: MouseEvent): string | null {
  const cell = getCellMetrics(terminal);
  const element = (terminal as unknown as { element?: HTMLElement }).element;
  if (!cell || !element) return null;

  const rect = element.getBoundingClientRect();
  const row = Math.floor((event.clientY - rect.top) / cell.height);
  const column = Math.floor((event.clientX - rect.left) / cell.width) + 1;
  if (row < 0 || row >= terminal.rows || column < 1 || column > terminal.cols) return null;

  return getTerminalLinkAtBufferCell(
    terminal.buffer.active,
    terminal.buffer.active.viewportY + row + 1,
    column
  );
}

export function getTerminalLinkAtBufferCell(
  buffer: BufferLike,
  bufferLineNumber: number,
  column: number
): string | null {
  const fileLink = findFileLinks(buffer, bufferLineNumber).find((link) =>
    rangeContainsColumn(link.range, bufferLineNumber, column)
  );
  if (fileLink) return fileLink.text;

  const lineWithColumns = getLineTextWithColumns(buffer.getLine(bufferLineNumber - 1));
  if (!lineWithColumns.text) return null;
  for (const match of lineWithColumns.text.matchAll(URL_PATTERN)) {
    const text = trimLinkText(match[0]);
    const startOffset = match.index ?? 0;
    const endOffset = startOffset + text.length - 1;
    const start = lineWithColumns.columnForOffset(startOffset);
    const end = lineWithColumns.columnForOffset(endOffset);
    if (column >= start && column <= end) return text;
  }
  return null;
}

function getLineTextWithColumns(line: ReturnType<BufferLike['getLine']>): LineTextWithColumns {
  const fallbackText = line?.translateToString(true) ?? '';
  if (!line || !hasCellAccess(line)) {
    return {
      text: fallbackText,
      columnForOffset: (offset) => offset + 1,
    };
  }

  let text = '';
  const offsetColumns: number[] = [];
  for (let cellIndex = 0; cellIndex < line.length; cellIndex += 1) {
    const cell = line.getCell(cellIndex);
    if (!cell || cell.getWidth() === 0) continue;

    const chars = cell.getChars() || ' ';
    const column = cellIndex + 1;
    for (let offset = 0; offset < chars.length; offset += 1) {
      offsetColumns.push(column);
    }
    text += chars;
  }

  const trimLength = text.length - text.trimEnd().length;
  if (trimLength > 0) {
    text = text.slice(0, -trimLength);
    offsetColumns.splice(-trimLength);
  }

  return {
    text,
    columnForOffset: (offset) => offsetColumns[offset] ?? offset + 1,
  };
}

function hasCellAccess(
  line: ReturnType<BufferLike['getLine']>
): line is BufferLineWithOptionalCells {
  return (
    !!line &&
    'length' in line &&
    'getCell' in line &&
    typeof line.length === 'number' &&
    typeof line.getCell === 'function'
  );
}

function rangeContainsColumn(
  range: ILink['range'],
  bufferLineNumber: number,
  column: number
): boolean {
  if (bufferLineNumber < range.start.y || bufferLineNumber > range.end.y) return false;
  const startColumn = bufferLineNumber === range.start.y ? range.start.x : 1;
  const endColumn = bufferLineNumber === range.end.y ? range.end.x : Number.POSITIVE_INFINITY;
  return column >= startColumn && column <= endColumn;
}

function trimLinkText(text: string): string {
  return text.replace(/[),.;:!?]+$/, '');
}
