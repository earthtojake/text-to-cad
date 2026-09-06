import {
  splitPanePanelId,
  type TabDescriptor,
  type TaskDiffSelectionState,
  type TaskPaneLayoutState,
} from '@core/features/tasks/contributions/mementos';
import { resolveWorkspacePath } from '@core/features/workspaces/api/browser/workspace-path';
import type { MementoLayoutStorage } from '@core/primitives/mementos/browser';

export function sanitizeDiffSelection(
  value: TaskDiffSelectionState,
  validPaths: ReadonlySet<string>
): TaskDiffSelectionState {
  const activeFile = value.activeFile;
  if (!activeFile || activeFile.group === 'git' || activeFile.group === 'pr') return value;
  if (
    (activeFile.group === 'disk' || activeFile.group === 'staged') &&
    !validPaths.has(activeFile.path)
  ) {
    return { ...value, activeFile: undefined };
  }
  return value;
}

/**
 * Resolves persisted file-tab paths to absolute runtime identity. Diff-tab
 * paths are already validated checkout-relative GitFilePaths and pass through.
 */
export function resolvePaneLayoutFilePaths(
  value: TaskPaneLayoutState,
  workspacePath: string
): TaskPaneLayoutState {
  return {
    ...value,
    groups: value.groups.map((group) => ({
      ...group,
      tabManager: {
        ...group.tabManager,
        tabs: group.tabManager.tabs.map((tab) => resolveTabDescriptorPath(tab, workspacePath)),
      },
    })),
  };
}

function resolveTabDescriptorPath(tab: TabDescriptor, workspacePath: string): TabDescriptor {
  if (tab.kind === 'file' || tab.kind === 'cad') {
    return { ...tab, path: resolveWorkspacePath(workspacePath, tab.path) };
  }
  return tab;
}

/**
 * Drops every persisted panel-layout entry that references a destroyed
 * split-pane group, so a later re-split (new group id) starts fresh from
 * defaults instead of accreting dead entries.
 *
 * Storage entry keys are library-internal
 * (`react-resizable-panels:${groupId}:${panelIds...}`), so an entry
 * references the pane group iff its `pane:${paneGroupId}` panel id appears as
 * a `:`-delimited segment. Pane group ids are UUIDs of fixed length, so a
 * substring match cannot hit a different group.
 */
export function deleteSplitPaneLayoutEntries(
  storage: Pick<MementoLayoutStorage, 'deleteEntry'>,
  entryKeys: readonly string[],
  paneGroupId: string
): void {
  const needle = `:${splitPanePanelId(paneGroupId)}`;
  for (const key of entryKeys) {
    if (key.includes(needle)) storage.deleteEntry(key);
  }
}
