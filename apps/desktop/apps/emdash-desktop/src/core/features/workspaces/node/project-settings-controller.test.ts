import { ok } from '@emdash/shared';
import { describe, expect, it, vi } from 'vitest';
import { createProjectSettingsOperations } from './project-settings-controller';

describe('workspace project settings', () => {
  it('serves the registry-resolved workspace lifecycle config to the Scripts tab', async () => {
    const getProjectConfig = vi.fn(async () =>
      ok({
        resolved: {
          setup: { value: 'personal setup', from: 'personal' },
          run: { value: 'team run', from: 'team' },
          shellSetup: { value: 'host shell', from: 'host-default' },
          autoRunSetup: { value: true, from: 'built-in' },
          autoRunRun: { value: false, from: 'built-in' },
        },
      })
    );
    const operations = createProjectSettingsOperations({
      runtimes: {
        client: vi.fn(async () =>
          ok({ workspaceRegistry: { getProjectConfig }, files: {} } as never)
        ),
      } as never,
      workspaceIdentity: {
        resolve: vi.fn(async () => ({
          workspaceId: 'ws-1',
          projectId: 'project-1',
          path: '/workspace',
          host: { type: 'local' },
        })) as never,
      },
    });

    await expect(operations.getSettings('ws-1')).resolves.toEqual(
      ok({
        scripts: { setup: 'personal setup', run: 'team run' },
        shellSetup: 'host shell',
      })
    );
    expect(getProjectConfig).toHaveBeenCalledWith({ workspaceId: 'ws-1' });
  });
});
