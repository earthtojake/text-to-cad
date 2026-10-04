import type { ClipboardPort } from '@text-to-cad/ui/host';
import type { FileActions } from '@text-to-cad/ui/file-viewer';
import { createCadFileActions } from '@text-to-cad/ui/catalog';
import type { CadServerInfo } from '@text-to-cad/core/client';

/**
 * The file menu's host actions in this Viewer: the file's path to the clipboard, and — where the
 * server advertises it — the file shown in the file manager of the machine the server runs on,
 * through its guarded `POST /__cad/reveal`. The menu labels Finder, Explorer or the file manager by
 * the server's platform.
 */
export function createWebFileActions(server: CadServerInfo, { clipboard }: { clipboard: ClipboardPort }): FileActions {
  const platform = server.platform === 'darwin' || server.platform === 'win32' || server.platform === 'linux' ? server.platform
    : navigator.userAgent.includes('Macintosh') ? 'darwin' : navigator.userAgent.includes('Windows') ? 'win32' : 'linux';
  const reveals = Array.isArray(server.serverFeatures) && server.serverFeatures.includes('reveal-path');
  return createCadFileActions({
    platform, clipboard,
    reveal: reveals ? async (path) => {
      const response = await fetch('/__cad/reveal', { method: 'POST',
        headers: { 'x-cadgen-viewer': '1', 'content-type': 'application/json' },
        body: JSON.stringify({ path }) });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        throw new Error(detail?.error || 'Could not reveal this file in the file manager.');
      }
    } : undefined,
  });
}
