import { hostRef, LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import type { Logger } from '@emdash/shared/logger';
import { describe, expect, it, vi } from 'vitest';
import type { GitHubAccountSummary } from '@core/primitives/github/api';
import type { AgentGitCredentialsSetting, Resolved } from '@core/primitives/project-settings/api';
import { createGitCredentialsService } from './git-credentials-service';

const account: GitHubAccountSummary = {
  accountId: 'account-1',
  host: 'GitHub.com',
  login: 'octocat',
  avatarUrl: 'https://example.invalid/a.png',
  credentialSource: 'emdash_oauth',
  isDefault: true,
};

const REMOTE_HOST = hostRef('remote', 'ssh-1');

function makeService(
  options: {
    setting?: AgentGitCredentialsSetting;
    resolution?: Resolved<GitHubAccountSummary | null>;
    accounts?: GitHubAccountSummary[];
  } = {}
) {
  const mintSession = vi.fn(async () => ({ port: 45678, nonce: 'nonce-1' }));
  const revokeSession = vi.fn();
  const logger = { info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() };
  const service = createGitCredentialsService({
    getAgentGitCredentialsSetting: async () => options.setting ?? 'effective-account',
    resolveProjectGitHubAccount: async () =>
      options.resolution ?? { value: account, provenance: { kind: 'set' } },
    listAccounts: async () => options.accounts ?? [account],
    channels: { mintSession, revokeSession },
    logger: logger as unknown as Logger,
  });
  return { service, mintSession, revokeSession, logger };
}

describe('resolveSessionSpec', () => {
  it('maps the effective-account setting to a channel-backed spec with the account host', async () => {
    const { service, mintSession } = makeService();
    const spec = await service.resolveSessionSpec({ projectId: 'p1', host: LOCAL_HOST_REF });
    expect(spec).toEqual({
      mode: 'effective-account',
      channel: { port: 45678, nonce: 'nonce-1' },
      hosts: ['github.com'],
    });
    expect(mintSession).toHaveBeenCalledWith({ kind: 'project', projectId: 'p1' });
  });

  it('maps system and none settings without minting a channel', async () => {
    const system = makeService({ setting: 'system' });
    await expect(
      system.service.resolveSessionSpec({ projectId: 'p1', host: LOCAL_HOST_REF })
    ).resolves.toEqual({ mode: 'system' });
    expect(system.mintSession).not.toHaveBeenCalled();

    const none = makeService({ setting: 'none' });
    await expect(
      none.service.resolveSessionSpec({ projectId: 'p1', host: REMOTE_HOST })
    ).resolves.toEqual({ mode: 'none' });
    expect(none.mintSession).not.toHaveBeenCalled();
  });

  it('skips the helper on remote hosts (loopback unreachable)', async () => {
    const { service, mintSession } = makeService();
    await expect(
      service.resolveSessionSpec({ projectId: 'p1', host: REMOTE_HOST })
    ).resolves.toBeUndefined();
    expect(mintSession).not.toHaveBeenCalled();
  });

  it('fails closed to native behavior on an unresolvable account pin', async () => {
    const { service, mintSession, logger } = makeService({
      resolution: { value: null, provenance: { kind: 'unresolvable' } },
    });
    await expect(
      service.resolveSessionSpec({ projectId: 'p1', host: LOCAL_HOST_REF })
    ).resolves.toBeUndefined();
    expect(mintSession).not.toHaveBeenCalled();
    expect(logger.warn).toHaveBeenCalled();
  });
});

describe('mintOperationCredentials', () => {
  it('leases a project-scoped channel and revokes it on release', async () => {
    const { service, revokeSession } = makeService();
    const lease = await service.mintOperationCredentials({ projectId: 'p1', host: LOCAL_HOST_REF });
    expect(lease?.credentials).toEqual({ port: 45678, nonce: 'nonce-1', host: 'github.com' });
    lease?.release();
    expect(revokeSession).toHaveBeenCalledWith('nonce-1');
  });

  it('returns nothing on remote hosts or when no account resolves', async () => {
    const remote = makeService();
    await expect(
      remote.service.mintOperationCredentials({ projectId: 'p1', host: REMOTE_HOST })
    ).resolves.toBeUndefined();

    const noAccount = makeService({
      resolution: { value: null, provenance: { kind: 'inferred', from: 'none' } },
    });
    await expect(
      noAccount.service.mintOperationCredentials({ projectId: 'p1', host: LOCAL_HOST_REF })
    ).resolves.toBeUndefined();
  });
});

describe('mintCloneCredentials', () => {
  it('leases a host-scoped channel for an https URL with a matching account', async () => {
    const { service, mintSession, revokeSession } = makeService();
    const lease = await service.mintCloneCredentials({
      repositoryUrl: 'https://github.com/org/repo.git',
      host: LOCAL_HOST_REF,
    });
    expect(lease?.credentials).toEqual({ port: 45678, nonce: 'nonce-1', host: 'github.com' });
    expect(mintSession).toHaveBeenCalledWith({ kind: 'host', host: 'github.com' });
    lease?.release();
    expect(revokeSession).toHaveBeenCalledWith('nonce-1');
  });

  it('leaves ssh clones and unmatched hosts on native behavior', async () => {
    const { service, mintSession } = makeService();
    await expect(
      service.mintCloneCredentials({
        repositoryUrl: 'git@github.com:org/repo.git',
        host: LOCAL_HOST_REF,
      })
    ).resolves.toBeUndefined();
    await expect(
      service.mintCloneCredentials({
        repositoryUrl: 'https://gitlab.example.com/org/repo.git',
        host: LOCAL_HOST_REF,
      })
    ).resolves.toBeUndefined();
    expect(mintSession).not.toHaveBeenCalled();
  });
});
