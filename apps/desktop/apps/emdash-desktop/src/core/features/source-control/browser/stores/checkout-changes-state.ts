import type {
  CheckoutStatusState,
  FileGitStatus,
  GitChange,
  GitChangeStatus,
} from '@emdash/core/runtimes/git/api';

export interface CheckoutChangesState {
  staged: GitChange[];
  unstaged: GitChange[];
}

export function emptyCheckoutChangesState(): CheckoutChangesState {
  return { staged: [], unstaged: [] };
}

/**
 * Projects visible membership from status and uses diff reads only to enrich
 * entries which status says belong to that side.
 */
export function projectCheckoutChanges(
  status: CheckoutStatusState | undefined,
  metadata: CheckoutChangesState
): CheckoutChangesState {
  if (!status || status.kind !== 'ok') return emptyCheckoutChangesState();

  const stagedMetadata = new Map(metadata.staged.map((change) => [change.path, change]));
  const unstagedMetadata = new Map(metadata.unstaged.map((change) => [change.path, change]));
  const staged: GitChange[] = [];
  const unstaged: GitChange[] = [];

  for (const entry of Object.values(status.entries)) {
    if (isChangedOnSide(entry, 'staged')) {
      staged.push(stagedMetadata.get(entry.path) ?? changeFromStatus(entry, 'staged'));
    }
    if (isChangedOnSide(entry, 'unstaged')) {
      unstaged.push(unstagedMetadata.get(entry.path) ?? changeFromStatus(entry, 'unstaged'));
    }
  }

  return { staged, unstaged };
}

export function reduceStageFiles(
  changes: CheckoutChangesState,
  input: { paths: readonly string[] }
): void {
  movePaths(changes, input.paths, 'unstaged', 'staged');
}

export function reduceStageAll(changes: CheckoutChangesState): void {
  changes.staged = mergeByPath([...changes.staged, ...changes.unstaged]);
  changes.unstaged = [];
}

export function reduceUnstageFiles(
  changes: CheckoutChangesState,
  input: { paths: readonly string[] }
): void {
  movePaths(changes, input.paths, 'staged', 'unstaged');
}

export function reduceUnstageAll(changes: CheckoutChangesState): void {
  changes.unstaged = mergeByPath([...changes.unstaged, ...changes.staged]);
  changes.staged = [];
}

function isChangedOnSide(entry: FileGitStatus, side: 'staged' | 'unstaged'): boolean {
  return side === 'staged'
    ? entry.index !== 'unmodified' && entry.index !== 'untracked' && entry.index !== 'ignored'
    : entry.worktree !== 'unmodified' && entry.worktree !== 'ignored';
}

function changeFromStatus(entry: FileGitStatus, side: 'staged' | 'unstaged'): GitChange {
  const code = side === 'staged' ? entry.index : entry.worktree;
  let status: GitChangeStatus = 'modified';
  if (entry.isConflicted || code === 'unmerged') status = 'conflicted';
  else if (code === 'added' || code === 'copied' || code === 'untracked') status = 'added';
  else if (code === 'deleted') status = 'deleted';
  else if (code === 'renamed') status = 'renamed';
  return { path: entry.path, status, additions: 0, deletions: 0 };
}

function movePaths(
  changes: CheckoutChangesState,
  paths: readonly string[],
  from: keyof CheckoutChangesState,
  to: keyof CheckoutChangesState
): void {
  const requested = new Set(paths);
  const moving = changes[from].filter((change) => requested.has(change.path));
  const movingPaths = new Set(moving.map((change) => change.path));
  changes[from] = changes[from].filter((change) => !requested.has(change.path));
  changes[to] = [...changes[to].filter((change) => !movingPaths.has(change.path)), ...moving];
}

function mergeByPath(changes: GitChange[]): GitChange[] {
  return [...new Map(changes.map((change) => [change.path, change])).values()];
}
