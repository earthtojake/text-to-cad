import { err, ok } from '@emdash/shared';
import { describe, expect, it } from 'vitest';
import { GitHubRepositoryResolver } from '@core/features/github/api/node/services/github-repository-resolver';
import type { HostProbeResult } from './github-host-service';

class FakeHostService {
  readonly calls: string[] = [];

  constructor(private readonly results: Record<string, HostProbeResult>) {}

  async probe(host: string): Promise<HostProbeResult> {
    this.calls.push(host);
    return this.results[host] ?? err({ type: 'not_github', host });
  }
}

describe('GitHubRepositoryResolver', () => {
  it('resolves GitHub.com remotes through the host service', async () => {
    const hostService = new FakeHostService({ 'github.com': ok({ host: 'github.com' }) });
    const resolver = new GitHubRepositoryResolver(hostService);

    await expect(resolver.resolve('git@github.com:owner/repo.git')).resolves.toEqual({
      success: true,
      data: {
        host: 'github.com',
        owner: 'owner',
        repo: 'repo',
        nameWithOwner: 'owner/repo',
        repositoryUrl: 'https://github.com/owner/repo',
      },
    });
    expect(hostService.calls).toEqual(['github.com']);
  });

  it('resolves compatible GHES hosts', async () => {
    const hostService = new FakeHostService({ 'ghe.example.com': ok({ host: 'ghe.example.com' }) });
    const resolver = new GitHubRepositoryResolver(hostService);

    await expect(resolver.resolve('https://ghe.example.com/owner/repo')).resolves.toMatchObject({
      success: true,
      data: {
        host: 'ghe.example.com',
        repositoryUrl: 'https://ghe.example.com/owner/repo',
      },
    });
  });

  it('does not treat structurally parseable non-GitHub hosts as GitHub', async () => {
    const hostService = new FakeHostService({
      'gitlab.com': err({ type: 'not_github', host: 'gitlab.com', reason: 'not GHES' }),
    });
    const resolver = new GitHubRepositoryResolver(hostService);

    await expect(resolver.resolve('https://gitlab.com/owner/repo')).resolves.toEqual({
      success: false,
      error: {
        type: 'not_github',
        host: 'gitlab.com',
        reason: 'not GHES',
      },
    });
  });

  it('preserves host probe failure reasons', async () => {
    const hostService = new FakeHostService({
      'ghe.example.com': err({
        type: 'host_unreachable',
        host: 'ghe.example.com',
        reason: 'VPN disconnected',
      }),
    });
    const resolver = new GitHubRepositoryResolver(hostService);

    await expect(resolver.resolve('https://ghe.example.com/owner/repo')).resolves.toEqual({
      success: false,
      error: {
        type: 'host_unreachable',
        host: 'ghe.example.com',
        reason: 'VPN disconnected',
      },
    });
  });
});
