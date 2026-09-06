import { Tooltip } from '@emdash/ui/react/primitives';
import { cn } from '@core/primitives/styling/browser/cn';
import {
  workspaceRemovalNeedsAttention,
  type ProjectWorkspacePathIssue,
  type ProjectWorkspaceRow,
} from '@core/primitives/workspaces/api';
import { workspaceRowLabel } from './workspace-row-label';

type PillTone = 'warning' | 'destructive';

const PILL_BASE =
  'shrink-0 rounded-full border px-1.5 py-0.5 text-micro tracking-[1.25px] uppercase';

function pillClass(tone: PillTone, options: { pulse?: boolean; className?: string } = {}): string {
  return cn(
    PILL_BASE,
    tone === 'warning'
      ? 'border-border-warning text-foreground-warning'
      : 'border-border-destructive text-foreground-destructive',
    options.pulse && 'animate-pulse',
    options.className
  );
}

/** Pending-deletion treatment: the tombstoned row is its own visible state (ADR 0006). */
export function RemovalPill({
  pendingRemoval,
  needsAttention,
  message,
  className,
}: {
  pendingRemoval: boolean;
  needsAttention: boolean;
  message?: string;
  className?: string;
}) {
  if (!pendingRemoval) return null;
  if (needsAttention) {
    return (
      <Tooltip.Root>
        <Tooltip.Trigger>
          <span className={pillClass('destructive', { className })}>Removal failed</span>
        </Tooltip.Trigger>
        <Tooltip.Content className="max-w-70 text-xs">
          {message ?? 'The removal stopped after a failure that needs your decision.'}
        </Tooltip.Content>
      </Tooltip.Root>
    );
  }
  return <span className={pillClass('warning', { pulse: true, className })}>Removing…</span>;
}

/** Aggregate pending-removal pill for a whole project; renders nothing while clear. */
export function RemovalSummaryPill({
  rows,
  className,
}: {
  rows: readonly ProjectWorkspaceRow[];
  className?: string;
}) {
  const pendingRows = rows.filter((row) => row.pendingRemoval);
  if (pendingRows.length === 0) return null;
  const needsAttention = pendingRows.filter((row) => workspaceRemovalNeedsAttention(row)).length;
  const label =
    needsAttention > 0
      ? `${needsAttention} ${needsAttention === 1 ? 'removal needs' : 'removals need'} attention`
      : `${pendingRows.length} ${pendingRows.length === 1 ? 'removal' : 'removals'} pending`;
  return (
    <span
      className={pillClass(needsAttention > 0 ? 'destructive' : 'warning', {
        pulse: needsAttention === 0,
        className,
      })}
    >
      {label}
    </span>
  );
}

export function pathIssueMessage(
  issue: ProjectWorkspacePathIssue | undefined,
  path: string
): string {
  if (!issue) return 'Workspace path needs attention.';
  if (issue.reason) return issue.reason;
  if (issue.kind === 'prunable') return 'Git reports this worktree as prunable.';
  return `Directory not found at ${path}.`;
}

export function PathIssueChip({
  issue,
  path,
  className,
}: {
  issue: ProjectWorkspacePathIssue;
  path: string;
  className?: string;
}) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger>
        <span
          className={pillClass(issue.kind === 'prunable' ? 'warning' : 'destructive', {
            className,
          })}
        >
          {issue.kind === 'prunable' ? 'Stale git record' : 'Missing'}
        </span>
      </Tooltip.Trigger>
      <Tooltip.Content className="max-w-80 text-xs">
        {pathIssueMessage(issue, path)}
      </Tooltip.Content>
    </Tooltip.Root>
  );
}

/** Aggregate path-issue pill for a whole project; renders nothing while clear. */
export function PathIssueSummaryPill({
  rows,
  className,
}: {
  rows: readonly ProjectWorkspaceRow[];
  className?: string;
}) {
  const issueRows = rows.filter((row) => row.pathIssue !== undefined);
  const summary = pathIssueSummary(issueRows);
  if (!summary) return null;
  return (
    <Tooltip.Root>
      <Tooltip.Trigger>
        <span className={pillClass('warning', { className })}>{summary}</span>
      </Tooltip.Trigger>
      <Tooltip.Content className="max-w-96 text-xs">
        <div className="flex flex-col gap-1">
          {issueRows.map((row) => (
            <div key={`${row.workspaceId ?? row.path}:${row.path}`} className="min-w-0">
              <div className="font-medium">{workspaceRowLabel(row)}</div>
              <div className="text-foreground-muted">
                {pathIssueMessage(row.pathIssue, row.path)}
              </div>
            </div>
          ))}
        </div>
      </Tooltip.Content>
    </Tooltip.Root>
  );
}

function pathIssueSummary(rows: readonly ProjectWorkspaceRow[]): string | undefined {
  if (rows.length === 0) return undefined;
  const [first] = rows;
  if (rows.length === 1 && first?.pathIssue) {
    return first.pathIssue.kind === 'prunable'
      ? `${workspaceRowLabel(first)} has a stale git record`
      : `${workspaceRowLabel(first)} missing`;
  }
  return `${rows.length} worktrees need attention`;
}
