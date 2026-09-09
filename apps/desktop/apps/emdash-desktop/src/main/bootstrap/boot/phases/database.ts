import type Database from 'better-sqlite3';
import { resetStaleAcpAgentStatuses } from '@core/features/conversations/node/reset-stale-acp-agent-statuses';
import { resetStaleTuiAgentStatuses } from '@core/features/conversations/node/reset-stale-tui-agent-statuses';
import {
  createEditorBufferService,
  editorBufferDatabasePath,
  type EditorBufferService,
} from '@core/features/editor/node/editor-buffer-service';
import type { WorkspaceIdentityService } from '@core/features/workspaces/api/node/workspace-identity-service';
import { createWorkspaceIdentityService } from '@core/features/workspaces/node/workspace-identity-source';
import { appSettingsContributions } from '@core/manifests/node/settings-contributions';
import type { AppDb } from '@core/services/app-db/node/db';
import { createAppSettingsService, type AppSettingsService } from '@core/services/settings/node';
import { createDrizzleClient } from '@main/db/drizzleClient';
import { initializeDatabase } from '@main/db/initialize';
import { closeAppDb, setAppDb } from '@main/db/instance';
import { resolveDatabasePath } from '@main/db/path';
import { cleanupLegacyBrowserPartitions } from '@main/host/browser/browser-partition-cleanup';
import { log } from '@main/lib/logger';
import { runInBackground } from '../../core/background';
import type { AppConfig } from '../../core/config';
import { step } from '../../core/phase';
import { setWorkspaceIdentityService } from '../../core/service-instances';

export type DatabaseBundle = {
  readonly appSettings: AppSettingsService;
  readonly db: AppDb;
  readonly editorBuffer: EditorBufferService;
  readonly sqlite: Database.Database;
  readonly workspaceIdentity: WorkspaceIdentityService;
};

export async function bootDatabase(config: AppConfig): Promise<DatabaseBundle> {
  if (config.forceBootFailure) {
    throw new Error('Boot failure forced by EMDASH_FORCE_BOOT_FAILURE=1');
  }

  const client = createDrizzleClient();
  let published = false;
  let editorBuffer: EditorBufferService | undefined;
  try {
    await step('db-initialize', () => initializeDatabase(client.sqlite));
    setAppDb(client);
    published = true;
    const workspaceIdentity = createWorkspaceIdentityService({ db: client.db });
    // Crash-recovery buffers live in their own derived SQLite store beside the
    // app database; it is opened here but never touches the Drizzle migrations.
    editorBuffer = createEditorBufferService({
      databasePath: editorBufferDatabasePath(resolveDatabasePath()),
      logger: log,
    });
    const appSettings = createAppSettingsService({
      db: client.db,
      contributions: appSettingsContributions,
    });
    setWorkspaceIdentityService(workspaceIdentity);
    const buffer = editorBuffer;
    await step('db-startup-repairs', () => runStartupRepairs(client.db, buffer));
    return {
      appSettings,
      db: client.db,
      editorBuffer,
      sqlite: client.sqlite,
      workspaceIdentity,
    };
  } catch (error) {
    try {
      editorBuffer?.dispose();
    } finally {
      if (published) closeAppDb();
      else client.close();
    }
    throw error;
  }
}

async function runStartupRepairs(db: AppDb, editorBuffer: EditorBufferService): Promise<void> {
  await resetStaleAcpAgentStatuses(db);
  await resetStaleTuiAgentStatuses(db);

  runInBackground('editor-buffer-prune', () => editorBuffer.pruneStale(), {
    onError: (error) => log.warn('Failed to prune stale editor buffers', { error }),
  });
  runInBackground('browser-partition-cleanup', cleanupLegacyBrowserPartitions, {
    onError: (error) => log.warn('Failed to clean legacy browser partitions', { error }),
  });
}
