import { describe, expect, it, vi } from 'vitest';
import { DesktopProjectSettingsAuthority } from './durable-project-settings';
import type { ProjectSettingsStorage, StoredProjectSettings } from './project-settings-storage';

describe('DesktopProjectSettingsAuthority', () => {
  it('reads and patches desktop-owned settings without a Project Provider', async () => {
    const row: StoredProjectSettings = {
      baseProjectSettingsJson: JSON.stringify({
        worktreeRoot: '/tmp/worktrees',
        baseRemote: 'origin',
        tmux: true,
      }),
      shareableProjectSettingsJson: '{}',
      legacyConfigMigratedAt: null,
    };
    const storage: ProjectSettingsStorage = {
      get: vi.fn(async () => row),
      insertIfMissing: vi.fn(),
      update: vi.fn(async (_projectId, patch) => {
        Object.assign(row, patch);
      }),
    };
    const authority = new DesktopProjectSettingsAuthority(storage);

    await expect(authority.read('project-1')).resolves.toMatchObject({
      success: true,
      data: {
        gitIdentity: { stored: { baseRemote: 'origin' } },
        placement: { stored: { worktreeRoot: '/tmp/worktrees', tmux: true } },
      },
    });

    await expect(
      authority.patch('project-1', {
        gitIdentity: { stored: { pushRemote: 'fork', baseRemote: null } },
        placement: { stored: { tmux: false } },
      })
    ).resolves.toEqual({ success: true, data: undefined });

    expect(JSON.parse(row.baseProjectSettingsJson)).toMatchObject({
      worktreeRoot: '/tmp/worktrees',
      pushRemote: 'fork',
      tmux: false,
    });
    expect(JSON.parse(row.baseProjectSettingsJson)).not.toHaveProperty('baseRemote');
  });

  it('does not preserve migration-only lifecycle settings during a durable patch', async () => {
    const shareable = JSON.stringify({
      preservePatterns: ['.env.local'],
      scripts: { setup: 'pnpm install' },
    });
    const row: StoredProjectSettings = {
      baseProjectSettingsJson: JSON.stringify({
        baseRemote: 'origin',
        autoRunSetupScriptOnTaskCreation: false,
        autoRunRunScriptOnTaskCreation: true,
      }),
      shareableProjectSettingsJson: shareable,
      legacyConfigMigratedAt: null,
    };
    const storage: ProjectSettingsStorage = {
      get: vi.fn(async () => row),
      insertIfMissing: vi.fn(),
      update: vi.fn(async (_projectId, patch) => {
        Object.assign(row, patch);
      }),
    };
    const authority = new DesktopProjectSettingsAuthority(storage);

    await authority.patch('project-1', {
      gitIdentity: { stored: { pushRemote: 'fork' } },
    });

    expect(JSON.parse(row.baseProjectSettingsJson)).toEqual({
      baseRemote: 'origin',
      pushRemote: 'fork',
    });
    expect(row.shareableProjectSettingsJson).toBe(shareable);
  });
});
