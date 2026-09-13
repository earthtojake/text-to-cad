import type { ProjectWorkspaceGitStats } from '@core/primitives/workspaces/api';

export function GitStatsCell({
  stats,
  loading,
}: {
  stats: ProjectWorkspaceGitStats | undefined;
  loading: boolean;
}) {
  if (stats) {
    const hasStats = stats.added > 0 || stats.removed > 0 || stats.ahead > 0 || stats.behind > 0;
    if (!hasStats) return '-';

    return (
      <span className="inline-flex gap-1">
        {stats.added > 0 && <span className="text-foreground-diff-added">+{stats.added}</span>}
        {stats.removed > 0 && (
          <span className="text-foreground-diff-deleted">-{stats.removed}</span>
        )}
        {stats.ahead > 0 && <span>↑{stats.ahead}</span>}
        {stats.behind > 0 && <span>↓{stats.behind}</span>}
      </span>
    );
  }
  return loading ? 'Loading...' : '-';
}
