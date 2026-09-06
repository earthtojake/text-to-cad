import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  emit: vi.fn(),
  listAccounts: vi.fn(),
  logError: vi.fn(),
  startDeviceFlow: vi.fn(),
  telemetryCapture: vi.fn(),
}));

vi.mock('@core/features/github/node', () => ({
  githubEvents: { emit: mocks.emit },
}));

describe('githubController auth', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
  });

  it('returns the registered GitHub account and emits success after device flow registration', async () => {
    const user = {
      id: 42,
      login: 'octocat',
      name: 'Octocat',
      email: '',
      avatar_url: 'https://github.com/octocat.png',
    };
    mocks.startDeviceFlow.mockResolvedValue({
      success: true,
      token: 'gho_device',
      user,
      account: { accountId: 'github.com:42' },
    });
    mocks.listAccounts.mockResolvedValue([
      {
        accountId: 'github.com:42',
        host: 'github.com',
        login: 'octocat',
        avatarUrl: 'https://github.com/octocat.png',
        credentialSource: 'device_flow',
        isDefault: true,
      },
    ]);

    const { createGithubOperations } = await import('./controller');
    const githubController = createGithubOperations({
      accountService: {
        listAccounts: mocks.listAccounts,
        importCliAccounts: vi.fn(),
        removeAccount: vi.fn(),
        setDefaultAccount: vi.fn(),
      } as never,
      deviceFlowService: {
        start: mocks.startDeviceFlow,
        cancelAuth: vi.fn(),
        cancel: vi.fn(),
      } as never,
      logger: { error: mocks.logError } as never,
      repositoryService: {} as never,
      telemetry: { capture: mocks.telemetryCapture } as never,
    });

    await expect(githubController.auth()).resolves.toEqual({
      success: true,
      account: {
        accountId: 'github.com:42',
        host: 'github.com',
        login: 'octocat',
        avatarUrl: 'https://github.com/octocat.png',
        credentialSource: 'device_flow',
        isDefault: true,
      },
    });
    expect(mocks.emit).toHaveBeenCalledWith(undefined, {
      type: 'auth-success',
      user,
    });
    expect(mocks.telemetryCapture).toHaveBeenCalledWith('integration_connected', {
      provider: 'github',
    });
  });

  it('returns failure and does not emit success when device flow cannot register an account', async () => {
    mocks.startDeviceFlow.mockResolvedValue({
      success: true,
      token: 'gho_device',
      user: {
        id: 42,
        login: 'octocat',
        name: 'Octocat',
        email: '',
        avatar_url: 'https://github.com/octocat.png',
      },
      account: { accountId: 'github.com:42' },
    });
    mocks.listAccounts.mockResolvedValue([]);

    const { createGithubOperations } = await import('./controller');
    const githubController = createGithubOperations({
      accountService: { listAccounts: mocks.listAccounts } as never,
      deviceFlowService: { start: mocks.startDeviceFlow } as never,
      logger: { error: mocks.logError } as never,
      repositoryService: {} as never,
      telemetry: { capture: mocks.telemetryCapture } as never,
    });

    await expect(githubController.auth()).resolves.toEqual({
      success: false,
      error: 'Failed to register GitHub account',
    });
    expect(mocks.emit).toHaveBeenCalledWith(undefined, {
      type: 'auth-error',
      error: 'account_registration_failed',
      message: 'Failed to register GitHub account',
    });
    expect(mocks.telemetryCapture).not.toHaveBeenCalled();
  });

  it('reports account registration failure when registration throws after device flow succeeds', async () => {
    mocks.startDeviceFlow.mockResolvedValue({
      success: true,
      token: 'gho_device',
      user: {
        id: 42,
        login: 'octocat',
        name: 'Octocat',
        email: '',
        avatar_url: 'https://github.com/octocat.png',
      },
      account: { accountId: 'github.com:42' },
    });
    mocks.listAccounts.mockRejectedValue(new Error('secure storage failed'));

    const { createGithubOperations } = await import('./controller');
    const githubController = createGithubOperations({
      accountService: { listAccounts: mocks.listAccounts } as never,
      deviceFlowService: { start: mocks.startDeviceFlow } as never,
      logger: { error: mocks.logError } as never,
      repositoryService: {} as never,
      telemetry: { capture: mocks.telemetryCapture } as never,
    });

    await expect(githubController.auth()).resolves.toEqual({
      success: false,
      error: 'Failed to register GitHub account',
    });
    expect(mocks.emit).toHaveBeenCalledWith(undefined, {
      type: 'auth-error',
      error: 'account_registration_failed',
      message: 'Failed to register GitHub account',
    });
    expect(mocks.telemetryCapture).not.toHaveBeenCalled();
  });
});
