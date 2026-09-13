import type { HostObservation } from '@core/features/projects/api/host-observation';
import {
  workspaceRemovalNeedsAttention,
  type MeasureProjectWorkspacesResult,
  type ProjectWorkspaceGitStats,
  type ProjectWorkspaceRow,
  type ProjectWorkspaceUsage,
} from '@core/primitives/workspaces/api';
import type { WorkspaceRuntimeStatus } from './workspace-runtime-status';

export type JoinedWorkspaceRow = {
  row: ProjectWorkspaceRow;
  key: string;
  status: WorkspaceRuntimeStatus;
  /** Tombstone presence (ADR 0006): the row itself is the visible pending deletion. */
  pendingRemoval: boolean;
  /** Terminal removal failure: auto-retry stopped; Retry / Untrack-anyway apply. */
  removalNeedsAttention: boolean;
  /** One-line detail for error states (failed removal or failed create). */
  statusMessage?: string;
  usage?: ProjectWorkspaceUsage;
  gitStats?: ProjectWorkspaceGitStats;
};

export type WorkspaceRowSources = {
  rows: readonly ProjectWorkspaceRow[];
  usageResults?: MeasureProjectWorkspacesResult['results'];
};

export function joinWorkspaceRows(sources: WorkspaceRowSources): JoinedWorkspaceRow[] {
  const usageByPath = successfulResultsByPath(sources.usageResults, (result) => result.usage);

  return sources.rows.map((row) => {
    const removalNeedsAttention = workspaceRemovalNeedsAttention(row);
    return {
      row,
      key: row.workspaceId ?? row.path,
      status: workspaceRowStatus(row, removalNeedsAttention),
      pendingRemoval: row.pendingRemoval,
      removalNeedsAttention,
      statusMessage: rowStatusMessage(row, removalNeedsAttention),
      usage: usageByPath.get(row.path),
      // Mirror-derived; `added` includes untracked files' lines.
      gitStats: row.gitStats ?? undefined,
    };
  });
}

export function workspaceRowsHostObservation(
  rows: readonly JoinedWorkspaceRow[]
): HostObservation<readonly JoinedWorkspaceRow[]> {
  const observedAt = rows.reduce((latest, joined) => {
    const timestamp = joined.row.lastObservedAt
      ? Date.parse(joined.row.lastObservedAt)
      : Number.NaN;
    return Number.isFinite(timestamp) ? Math.max(latest, timestamp) : latest;
  }, 0);
  return observedAt > 0
    ? { kind: 'observed', value: rows, observedAt }
    : { kind: 'never-observed' };
}

/**
 * Session activity is the baseline; the mirror's deletion tombstone and outcome
 * fields refine it into tearing-down / setting-up / error (spec §2, §6).
 */
function workspaceRowStatus(
  row: ProjectWorkspaceRow,
  removalNeedsAttention: boolean
): WorkspaceRuntimeStatus {
  if (removalNeedsAttention) return 'error';
  if (row.pendingRemoval) return 'tearing-down';
  if (row.lastCreateOutcome?.status === 'failed') return 'error';
  if (row.runtimeOverlay?.creation) return 'setting-up';
  return row.hasActiveSessions ? 'active' : 'idle';
}

function rowStatusMessage(
  row: ProjectWorkspaceRow,
  removalNeedsAttention: boolean
): string | undefined {
  if (removalNeedsAttention) return row.removalStop?.message;
  if (row.pendingRemoval) return undefined;
  if (row.lastCreateOutcome?.status === 'failed') return row.lastCreateOutcome.message;
  return undefined;
}

function successfulResultsByPath<TValue, TResult extends { path: string; success: boolean }>(
  results: readonly TResult[] | undefined,
  value: (result: Extract<TResult, { success: true }>) => TValue
): Map<string, TValue> {
  const byPath = new Map<string, TValue>();
  for (const result of results ?? []) {
    if (result.success)
      byPath.set(result.path, value(result as Extract<TResult, { success: true }>));
  }
  return byPath;
}
