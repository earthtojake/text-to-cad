/**
 * The message the renderer shows for a failed invoke.
 *
 * Electron wraps a rejected `ipcMain.handle` as
 * `Error invoking remote method 'text-to-cad:sessions.create': IpcError: <message>`;
 * the handler's own words are the part worth showing.
 */
export function errorMessage(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error);
  return raw.replace(/^Error invoking remote method '[^']*': (?:\w*Error: )?/, "").trim();
}

/**
 * What a `sessions.create` rejects with when the person deleted the session
 * while it was still starting. Not a failure to show: the renderer swallows it
 * (`isDeletedWhileStarting`) rather than put a card or a toast up for a thread
 * that is gone on purpose.
 */
export const DELETED_WHILE_STARTING = "This session was deleted while it was starting.";

export const isDeletedWhileStarting = (message: string): boolean => message === DELETED_WHILE_STARTING;
