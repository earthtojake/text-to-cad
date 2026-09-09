import type { WorkbenchChatTarget } from './workbench-chat-input-bridge';

export interface WorkbenchChatSubmission {
  conversationId: string;
  text: string;
  messageCountBeforeSubmit: number;
  agentIsWorking: boolean;
}

export type WorkbenchChatSubmissionPreparation =
  | {
      success: true;
      hiddenContext?: string;
      onDispatchFailure?: (
        error: string
      ) => Promise<WorkbenchChatSubmissionRollback> | WorkbenchChatSubmissionRollback;
    }
  | { success: false; error: string };

export type WorkbenchChatSubmissionRollback = { success: true } | { success: false; error: string };

export type WorkbenchChatSubmissionHandler = (
  submission: WorkbenchChatSubmission
) => Promise<WorkbenchChatSubmissionPreparation>;

interface RegisteredHandler {
  token: symbol;
  handler: WorkbenchChatSubmissionHandler;
}

const handlers = new Map<string, RegisteredHandler>();

function targetKey(target: WorkbenchChatTarget): string {
  return `${target.projectId}\u0000${target.taskId}`;
}

/**
 * Lets an active artifact contribute prompt context and own its mutation lifecycle
 * without teaching the shared ACP composer about that artifact type.
 */
export function registerWorkbenchChatSubmissionHandler(
  target: WorkbenchChatTarget,
  handler: WorkbenchChatSubmissionHandler
): () => void {
  const key = targetKey(target);
  const token = Symbol(key);
  handlers.set(key, { token, handler });
  return () => {
    if (handlers.get(key)?.token === token) handlers.delete(key);
  };
}

export async function prepareWorkbenchChatSubmission(
  target: WorkbenchChatTarget,
  submission: WorkbenchChatSubmission
): Promise<WorkbenchChatSubmissionPreparation> {
  const registered = handlers.get(targetKey(target));
  return registered
    ? registered.handler(submission)
    : {
        success: false,
        error: 'The engineering artifact lifecycle is not ready. Wait a moment and try again.',
      };
}

export function combineWorkbenchHiddenContext(
  ...contexts: Array<string | null | undefined>
): string | undefined {
  const values = contexts
    .map((context) => context?.trim())
    .filter((context): context is string => !!context);
  return values.length > 0 ? values.join('\n\n') : undefined;
}

/** Test-only reset for this renderer-local bridge. */
export function resetWorkbenchChatSubmissionBridgeForTests(): void {
  handlers.clear();
}
