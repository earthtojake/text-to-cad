import { fileURLToPath } from 'node:url';
import { workspaceWorkers, type WorkspaceWorkerId } from './worker-manifest';

export function workspaceWorkerPath(id: WorkspaceWorkerId): string {
  return fileURLToPath(new URL(`./${workspaceWorkers[id].file}`, import.meta.url));
}
