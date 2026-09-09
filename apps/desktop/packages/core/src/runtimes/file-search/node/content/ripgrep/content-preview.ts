import {
  CONTENT_SEARCH_MAX_PREVIEW_LENGTH,
  type ContentSearchRange,
} from '#runtimes/file-search/api';

export const DEFAULT_CONTENT_PREVIEW_CHARS_PER_MATCH = 1_000;
export const DEFAULT_CONTENT_PREVIEW_MAX_LENGTH = CONTENT_SEARCH_MAX_PREVIEW_LENGTH;

const DEFAULT_LEADING_CONTEXT_RATIO = 0.2;
const ELISION_PREFIX = '⟪ ';
const ELISION_SUFFIX = ' characters skipped ⟫';

export type ContentPreviewRangeLocation = Readonly<{
  sourceRange: ContentSearchRange;
  previewRange: ContentSearchRange;
}>;

export type ContentSearchPreview = Readonly<{
  previewText: string;
  locations: ContentPreviewRangeLocation[];
  locationsOmitted: boolean;
}>;

export type ContentSearchPreviewOptions = Readonly<{
  /** Desired UTF-16 code units of match and context for each occurrence. */
  charsPerMatch?: number;
  /** Absolute UTF-16 code-unit bound for the returned preview, including elisions. */
  maxLength?: number;
  /** Portion of each context budget placed before the occurrence. */
  leadingContextRatio?: number;
}>;

type OffsetRange = Readonly<{
  start: number;
  end: number;
  sourceRange: ContentSearchRange;
  originalIndex: number;
}>;

type Window = {
  start: number;
  end: number;
};

/**
 * Builds a bounded, single-line preview while retaining real source coordinates for navigation.
 * Locations are returned in source order. Complete locations are always budgeted before context.
 */
export function createContentSearchPreview(
  text: string,
  sourceRanges: readonly ContentSearchRange[],
  options: ContentSearchPreviewOptions = {}
): ContentSearchPreview {
  const charsPerMatch = positiveInteger(
    options.charsPerMatch ?? DEFAULT_CONTENT_PREVIEW_CHARS_PER_MATCH,
    'charsPerMatch'
  );
  const maxLength = positiveInteger(
    options.maxLength ?? DEFAULT_CONTENT_PREVIEW_MAX_LENGTH,
    'maxLength'
  );
  const leadingContextRatio = ratio(options.leadingContextRatio ?? DEFAULT_LEADING_CONTEXT_RATIO);
  const ranges = normalizeRanges(text, sourceRanges);
  const selectedRanges = selectLocations(ranges, text.length, maxLength);

  if (selectedRanges.length === 0) {
    return {
      previewText: '',
      locations: [],
      locationsOmitted: ranges.length > 0,
    };
  }

  const maximumContext = selectedRanges.reduce(
    (maximum, range) => Math.max(maximum, charsPerMatch - (range.end - range.start)),
    0
  );
  let minimumContext = 0;
  let maximumFittingContext = Math.max(0, maximumContext);

  while (minimumContext < maximumFittingContext) {
    const candidateContext = Math.ceil((minimumContext + maximumFittingContext) / 2);
    const candidateWindows = buildWindows(
      text,
      selectedRanges,
      candidateContext,
      charsPerMatch,
      leadingContextRatio
    );
    if (renderedLength(candidateWindows, text.length) <= maxLength) {
      minimumContext = candidateContext;
    } else {
      maximumFittingContext = candidateContext - 1;
    }
  }

  const windows = buildWindows(
    text,
    selectedRanges,
    minimumContext,
    charsPerMatch,
    leadingContextRatio
  );
  const rendered = renderPreview(text, windows, selectedRanges);

  if (rendered.previewText.length > maxLength) {
    throw new Error('Content preview exceeded its hard length bound');
  }

  return {
    ...rendered,
    locationsOmitted: selectedRanges.length < ranges.length,
  };
}

function normalizeRanges(text: string, sourceRanges: readonly ContentSearchRange[]): OffsetRange[] {
  return sourceRanges
    .map((range, originalIndex): OffsetRange => {
      const { startColumn, endColumn } = range;
      if (
        !Number.isInteger(startColumn) ||
        !Number.isInteger(endColumn) ||
        startColumn < 1 ||
        endColumn <= startColumn ||
        endColumn > text.length + 1
      ) {
        throw new RangeError('Content preview received an out-of-bounds source range');
      }

      const start = startColumn - 1;
      const end = endColumn - 1;
      if (!isUtf16Boundary(text, start) || !isUtf16Boundary(text, end)) {
        throw new RangeError('Content preview source ranges cannot split UTF-16 surrogate pairs');
      }

      return {
        start,
        end,
        sourceRange: { startColumn, endColumn },
        originalIndex,
      };
    })
    .sort(
      (left, right) =>
        left.start - right.start || left.end - right.end || left.originalIndex - right.originalIndex
    );
}

/** Selects every location if their match-only representation fits; otherwise omits deterministically. */
function selectLocations(
  ranges: readonly OffsetRange[],
  textLength: number,
  maxLength: number
): OffsetRange[] {
  const selected: OffsetRange[] = [];
  const windows: Window[] = [];
  let currentLength = 0;

  for (const range of ranges) {
    const last = windows.at(-1);
    if (!last) {
      const candidateLength =
        omittedLength(range.start) +
        (range.end - range.start) +
        omittedLength(textLength - range.end);
      if (candidateLength > maxLength) break;

      windows.push({ start: range.start, end: range.end });
      selected.push(range);
      currentLength = candidateLength;
      continue;
    }

    const previousSuffixLength = omittedLength(textLength - last.end);
    const candidateEnd = Math.max(last.end, range.end);
    const candidateSuffixLength = omittedLength(textLength - candidateEnd);
    let candidateLength: number;
    let mergeWithLast = range.start <= last.end;

    if (mergeWithLast) {
      candidateLength =
        currentLength + candidateEnd - last.end + candidateSuffixLength - previousSuffixLength;
    } else {
      const gap = range.start - last.end;
      mergeWithLast = shouldMergeGap(gap);
      candidateLength =
        currentLength -
        previousSuffixLength +
        (mergeWithLast ? gap : omittedLength(gap)) +
        (range.end - range.start) +
        candidateSuffixLength;
    }

    if (candidateLength > maxLength) break;

    if (mergeWithLast) last.end = candidateEnd;
    else windows.push({ start: range.start, end: range.end });
    selected.push(range);
    currentLength = candidateLength;
  }

  return selected;
}

function buildWindows(
  text: string,
  ranges: readonly OffsetRange[],
  contextPerMatch: number,
  charsPerMatch: number,
  leadingContextRatio: number
): Window[] {
  const windows: Window[] = [];

  for (const range of ranges) {
    const matchLength = range.end - range.start;
    const context = Math.min(contextPerMatch, Math.max(0, charsPerMatch - matchLength));
    const leadingContext = Math.floor(context * leadingContextRatio);
    const trailingContext = context - leadingContext;
    let start = Math.max(0, range.start - leadingContext);
    let end = Math.min(text.length, range.end + trailingContext);

    const missingLeadingContext = leadingContext - (range.start - start);
    if (missingLeadingContext > 0) end = Math.min(text.length, end + missingLeadingContext);
    const missingTrailingContext = trailingContext - (end - range.end);
    if (missingTrailingContext > 0) start = Math.max(0, start - missingTrailingContext);

    start = utf16BoundaryAtOrAfter(text, start);
    end = utf16BoundaryAtOrBefore(text, end);

    const last = windows.at(-1);
    if (!last) {
      windows.push({ start, end });
      continue;
    }

    const gap = start - last.end;
    if (gap <= 0 || shouldMergeGap(gap)) last.end = Math.max(last.end, end);
    else windows.push({ start, end });
  }

  return windows;
}

function renderPreview(
  text: string,
  windows: readonly Window[],
  ranges: readonly OffsetRange[]
): Pick<ContentSearchPreview, 'previewText' | 'locations'> {
  let previewText = '';
  let sourceCursor = 0;
  const renderedWindows: Array<Window & { previewStart: number }> = [];

  for (const window of windows) {
    if (window.start > sourceCursor) previewText += elision(window.start - sourceCursor);
    const previewStart = previewText.length;
    previewText += text.slice(window.start, window.end);
    renderedWindows.push({ ...window, previewStart });
    sourceCursor = window.end;
  }
  if (sourceCursor < text.length) previewText += elision(text.length - sourceCursor);

  let windowIndex = 0;
  const locations = ranges.map((range): ContentPreviewRangeLocation => {
    while (renderedWindows[windowIndex].end < range.end) windowIndex += 1;
    const window = renderedWindows[windowIndex];
    if (range.start < window.start || range.end > window.end) {
      throw new Error('Content preview failed to retain a selected source location');
    }

    const previewStart = window.previewStart + range.start - window.start;
    return {
      sourceRange: { ...range.sourceRange },
      previewRange: {
        startColumn: previewStart + 1,
        endColumn: previewStart + (range.end - range.start) + 1,
      },
    };
  });

  return { previewText, locations };
}

function renderedLength(windows: readonly Window[], textLength: number): number {
  if (windows.length === 0) return 0;

  let length = omittedLength(windows[0].start);
  for (let index = 0; index < windows.length; index += 1) {
    const window = windows[index];
    length += window.end - window.start;
    const next = windows[index + 1];
    if (next) length += omittedLength(next.start - window.end);
  }
  return length + omittedLength(textLength - windows.at(-1)!.end);
}

function shouldMergeGap(gap: number): boolean {
  return gap <= omittedLength(gap);
}

function omittedLength(count: number): number {
  return count > 0 ? elision(count).length : 0;
}

function elision(count: number): string {
  return `${ELISION_PREFIX}${count}${ELISION_SUFFIX}`;
}

function utf16BoundaryAtOrAfter(text: string, offset: number): number {
  return isUtf16Boundary(text, offset) ? offset : offset + 1;
}

function utf16BoundaryAtOrBefore(text: string, offset: number): number {
  return isUtf16Boundary(text, offset) ? offset : offset - 1;
}

function isUtf16Boundary(text: string, offset: number): boolean {
  if (offset <= 0 || offset >= text.length) return true;
  return !(isHighSurrogate(text.charCodeAt(offset - 1)) && isLowSurrogate(text.charCodeAt(offset)));
}

function isHighSurrogate(codeUnit: number): boolean {
  return codeUnit >= 0xd800 && codeUnit <= 0xdbff;
}

function isLowSurrogate(codeUnit: number): boolean {
  return codeUnit >= 0xdc00 && codeUnit <= 0xdfff;
}

function positiveInteger(value: number, name: string): number {
  if (!Number.isInteger(value) || value <= 0) {
    throw new RangeError(`Content preview ${name} must be a positive integer`);
  }
  return value;
}

function ratio(value: number): number {
  if (!Number.isFinite(value) || value < 0 || value > 1) {
    throw new RangeError('Content preview leadingContextRatio must be between zero and one');
  }
  return value;
}
