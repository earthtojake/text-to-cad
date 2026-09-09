import type { AgentAuthContext } from '@emdash/core/services/agent-plugins/api/plugins';
import { describe, expect, it, vi } from 'vitest';
import { authenticatedFromEnv, commandAuthStatus } from './auth';

function ctx(overrides: Partial<AgentAuthContext> = {}): AgentAuthContext {
  return {
    cli: 'agent',
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

describe('agent auth helpers', () => {
  it('reports authenticated when any requested environment variable is present', () => {
    expect(
      authenticatedFromEnv(ctx({ env: { OPENAI_API_KEY: 'sk-test' } }), ['OPENAI_API_KEY'])
    ).toEqual({ kind: 'authenticated' });
  });

  it('reports unknown when requested environment variables are absent', () => {
    expect(authenticatedFromEnv(ctx(), ['OPENAI_API_KEY'])).toEqual({ kind: 'unknown' });
  });

  it('maps command output to authenticated status', async () => {
    const exec = vi
      .fn()
      .mockResolvedValue({ stdout: 'Authenticated as user@example.com', stderr: '' });

    await expect(
      commandAuthStatus(ctx({ exec }), ['login', 'status'], {
        authenticatedPattern: /authenticated/i,
      })
    ).resolves.toEqual({ kind: 'authenticated' });
  });

  it('maps command errors to unauthenticated status when output matches', async () => {
    const exec = vi.fn().mockRejectedValue({ stderr: 'not logged in' });

    await expect(
      commandAuthStatus(ctx({ exec }), ['login', 'status'], {
        unauthenticatedPattern: /not logged in/i,
      })
    ).resolves.toEqual({ kind: 'unauthenticated' });
  });
});
