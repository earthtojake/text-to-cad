import { describe, expect, it } from 'vitest';
import { WorkspaceRecordStore, type DurableWorkspaceRecord } from './record-store';
import { workspaceRegistryStore } from './store';

function repositoryRecord(): DurableWorkspaceRecord {
  return {
    id: 'repo-1',
    kind: 'repository',
    path: '/tmp/repo-1',
    parentId: null,
    origin: 'registered',
    gitAdminName: null,
    observedStatus: 'present',
    creation: null,
    lastCreateOutcome: null,
    lifecycle: null,
    lastRemovalAttempt: null,
    git: null,
    lastActivatedAt: null,
    createdAt: 1,
    updatedAt: 1,
    lastObservedAt: 1,
  };
}

describe('workspace registry settings persistence', () => {
  it('applies the fresh personal-config migration and round-trips its versioned payload', async () => {
    const handle = await workspaceRegistryStore.openTemp();
    try {
      const columns = handle.connection.native
        .prepare('PRAGMA table_info(workspace_records)')
        .all() as Array<{ name: string }>;
      const columnNames = columns.map(({ name }) => name);
      expect(columnNames).toContain('personal_config');
      expect(columnNames).toContain('legacy_desktop_settings_migrated');
      expect(columnNames).not.toContain('config_overlay');

      const records = new WorkspaceRecordStore(handle);
      records.insert(repositoryRecord());
      records.updatePersonalConfig('repo-1', {
        preservePatterns: [],
        scripts: { setup: 'pnpm install' },
        autoRunSetup: false,
      });

      const row = handle.connection.native
        .prepare(
          'SELECT personal_config, legacy_desktop_settings_migrated FROM workspace_records WHERE id = ?'
        )
        .get('repo-1') as {
        personal_config: string;
        legacy_desktop_settings_migrated: number;
      };
      expect(JSON.parse(row.personal_config)).toEqual({
        version: '1',
        value: {
          preservePatterns: [],
          scripts: { setup: 'pnpm install' },
          autoRunSetup: false,
        },
      });
      expect(row.legacy_desktop_settings_migrated).toBe(0);
      expect(records.getPersonalConfig('repo-1')).toEqual({
        preservePatterns: [],
        scripts: { setup: 'pnpm install' },
        autoRunSetup: false,
      });
    } finally {
      handle.close();
    }
  });
});
