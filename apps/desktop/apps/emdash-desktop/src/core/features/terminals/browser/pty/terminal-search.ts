export interface TerminalSearchBufferLineLike {
  isWrapped?: boolean;
  translateToString(trimRight?: boolean, startColumn?: number, endColumn?: number): string;
}

export interface TerminalSearchBufferLike {
  length: number;
  getLine(index: number): TerminalSearchBufferLineLike | undefined;
}

export interface TerminalSearchMatch {
  row: number;
  col: number;
  length: number;
}

interface PhysicalLineSegment {
  row: number;
  startIndex: number;
}

interface LogicalLine {
  text: string;
  segments: PhysicalLineSegment[];
}

function buildLogicalLines(buffer: TerminalSearchBufferLike): LogicalLine[] {
  const logicalLines: LogicalLine[] = [];
  let current: LogicalLine | null = null;

  for (let index = 0; index < buffer.length; index += 1) {
    const line = buffer.getLine(index);
    if (!line) continue;

    const text = line.translateToString(false);
    if (!current || !line.isWrapped) {
      if (current) logicalLines.push(current);
      current = { text: '', segments: [] };
    }

    current.segments.push({
      row: index,
      startIndex: current.text.length,
    });
    current.text += text;
  }

  if (current) logicalLines.push(current);

  return logicalLines;
}

function resolveMatchStart(
  segments: PhysicalLineSegment[],
  startIndex: number
): TerminalSearchMatch {
  for (let index = segments.length - 1; index >= 0; index -= 1) {
    const segment = segments[index];
    if (startIndex >= segment.startIndex) {
      return {
        row: segment.row,
        col: startIndex - segment.startIndex,
        length: 0,
      };
    }
  }

  const firstSegment = segments[0];
  return {
    row: firstSegment?.row ?? 0,
    col: 0,
    length: 0,
  };
}

export function collectTerminalSearchMatches(
  buffer: TerminalSearchBufferLike,
  query: string
): TerminalSearchMatch[] {
  if (!query) return [];

  const normalizedQuery = query.toLocaleLowerCase();
  if (!normalizedQuery) return [];

  const matches: TerminalSearchMatch[] = [];
  const logicalLines = buildLogicalLines(buffer);

  for (const logicalLine of logicalLines) {
    const haystack = logicalLine.text.toLocaleLowerCase();
    let fromIndex = 0;

    while (fromIndex <= haystack.length - normalizedQuery.length) {
      const matchIndex = haystack.indexOf(normalizedQuery, fromIndex);
      if (matchIndex === -1) break;

      const start = resolveMatchStart(logicalLine.segments, matchIndex);
      matches.push({
        row: start.row,
        col: start.col,
        length: query.length,
      });

      fromIndex = matchIndex + Math.max(1, normalizedQuery.length);
    }
  }

  return matches;
}

function compareMatchPosition(left: TerminalSearchMatch, right: TerminalSearchMatch): number {
  if (left.row !== right.row) return left.row - right.row;
  if (left.col !== right.col) return left.col - right.col;
  return left.length - right.length;
}

function findExactCurrentMatchIndex(
  matches: TerminalSearchMatch[],
  currentMatch: TerminalSearchMatch | null
): number {
  if (!currentMatch) return -1;

  return matches.findIndex(
    (candidate) =>
      candidate.row === currentMatch.row &&
      candidate.col === currentMatch.col &&
      candidate.length === currentMatch.length
  );
}

export function getNextTerminalSearchIndex(
  matches: TerminalSearchMatch[],
  currentMatch: TerminalSearchMatch | null,
  direction: 'next' | 'prev'
): number {
  if (matches.length === 0) return -1;

  const currentMatchIndex = findExactCurrentMatchIndex(matches, currentMatch);
  if (currentMatchIndex === -1 && currentMatch) {
    if (direction === 'prev') {
      for (let index = matches.length - 1; index >= 0; index -= 1) {
        if (compareMatchPosition(matches[index], currentMatch) < 0) {
          return index;
        }
      }
      return matches.length - 1;
    }

    const nextIndex = matches.findIndex(
      (candidate) => compareMatchPosition(candidate, currentMatch) > 0
    );
    return nextIndex === -1 ? 0 : nextIndex;
  }

  if (currentMatchIndex === -1) {
    return direction === 'prev' ? matches.length - 1 : 0;
  }

  if (direction === 'prev') {
    return currentMatchIndex === 0 ? matches.length - 1 : currentMatchIndex - 1;
  }

  return currentMatchIndex === matches.length - 1 ? 0 : currentMatchIndex + 1;
}
