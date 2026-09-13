import type { AgentAuthContext } from '@emdash/core/services/agent-plugins/api/plugins';
import { describe, expect, it, vi } from 'vitest';
import { claudeAuthStatus } from './auth';

function ctx(overrides: Partial<AgentAuthContext> = {}): AgentAuthContext {
  return {
    cli: 'claude',
    env: {},
    exec: vi.fn().mockResolvedValue({ stdout: '', stderr: '' }),
    fs: {
      read: vi.fn(),
      write: vi.fn(),
      delete: vi.fn(),
      exists: vi.fn(),
      list: vi.fn(),
    },
    ...overrides,
  };
}

describe('claudeAuthStatus', () => {
  it('reports authenticated from ANTHROPIC_API_KEY without probing the CLI', async () => {
    const exec = vi.fn();

    await expect(
      claudeAuthStatus(ctx({ env: { ANTHROPIC_API_KEY: 'test-key' }, exec }))
    ).resolves.toEqual({ kind: 'authenticated' });
    expect(exec).not.toHaveBeenCalled();
  });

  it('reports authenticated and extracts the email from claude auth status JSON', async () => {
    const exec = vi.fn().mockResolvedValue({
      stdout: JSON.stringify({
        loggedIn: true,
        authMethod: 'oauth',
        email: 'user@example.com',
      }),
      stderr: '',
    });

    await expect(claudeAuthStatus(ctx({ exec }))).resolves.toEqual({
      kind: 'authenticated',
      account: 'user@example.com',
    });
    expect(exec).toHaveBeenCalledWith('claude', ['auth', 'status'], { timeout: 5000 });
  });

  it('reports unauthenticated when claude auth status exits 1 with status JSON', async () => {
    const exec = vi.fn().mockRejectedValue({
      code: 1,
      stdout: JSON.stringify({ loggedIn: false }),
      stderr: '',
      message: 'Command failed: claude auth status\n',
    });

    await expect(claudeAuthStatus(ctx({ exec }))).resolves.toEqual({ kind: 'unauthenticated' });
  });

  it('reports unknown when an older CLI does not recognize the auth status command', async () => {
    const exec = vi.fn().mockRejectedValue({
      code: 1,
      stdout: '',
      stderr: "error: unknown command 'auth'",
    });

    await expect(claudeAuthStatus(ctx({ exec }))).resolves.toEqual({ kind: 'unknown' });
  });
});
