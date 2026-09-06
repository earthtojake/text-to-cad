/**
 * The message the renderer shows for a failed invoke.
 *
 * Electron wraps a rejected `ipcMain.handle` as
 * `Error invoking remote method 'hardcore:sessions.create': IpcError: <message>`;
 * the handler's own words are the part worth showing.
 */
export function errorMessage(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error);
  return raw.replace(/^Error invoking remote method '[^']*': (?:\w*Error: )?/, "").trim();
}
