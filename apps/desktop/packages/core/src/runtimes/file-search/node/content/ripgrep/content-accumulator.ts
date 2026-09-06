import type { PortableRelativePath } from '#primitives/path/api';
import {
  type ContentSearchFileResult,
  type ContentSearchLineMatch,
  type ContentSearchResult,
} from '#runtimes/file-search/api';
import type { ContentSearchContext } from '../content-searcher';

const PROGRESS_MATCH_BATCH_SIZE = 50;
export const CONTENT_SEARCH_MAX_ACCUMULATED_PREVIEW_LENGTH = 4 * 1024 * 1024;

/** Bounds and batches the append-only result stream produced by the ripgrep adapter. */
export class ContentSearchAccumulator {
  private readonly files = new Map<PortableRelativePath, ContentSearchLineMatch[]>();
  private readonly progress = new Map<PortableRelativePath, ContentSearchLineMatch[]>();
  private occurrenceCount = 0;
  private pendingOccurrenceCount = 0;
  private textLength = 0;

  constructor(private readonly context: ContentSearchContext) {}

  remainingOccurrences(limit: number): number {
    return Math.max(0, limit - this.occurrenceCount);
  }

  remainingTextLength(): number {
    return Math.max(0, CONTENT_SEARCH_MAX_ACCUMULATED_PREVIEW_LENGTH - this.textLength);
  }

  add(path: PortableRelativePath, match: ContentSearchLineMatch, limit: number): boolean {
    const remaining = this.remainingOccurrences(limit);
    if (remaining <= 0) return true;

    if (
      this.textLength + match.previewText.length >
      CONTENT_SEARCH_MAX_ACCUMULATED_PREVIEW_LENGTH
    ) {
      return true;
    }

    const locations = match.locations.slice(0, remaining).map(cloneLocation);
    const lineMatch: ContentSearchLineMatch = {
      lineNumber: match.lineNumber,
      previewText: match.previewText,
      locations,
    };
    appendLineMatch(this.files, path, lineMatch);
    appendLineMatch(this.progress, path, {
      ...lineMatch,
      locations: lineMatch.locations.map(cloneLocation),
    });
    this.textLength += match.previewText.length;
    this.occurrenceCount += locations.length;
    this.pendingOccurrenceCount += locations.length;
    if (this.pendingOccurrenceCount >= PROGRESS_MATCH_BATCH_SIZE) this.flushProgress();
    return locations.length < match.locations.length || this.occurrenceCount >= limit;
  }

  result(complete: boolean): ContentSearchResult {
    this.flushProgress();
    const files = toFileResults(this.files);
    return { files, complete };
  }

  private flushProgress(): void {
    if (this.pendingOccurrenceCount === 0 || this.context.signal.aborted) return;
    this.context.onProgress({ files: toFileResults(this.progress) });
    this.progress.clear();
    this.pendingOccurrenceCount = 0;
  }
}

function appendLineMatch(
  files: Map<PortableRelativePath, ContentSearchLineMatch[]>,
  path: PortableRelativePath,
  match: ContentSearchLineMatch
): void {
  const matches = files.get(path);
  if (!matches) {
    files.set(path, [match]);
    return;
  }
  matches.push(match);
}

function toFileResults(
  files: ReadonlyMap<PortableRelativePath, ContentSearchLineMatch[]>
): ContentSearchFileResult[] {
  return [...files].map(([path, matches]) => ({
    path,
    matches: matches.map((match) => ({
      ...match,
      locations: match.locations.map(cloneLocation),
    })),
  }));
}

function cloneLocation(location: ContentSearchLineMatch['locations'][number]) {
  return {
    sourceRange: { ...location.sourceRange },
    previewRange: { ...location.previewRange },
  };
}
