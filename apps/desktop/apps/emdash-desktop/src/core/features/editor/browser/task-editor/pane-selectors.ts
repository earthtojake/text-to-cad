import type { FileTabResource } from '@core/features/editor/api/browser/task-editor/stores/file-tab-resource';
/**
 * Pane selectors for the editor domain.
 *
 * These helpers let editor code read file-tab state from a generic PaneStore /
 * PaneLayoutStore without the engine having to know about FileTabResource.
 */
import type { PaneLayoutStore } from '@core/primitives/workbench-shell/browser/tabs/pane-layout-store';
import type { PaneStore } from '@core/primitives/workbench-shell/browser/tabs/pane-store';

export function activeFileResource(pane: PaneStore): FileTabResource | undefined {
  return pane.activeResourceOfKind<FileTabResource>('file');
}

export function fileResourceByPath(pane: PaneStore, path: string): FileTabResource | undefined {
  return pane.resourcesOfKind<FileTabResource>('file').find((r) => r.path === path);
}

export function activeFilePath(pane: PaneStore): string | null {
  return activeFileResource(pane)?.path ?? null;
}

/** All open file tab resources for a single pane, in tab-order. */
export function openFileResources(pane: PaneStore): FileTabResource[] {
  return pane.resourcesOfKind<FileTabResource>('file');
}

/** Union of open file tab resources across all panes (de-duplicated by path). */
export function allOpenFileResources(paneLayout: PaneLayoutStore): FileTabResource[] {
  const seen = new Map<string, FileTabResource>();
  for (const { pane } of paneLayout.groups) {
    for (const resource of openFileResources(pane)) {
      if (!seen.has(resource.path)) seen.set(resource.path, resource);
    }
  }
  return [...seen.values()];
}

/** Union of open file paths across all panes (de-duplicated). */
export function allOpenFilePaths(paneLayout: PaneLayoutStore): string[] {
  return allOpenFileResources(paneLayout).map((r) => r.path);
}
