import { existsSync, rmSync } from 'node:fs';
import { resolveDatabasePath } from './path';

/**
 * Best-effort removal of the retired operations-kernel SQLite store (ADR 0006
 * demolition). Older builds kept a `<app-db>-operations.db` next to the app
 * database; nothing reads or writes it anymore, so orphaned files (and their WAL
 * sidecars) are deleted on startup. Failures are logged and never fatal.
 */
export function cleanupLegacyOperationsDatabases(log: {
  info(message: string, metadata?: Record<string, unknown>): void;
  warn(message: string, metadata?: Record<string, unknown>): void;
}): void {
  const appDbPath = resolveDatabasePath();
  const basePath = appDbPath.endsWith('.db')
    ? appDbPath.replace(/\.db$/, '-operations.db')
    : `${appDbPath}-operations.db`;
  for (const path of [basePath, `${basePath}-wal`, `${basePath}-shm`]) {
    try {
      if (!existsSync(path)) continue;
      rmSync(path, { force: true });
      log.info('Removed orphaned operations database file', { path });
    } catch (error) {
      log.warn('Failed to remove orphaned operations database file', {
        path,
        error: String(error),
      });
    }
  }
}
