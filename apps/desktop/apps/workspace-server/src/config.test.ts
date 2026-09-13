import type { Result } from '@emdash/shared';
import { describe, expect, it } from 'vitest';
import {
  loadWorkspaceServerConfig,
  type WorkspaceServerConfig,
  type WorkspaceServerConfigError,
} from './config';

describe('loadWorkspaceServerConfig', () => {
  it('defaults to the serve command over stdio', () => {
    const config = expectLoaded(loadWorkspaceServerConfig([], {}));

    expect(config).toEqual({
      command: 'serve',
      appVersion: '0.0.0',
      serve: { kind: 'stdio' },
    });
  });

  it('preserves legacy socket serving args', () => {
    const config = expectLoaded(loadWorkspaceServerConfig(['--socket', '/tmp/workspace.sock'], {}));

    expect(config).toEqual({
      command: 'serve',
      appVersion: '0.0.0',
      serve: { kind: 'socket', path: '/tmp/workspace.sock' },
    });
  });

  it('defaults lifecycle commands to socket mode', () => {
    const config = expectLoaded(loadWorkspaceServerConfig(['start'], {}));

    expect(config).toEqual({
      command: 'start',
      appVersion: '0.0.0',
      serve: { kind: 'socket', path: undefined },
    });
  });

  it('rejects unknown commands', () => {
    const result = loadWorkspaceServerConfig(['restart'], {});

    expect(result).toMatchObject({
      success: false,
      error: {
        type: 'args',
        message: "Unknown command 'restart'",
      },
    });
  });

  it('rejects stdio for lifecycle commands', () => {
    const result = loadWorkspaceServerConfig(['status', '--stdio'], {});

    expect(result).toMatchObject({
      success: false,
      error: {
        type: 'args',
        message: 'status only supports socket mode',
      },
    });
  });
});

function expectLoaded(
  result: Result<WorkspaceServerConfig, WorkspaceServerConfigError>
): WorkspaceServerConfig {
  if (!result.success) throw new Error(`Expected config to load: ${String(result.error)}`);
  return result.data;
}
