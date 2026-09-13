import type { HostFileRef } from '@emdash/core/primitives/path/api';
import { isCadFilePath } from '@core/features/cad/api/browser/cad-file';
import { taskViewDef } from '@core/features/tasks/contributions/views';
import { nativePathFromHost } from '@core/primitives/desktop-runtime/api';
import { getNavigation } from '@core/primitives/navigation/browser/navigation-selectors';
import { focusTracker } from '@core/primitives/telemetry/browser/focus-tracker';
import type { OpenTarget } from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider';
import { getTaskComposition } from './task-composition-selectors';

export interface OpenFileContext {
  projectId: string;
  taskId: string;
}

export interface OpenFileOptions {
  /** Task whose composition hosts the tab. Defaults to the focused task view. */
  context?: OpenFileContext;
  /**
   * Pane placement. `artifact` reuses one stable file/CAD pane to the right of
   * the chat instead of splitting again as focus moves between panes.
   */
  target?: 'active' | 'right' | 'artifact';
  /** Open as a preview (italic, replaced-by-next-preview) tab. Defaults to pinned. */
  preview?: boolean;
  /**
   * Also reveal the file in the Files sidebar and move focus to the editor —
   * the "navigate to this file" intent (chat links, command palette). Sidebar
   * clicks leave this off: the tree already shows the file and keeps focus.
   */
  reveal?: boolean;
}

/**
 * The single entry point for opening a project file (spec §10). Routes known
 * CAD formats to the first-class CAD tab and everything else to the editor,
 * while placement stays in the pane/tab-layout machinery. The file tab
 * acquires buffer and disk facets from the app-global
 * OpenFileStore when it mounts, so there is no existence precheck here —
 * missing files open as a tab showing the store's `error(not-found)`
 * placeholder.
 *
 * Returns false when no task composition could be resolved for the context.
 */
export function openFile(ref: HostFileRef, options: OpenFileOptions = {}): boolean {
  const context = options.context ?? focusedTaskContext();
  if (!context) return false;
  const composition = getTaskComposition(context.projectId, context.taskId);
  if (!composition) return false;

  const path = nativePathFromHost(ref.path);
  const kind = isCadFilePath(path) ? 'cad' : 'file';
  const target =
    options.target === 'artifact'
      ? resolveArtifactTarget(composition.paneLayout)
      : (options.target ?? 'active');
  composition.paneLayout.open(kind, { path }, { preview: options.preview ?? false, target });
  if (options.reveal) {
    focusTracker.transition({ mainPanel: 'editor' }, 'panel_switch');
    composition.setFocusedRegion('main');
    composition.revealWorkspaceFile(path);
  }
  return true;
}

function resolveArtifactTarget(
  paneLayout: NonNullable<ReturnType<typeof getTaskComposition>>['paneLayout']
): OpenTarget {
  const artifactGroup = paneLayout.groups.find(({ pane }) =>
    pane.resolvedTabs.some((tab) => tab.kind === 'file' || tab.kind === 'cad')
  );
  if (artifactGroup) return { paneId: artifactGroup.paneId };

  const chatGroup = paneLayout.groups.find(({ pane }) =>
    pane.resolvedTabs.some((tab) => tab.kind === 'acp-chat' || tab.kind === 'conversation')
  );
  if (chatGroup) paneLayout.setActiveGroup(chatGroup.paneId);
  return 'right';
}

function focusedTaskContext(): OpenFileContext | undefined {
  const current = getNavigation().currentRef;
  if (current.viewId !== taskViewDef.id) return undefined;
  const { projectId, taskId } = current.params as { projectId?: string; taskId?: string };
  return projectId && taskId ? { projectId, taskId } : undefined;
}
