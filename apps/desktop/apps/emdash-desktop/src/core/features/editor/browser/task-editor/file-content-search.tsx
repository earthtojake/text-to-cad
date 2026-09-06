import {
  portableRelativePathBasename,
  portableRelativePathDirname,
} from '@emdash/core/primitives/path/api';
import type {
  ContentSearchFileResult,
  ContentSearchLineMatch,
} from '@emdash/core/runtimes/file-search/api';
import {
  SearchResultsTree,
  type SearchResultFile,
  type SearchResultMatch,
} from '@emdash/ui/react/components';
import {
  createLiveJobReplicaCache,
  LiveJobCancelledError,
  LiveJobFailedError,
} from '@emdash/wire/live';
import { Loader2 } from 'lucide-react';
import { useMemo, useState, useEffect } from 'react';
import type {
  FileSelection,
  FileTabResource,
} from '@core/features/editor/api/browser/task-editor/stores/file-tab-resource';
import { FileIcon } from '@core/features/editor/contributions/browser/file-icon';
import { searchContract } from '@core/features/search/api';
import { getSearchClient } from '@core/features/search/api/client';
import { useTaskComposition } from '@core/features/workbench/api/browser/task-composition-context';
import { useDebounce } from '@core/primitives/react-hooks/browser/useDebounce';
import {
  countContentSearchOccurrences,
  mergeContentSearchFiles,
} from './file-content-search-model';

const SEARCH_DEBOUNCE_MS = 200;

type SearchState = Readonly<{
  files: ContentSearchFileResult[];
  isSearching: boolean;
  complete: boolean;
  error: string | null;
}>;

const INITIAL_SEARCH_STATE: SearchState = {
  files: [],
  isSearching: true,
  complete: true,
  error: null,
};

export function FileContentSearchResults({
  workspaceId,
  query,
}: {
  workspaceId: string;
  query: string;
}) {
  const taskView = useTaskComposition();
  const debouncedQuery = useDebounce(query, SEARCH_DEBOUNCE_MS);
  const [state, setState] = useState<SearchState>(INITIAL_SEARCH_STATE);

  useEffect(() => {
    setState(INITIAL_SEARCH_STATE);
    if (query !== debouncedQuery || !debouncedQuery) return;

    let disposed = false;
    let cancelActiveJob: (() => void) | undefined;

    void (async () => {
      try {
        const client = await getSearchClient();
        if (disposed) return;
        const jobs = createLiveJobReplicaCache(
          searchContract.searchWorkspaceContent,
          client.searchWorkspaceContent
        );
        let lease: Awaited<ReturnType<typeof jobs.start>> | undefined;
        let unsubscribe: (() => void) | undefined;
        try {
          lease = await jobs.start({ workspaceId, query: debouncedQuery });
          const job = await lease.ready();
          cancelActiveJob = () => void job.cancel();
          if (disposed) {
            await job.cancel();
            return;
          }

          unsubscribe = job.onProgress((progress) => {
            if (disposed) return;
            setState((current) => ({
              ...current,
              files: mergeContentSearchFiles(current.files, progress.files),
            }));
          });

          const result = await job.result;
          if (!disposed) {
            setState({
              files: result.files,
              isSearching: false,
              complete: result.complete,
              error: null,
            });
          }
        } finally {
          unsubscribe?.();
          await lease?.release();
          await jobs.dispose();
        }
      } catch (error) {
        if (!disposed && !(error instanceof LiveJobCancelledError)) {
          setState({
            files: [],
            isSearching: false,
            complete: true,
            error: contentSearchErrorMessage(error),
          });
        }
      }
    })();

    return () => {
      disposed = true;
      cancelActiveJob?.();
    };
  }, [debouncedQuery, query, workspaceId]);

  const searchFiles = useMemo(() => mapSearchFiles(state.files), [state.files]);
  const matchByKey = useMemo(() => coreMatchByKey(state.files), [state.files]);

  const occurrenceCount = countContentSearchOccurrences(state.files);
  const resultSummary = `${occurrenceCount} ${occurrenceCount === 1 ? 'result' : 'results'} in ${state.files.length} ${state.files.length === 1 ? 'file' : 'files'}`;

  const openMatch = (path: string, match: ContentSearchLineMatch, preview: boolean) => {
    const location = match.locations[0];
    if (!location) return;
    taskView.paneLayout.open('file', { path }, { preview });
    const resource = taskView.activePane.activeResourceOfKind<FileTabResource>('file');
    if (!resource) return;
    const selection: FileSelection = {
      lineNumber: match.lineNumber,
      startColumn: location.sourceRange.startColumn,
      endColumn: location.sourceRange.endColumn,
    };
    resource.requestSelection(selection);
    taskView.setFocusedRegion('main');
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex h-8 shrink-0 items-center gap-1.5 px-3 text-xs text-foreground-muted">
        {state.isSearching && <Loader2 className="size-3 animate-spin" aria-label="Searching" />}
        <span>{resultSummary}</span>
      </div>

      {state.error ? (
        <div className="px-3 py-6 text-center text-xs text-foreground-destructive">
          {state.error}
        </div>
      ) : !state.isSearching && state.files.length === 0 ? (
        <div className="px-3 py-6 text-center text-xs text-foreground-muted">No results found</div>
      ) : (
        <SearchResultsTree
          files={searchFiles}
          className="min-h-0 flex-1"
          ariaLabel="File content search results"
          renderFileIcon={(file) => <FileIcon filename={file.name} size={12} />}
          onOpenMatch={(file, match, { preview }) => {
            const coreMatch = matchByKey.get(matchKey(file.path, match));
            if (coreMatch) openMatch(file.path, coreMatch, preview);
          }}
        />
      )}

      {!state.isSearching && !state.complete && (
        <div className="shrink-0 border-t border-border px-3 py-2 text-xs text-foreground-muted">
          Results were limited. Refine your search to see more.
        </div>
      )}
    </div>
  );
}

function mapSearchFiles(files: readonly ContentSearchFileResult[]): SearchResultFile[] {
  return files.map((file) => ({
    path: file.path,
    name: portableRelativePathBasename(file.path),
    directory: portableRelativePathDirname(file.path) ?? '',
    occurrenceCount: countContentSearchOccurrences([file]),
    matches: file.matches.map((match) => ({
      lineNumber: match.lineNumber,
      previewText: match.previewText,
      highlightRanges: match.locations.map((location) => location.previewRange),
    })),
  }));
}

function coreMatchByKey(
  files: readonly ContentSearchFileResult[]
): ReadonlyMap<string, ContentSearchLineMatch> {
  const matches = new Map<string, ContentSearchLineMatch>();
  for (const file of files) {
    for (const match of file.matches) {
      matches.set(matchKey(file.path, match), match);
    }
  }
  return matches;
}

function matchKey(path: string, match: Pick<SearchResultMatch, 'lineNumber'>): string {
  return `${path}:${match.lineNumber}`;
}

function contentSearchErrorMessage(error: unknown): string {
  const payload = error instanceof LiveJobFailedError ? error.error : error;
  if (typeof payload === 'object' && payload !== null && 'message' in payload) {
    const message = payload.message;
    if (typeof message === 'string') return message;
  }
  return error instanceof Error ? error.message : 'Search failed';
}
