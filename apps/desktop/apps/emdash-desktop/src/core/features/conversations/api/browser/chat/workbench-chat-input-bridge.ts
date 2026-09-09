export interface WorkbenchChatTarget {
  projectId: string;
  taskId: string;
}

export type WorkbenchChatInput =
  | {
      kind: 'reference';
      reference: string;
    }
  | {
      kind: 'image';
      dataUrl: string;
      mimeType: 'image/png';
      name: string;
    };

export type WorkbenchChatInputHandler = (input: WorkbenchChatInput) => boolean | Promise<boolean>;

const handlers = new Map<string, WorkbenchChatInputHandler[]>();

function targetKey(target: WorkbenchChatTarget): string {
  return `${target.projectId}\u0000${target.taskId}`;
}

/**
 * Connects task-scoped artifact actions to the currently visible workbench composer.
 *
 * The most recently mounted matching composer gets first refusal. This keeps CAD
 * tools independent from ACP internals while still behaving predictably if a task
 * temporarily has more than one chat pane during a layout transition.
 */
export function subscribeWorkbenchChatInput(
  target: WorkbenchChatTarget,
  handler: WorkbenchChatInputHandler
): () => void {
  const key = targetKey(target);
  const current = handlers.get(key) ?? [];
  handlers.set(key, [...current, handler]);
  return () => {
    const next = (handlers.get(key) ?? []).filter((candidate) => candidate !== handler);
    if (next.length > 0) handlers.set(key, next);
    else handlers.delete(key);
  };
}

export async function publishWorkbenchChatInput(
  target: WorkbenchChatTarget,
  input: WorkbenchChatInput
): Promise<boolean> {
  const current = [...(handlers.get(targetKey(target)) ?? [])].reverse();
  for (const handler of current) {
    if (await handler(input)) return true;
  }
  return false;
}

export function hasWorkbenchChatInputSubscriber(target: WorkbenchChatTarget): boolean {
  return (handlers.get(targetKey(target))?.length ?? 0) > 0;
}

export function appendWorkbenchChatReference(draft: string, reference: string): string {
  const normalized = reference.trim();
  if (!normalized || draft.includes(normalized)) return draft;
  const separator = draft.length > 0 && !/\s$/.test(draft) ? ' ' : '';
  return `${draft}${separator}${normalized} `;
}

export function imageBytesFromDataUrl(dataUrl: string, mimeType: 'image/png'): Uint8Array | null {
  const prefix = `data:${mimeType};base64,`;
  if (!dataUrl.startsWith(prefix)) return null;
  try {
    const binary = atob(dataUrl.slice(prefix.length));
    return Uint8Array.from(binary, (character) => character.charCodeAt(0));
  } catch {
    return null;
  }
}

/** Test-only reset for this renderer-local event bridge. */
export function resetWorkbenchChatInputBridgeForTests(): void {
  handlers.clear();
}
