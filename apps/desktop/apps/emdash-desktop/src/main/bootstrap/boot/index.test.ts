import { beforeEach, describe, expect, it, vi } from 'vitest';

const bundles = {
  controllers: {},
  database: { editorBuffer: { dispose: vi.fn() } },
  infrastructure: {},
  runtimes: { clients: {} },
  services: {
    projects: {},
    pullRequestsRegistration: {},
  },
};
const mocks = vi.hoisted(() => ({
  appScopeDispose: vi.fn(),
  background: vi.fn(),
  closeAppDb: vi.fn(),
  configureCleanup: vi.fn(),
  configureShutdownClients: vi.fn(),
  controllers: vi.fn(),
  database: vi.fn(),
  gateway: vi.fn(),
  infrastructure: vi.fn(),
  logError: vi.fn(),
  logInfo: vi.fn(),
  logWarn: vi.fn(),
  startUserEnvCapture: vi.fn(),
  runtimes: vi.fn(),
  services: vi.fn(),
}));

vi.mock('@main/lib/logger', () => ({
  log: {
    error: mocks.logError,
    info: mocks.logInfo,
    warn: mocks.logWarn,
  },
}));
vi.mock('@main/lib/userEnv', () => ({
  startUserEnvCapture: mocks.startUserEnvCapture,
}));
vi.mock('@main/db/instance', () => ({
  closeAppDb: mocks.closeAppDb,
}));
vi.mock('../core/app-scope', () => ({
  appScope: { dispose: mocks.appScopeDispose },
}));
vi.mock('../shutdown', () => ({
  configureShutdownRuntimeClients: mocks.configureShutdownClients,
}));
vi.mock('../shutdown/phases', () => ({
  configureQuitCleanupServices: mocks.configureCleanup,
}));
vi.mock('./phases/background', () => ({ bootBackground: mocks.background }));
vi.mock('./phases/controllers', () => ({ bootControllers: mocks.controllers }));
vi.mock('./phases/database', () => ({ bootDatabase: mocks.database }));
vi.mock('./phases/gateway', () => ({ installGateway: mocks.gateway }));
vi.mock('./phases/infrastructure', () => ({ bootInfrastructure: mocks.infrastructure }));
vi.mock('./phases/runtimes', () => ({ bootRuntimes: mocks.runtimes }));
vi.mock('./phases/services', () => ({ bootServices: mocks.services }));

import { finishBoot } from './index';

describe('finishBoot', () => {
  beforeEach(() => {
    for (const mock of Object.values(mocks)) mock.mockReset();
    bundles.database.editorBuffer.dispose.mockReset();
    mocks.database.mockResolvedValue(bundles.database);
    mocks.infrastructure.mockResolvedValue(bundles.infrastructure);
    mocks.runtimes.mockResolvedValue(bundles.runtimes);
    mocks.services.mockResolvedValue(bundles.services);
    mocks.controllers.mockResolvedValue(bundles.controllers);
  });

  it('continues after the optional background step fails', async () => {
    const error = new Error('background setup failed');
    mocks.background.mockRejectedValue(error);

    await expect(finishBoot({} as never)).resolves.toBeUndefined();

    expect(mocks.logWarn).toHaveBeenCalledWith('Non-critical boot phase failed; continuing', {
      phase: 'background-tasks',
      error,
    });
  });

  it('starts user env capture before the backend chain without adding a boot step', async () => {
    await expect(finishBoot({} as never)).resolves.toBeUndefined();

    const order = (mock: { mock: { invocationCallOrder: number[] } }) =>
      mock.mock.invocationCallOrder[0]!;
    expect(order(mocks.startUserEnvCapture)).toBeLessThan(order(mocks.database));
    expect(order(mocks.database)).toBeLessThan(order(mocks.runtimes));
    expect(mocks.logInfo).not.toHaveBeenCalledWith(
      expect.stringContaining('resolve-user-env'),
      expect.anything()
    );
  });

  it('rethrows a critical step failure and stops boot', async () => {
    const error = new Error('database unavailable');
    mocks.database.mockRejectedValue(error);

    await expect(finishBoot({} as never)).rejects.toBe(error);

    expect(mocks.infrastructure).not.toHaveBeenCalled();
    expect(mocks.services).not.toHaveBeenCalled();
    expect(mocks.appScopeDispose).toHaveBeenCalledWith(error);
    // bootDatabase cleans up its own partial resources; there is nothing for
    // finishBoot to close when the database bundle never materialized.
    expect(mocks.closeAppDb).not.toHaveBeenCalled();
    expect(bundles.database.editorBuffer.dispose).not.toHaveBeenCalled();
  });

  it('disposes composed resources when a later critical step fails', async () => {
    const error = new Error('services unavailable');
    mocks.services.mockRejectedValue(error);

    await expect(finishBoot({} as never)).rejects.toBe(error);

    expect(mocks.appScopeDispose).toHaveBeenCalledWith(error);
    expect(mocks.closeAppDb).toHaveBeenCalledOnce();
    expect(bundles.database.editorBuffer.dispose).toHaveBeenCalledOnce();
    expect(mocks.controllers).not.toHaveBeenCalled();
  });

  it('does not start backend work when renderer startup is already cancelled', async () => {
    const controller = new AbortController();
    const error = new Error('renderer failed');
    controller.abort(error);

    await expect(finishBoot({} as never, controller.signal)).rejects.toBe(error);

    expect(mocks.startUserEnvCapture).not.toHaveBeenCalled();
    expect(mocks.database).not.toHaveBeenCalled();
    expect(mocks.appScopeDispose).toHaveBeenCalledWith(error);
  });

  it('stops between phases when renderer startup fails during backend boot', async () => {
    const controller = new AbortController();
    const error = new Error('renderer failed');
    mocks.database.mockImplementation(async () => {
      controller.abort(error);
      return bundles.database;
    });

    await expect(finishBoot({} as never, controller.signal)).rejects.toBe(error);

    expect(mocks.infrastructure).not.toHaveBeenCalled();
    expect(mocks.closeAppDb).toHaveBeenCalledOnce();
    expect(bundles.database.editorBuffer.dispose).toHaveBeenCalledOnce();
  });
});
