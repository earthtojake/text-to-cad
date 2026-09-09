import {
  CONTENT_SEARCH_MAX_LIMIT,
  CONTENT_SEARCH_MAX_PREVIEW_LENGTH,
  type ContentSearchLineMatch,
  type ContentSearchRange,
} from '#runtimes/file-search/api';
import { createContentSearchPreview } from './content-preview';

export type ParsedRipgrepMatch = Readonly<
  ContentSearchLineMatch & {
    path: string;
    locationsOmitted: boolean;
  }
>;

export type ParseRipgrepJsonLineOptions = Readonly<{
  maxLocations?: number;
  maxPreviewLength?: number;
}>;

type ByteRange = Readonly<{
  start: number;
  end: number;
}>;

/** Parses one ripgrep JSON-lines record; non-match records intentionally return null. */
export function parseRipgrepJsonLine(
  line: string,
  options: ParseRipgrepJsonLineOptions = {}
): ParsedRipgrepMatch | null {
  const event = JSON.parse(line) as unknown;
  if (!isRecord(event) || event.type !== 'match') return null;
  if (!isRecord(event.data)) throw new Error('ripgrep match record has no data object');

  const pathText = decodeText(event.data.path, 'path').toString('utf8');
  const lineBytes = stripLineTerminator(decodeText(event.data.lines, 'lines'));
  const lineNumber = event.data.line_number;
  if (!Number.isInteger(lineNumber) || (lineNumber as number) < 1) {
    throw new Error('ripgrep match record has an invalid line number');
  }
  if (!Array.isArray(event.data.submatches) || event.data.submatches.length === 0) {
    throw new Error('ripgrep match record has no submatches');
  }

  const maxLocations = options.maxLocations ?? CONTENT_SEARCH_MAX_LIMIT;
  if (
    !Number.isInteger(maxLocations) ||
    maxLocations < 1 ||
    maxLocations > CONTENT_SEARCH_MAX_LIMIT
  ) {
    throw new RangeError(`maxLocations must be between 1 and ${CONTENT_SEARCH_MAX_LIMIT}`);
  }
  const maxPreviewLength = options.maxPreviewLength ?? CONTENT_SEARCH_MAX_PREVIEW_LENGTH;
  if (
    !Number.isInteger(maxPreviewLength) ||
    maxPreviewLength < 1 ||
    maxPreviewLength > CONTENT_SEARCH_MAX_PREVIEW_LENGTH
  ) {
    throw new RangeError(
      `maxPreviewLength must be between 1 and ${CONTENT_SEARCH_MAX_PREVIEW_LENGTH}`
    );
  }

  let previousEnd = 0;
  const selectedByteRanges: ByteRange[] = [];
  for (const submatch of event.data.submatches) {
    if (!isRecord(submatch)) throw new Error('ripgrep emitted an invalid submatch');
    const start = submatch.start;
    const end = submatch.end;
    if (
      !Number.isInteger(start) ||
      !Number.isInteger(end) ||
      (start as number) < 0 ||
      (end as number) <= (start as number) ||
      (end as number) > lineBytes.length ||
      (start as number) < previousEnd
    ) {
      throw new Error('ripgrep emitted invalid or overlapping submatch byte offsets');
    }
    previousEnd = end as number;
    if (selectedByteRanges.length < maxLocations) {
      selectedByteRanges.push({ start: start as number, end: end as number });
    }
  }

  const ranges = utf16Ranges(lineBytes, selectedByteRanges);
  const preview = createContentSearchPreview(previewText(lineBytes), ranges, {
    maxLength: maxPreviewLength,
  });

  return {
    path: pathText,
    lineNumber: lineNumber as number,
    previewText: preview.previewText,
    locations: preview.locations,
    locationsOmitted:
      preview.locationsOmitted || selectedByteRanges.length < event.data.submatches.length,
  };
}

function decodeText(value: unknown, field: string): Buffer {
  if (!isRecord(value)) throw new Error(`ripgrep ${field} is not a text object`);
  if (typeof value.text === 'string') return Buffer.from(value.text, 'utf8');
  if (typeof value.bytes === 'string') return Buffer.from(value.bytes, 'base64');
  throw new Error(`ripgrep ${field} has neither text nor bytes`);
}

function utf16Ranges(line: Buffer, ranges: readonly ByteRange[]): ContentSearchRange[] {
  let byteCursor = 0;
  let utf16Cursor = 0;

  return ranges.map(({ start, end }) => {
    utf16Cursor += line.subarray(byteCursor, start).toString('utf8').length;
    const startColumn = utf16Cursor + 1;
    utf16Cursor += line.subarray(start, end).toString('utf8').length;
    const endColumn = utf16Cursor + 1;
    byteCursor = end;
    return { startColumn, endColumn };
  });
}

function stripLineTerminator(line: Buffer): Buffer {
  let end = line.length;
  if (end > 0 && line[end - 1] === 0x0a) end -= 1;
  if (end > 0 && line[end - 1] === 0x0d) end -= 1;
  return line.subarray(0, end);
}

function previewText(line: Buffer): string {
  return line.toString('utf8').replaceAll('\r', '\u240d');
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}
