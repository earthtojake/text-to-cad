import { openRegistryFixture, type RegistryFixture } from '@tooling/utils/provider-accounts';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { GitHubEvent, GitHubUser } from '@core/primitives/github/api';
import { GITHUB_PROVIDER_ID } from '../accounts/github-accounts';
import { GitHubDeviceFlowService } from './github-device-flow-service';

const user: GitHubUser = {
  id: 42,
  login: 'monalisa',
  name: 'Mona Lisa',
  email: '',
  avatar_url: 'https://avatars.githubusercontent.com/u/42',
};

describe('GitHubDeviceFlowService', () => {
  let fixture: RegistryFixture;
  let getAuthenticatedUser: (token: string, host?: string) => Promise<GitHubUser | null>;
  let emit: (event: GitHubEvent) => void;

  beforeEach(async () => {
    fixture = await openRegistryFixture('empty');
    getAuthenticatedUser = vi.fn(async () => user);
    emit = vi.fn();
  });

  afterEach(() => {
    fixture?.close();
  });

  it('registers a device-flow account in the registry', async () => {
    const service = new GitHubDeviceFlowService({
      accountStore: fixture.registry,
      identityClient: { getAuthenticatedUser },
      publishEvent: emit,
      createDeviceAuth: () => async () => ({ token: 'gho_device' }),
      config: { clientId: 'client-id', scopes: ['repo'] },
    });

    await expect(service.start()).resolves.toMatchObject({
      success: true,
      user,
      account: {
        accountId: 'github.com:42',
        credentialSource: 'device_flow',
      },
    });
    await expect(fixture.registry.resolveSecret(GITHUB_PROVIDER_ID, 'github.com:42')).resolves.toBe(
      'gho_device'
    );
  });

  it('returns an error when the device-flow token cannot identify a user', async () => {
    getAuthenticatedUser = vi.fn(async () => null);
    const service = new GitHubDeviceFlowService({
      accountStore: fixture.registry,
      identityClient: { getAuthenticatedUser },
      publishEvent: emit,
      createDeviceAuth: () => async () => ({ token: 'gho_device' }),
      config: { clientId: 'client-id', scopes: ['repo'] },
    });

    await expect(service.start()).resolves.toEqual({
      success: false,
      error: 'Failed to read authenticated GitHub user',
    });
    await expect(fixture.registry.listAccounts(GITHUB_PROVIDER_ID)).resolves.toEqual([]);
  });
});
