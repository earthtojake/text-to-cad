import { basenameFromAnyPath } from '@core/primitives/path-name/api/path-name';
import type { ProjectWorkspaceRow } from '@core/primitives/workspaces/api';

/** Display label for a workspace row: branch name, else the path's last segment. */
export function workspaceRowLabel(row: ProjectWorkspaceRow): string {
  return row.branch ?? (basenameFromAnyPath(row.path) || row.path);
}
