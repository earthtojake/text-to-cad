import type { TabViewContext } from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider';

/**
 * The task-specific tab context passed to PaneLayoutStore/PaneStore when a
 * task view is created. Extends the generic TabViewContext with the domain
 * fields that task-scoped providers (conversation, file, diff, browser)
 * need to operate.
 *
 * Providers receive TabViewContext at their boundaries and cast to
 * TaskTabContext to access the domain fields:
 *
 *   const taskCtx = ctx as TaskTabContext;
 *   conversationRegistry.get(taskCtx.taskId);
 */
export interface TaskTabContext extends TabViewContext {
  projectId: string;
  workspaceId: string;
  taskId: string;
  workspacePath?: string;
  /** Current remote connection for terminal/file-drop helpers, when this task is remote. */
  getRemoteConnectionId?: () => string | undefined;
}
