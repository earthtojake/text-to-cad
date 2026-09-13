import { relativeToWorkspace } from '@core/features/workspaces/api/browser/workspace-path';

export function getPaletteFileDisplayPath({
  workspacePath,
  filePath,
  fallback,
}: {
  workspacePath?: string;
  filePath: string;
  fallback?: string;
}): string {
  if (!workspacePath) return fallback ?? filePath.replace(/\\/g, '/');
  return relativeToWorkspace(workspacePath, filePath);
}
