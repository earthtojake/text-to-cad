import { join } from 'node:path';
import { app } from 'electron';
import { desktopWorkers, type DesktopWorkerId } from '@core/manifests/node/workers';

export function desktopWorkerPath(id: DesktopWorkerId): string {
  // app.getAppPath() is stable regardless of which output chunk this module is
  // bundled into. import.meta.url would resolve to out/main/chunks/ after code
  // splitting and miss the sibling runtime files at out/main/.
  //
  // In test environments, app may be a partial mock without getAppPath; fall
  // back to process.cwd() which resolves to apps/emdash-desktop/ in vitest
  // — the same root app.getAppPath() returns at runtime.
  const appPath = typeof app?.getAppPath === 'function' ? app.getAppPath() : process.cwd();
  return join(appPath, 'out', 'main', desktopWorkers[id].file);
}
