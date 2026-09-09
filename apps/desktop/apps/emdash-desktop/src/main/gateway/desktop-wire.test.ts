import type { Controller } from '@emdash/wire/rpc';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ControllersBundle } from '@main/bootstrap/boot/phases/controllers';

const mocks = vi.hoisted(() => ({
  ipcHandle: vi.fn(),
  exposeWireToWindows: vi.fn(),
  scopeAdd: vi.fn(),
}));

vi.mock('electron', () => ({
  ipcMain: { handle: mocks.ipcHandle, removeHandler: vi.fn() },
  MessageChannelMain: class {
    port1 = {};
    port2 = {};
  },
}));
vi.mock('@main/bootstrap/core/app-scope', () => ({
  appScope: { child: () => ({ add: mocks.scopeAdd }) },
}));
vi.mock('@emdash/wire/rpc', async (importOriginal) => {
  const original = await importOriginal<typeof import('@emdash/wire/rpc')>();
  return { ...original, exposeWireToWindows: mocks.exposeWireToWindows };
});

function stubController(overrides: Partial<Controller> = {}): Controller {
  return {
    call: vi.fn(async () => 'routed-result'),
    resolveLive: vi.fn(() => null),
    acquireLive: vi.fn(() => null),
    ...overrides,
  };
}

function bundleWith(controllers: Record<string, Controller>): ControllersBundle {
  return {
    controllers,
    scope: { dispose: vi.fn(async () => {}) },
  } as unknown as ControllersBundle;
}

describe('desktop wire gateway', () => {
  beforeEach(() => {
    vi.resetModules();
    for (const mock of Object.values(mocks)) mock.mockReset();
  });

  it('installs the renderer port handler before any controllers exist', async () => {
    const { installDesktopWire } = await import('./desktop-wire');
    installDesktopWire();

    expect(mocks.exposeWireToWindows).toHaveBeenCalledOnce();
    const [deps, controller] = mocks.exposeWireToWindows.mock.calls[0] as [
      { ipcMain: unknown },
      Controller,
    ];
    expect(deps.ipcMain).toBeDefined();
    expect(typeof controller.call).toBe('function');
  });

  it('queues calls made before registration and serves them once controllers register', async () => {
    const { installDesktopWire, registerDesktopWireControllers } = await import('./desktop-wire');
    installDesktopWire();
    const routing = mocks.exposeWireToWindows.mock.calls[0][1] as Controller;

    let settled = false;
    const pending = routing.call('projects.list', { input: true }).finally(() => {
      settled = true;
    });
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(settled).toBe(false);

    const projects = stubController();
    registerDesktopWireControllers(bundleWith({ projects }));

    await expect(pending).resolves.toBe('routed-result');
    expect(projects.call).toHaveBeenCalledWith('list', { input: true }, undefined);
  });

  it('routes synchronously once controllers are registered', async () => {
    const { installDesktopWire, registerDesktopWireControllers } = await import('./desktop-wire');
    installDesktopWire();
    const routing = mocks.exposeWireToWindows.mock.calls[0][1] as Controller;

    const source = { snapshot: vi.fn(), subscribe: vi.fn() };
    const projects = stubController({ resolveLive: vi.fn(() => source) });
    registerDesktopWireControllers(bundleWith({ projects }));

    expect(routing.resolveLive('projects.projectList')).toBe(source);
    await expect(routing.call('projects.open', {})).resolves.toBe('routed-result');
  });

  it('defers live topics requested before registration to the routed source', async () => {
    const { installDesktopWire, registerDesktopWireControllers } = await import('./desktop-wire');
    installDesktopWire();
    const routing = mocks.exposeWireToWindows.mock.calls[0][1] as Controller;

    const deferredSource = routing.resolveLive('projects.projectList');
    expect(deferredSource).not.toBeNull();
    const lease = routing.acquireLive('projects.projectList');
    expect(lease).not.toBeNull();

    const snapshot = { generation: 0, sequence: 0, timestamp: 0, data: { ok: true } };
    const source = {
      snapshot: vi.fn(async () => snapshot),
      subscribe: vi.fn(() => () => {}),
    };
    const projects = stubController({
      resolveLive: vi.fn(() => source),
      acquireLive: vi.fn(() => ({ ready: async () => source, release: async () => {} })),
    });
    registerDesktopWireControllers(bundleWith({ projects }));

    await expect(deferredSource!.snapshot()).resolves.toBe(snapshot);
    await expect(lease!.ready()).resolves.toBe(source);
  });

  it('rejects unknown wire paths after registration', async () => {
    const { installDesktopWire, registerDesktopWireControllers } = await import('./desktop-wire');
    installDesktopWire();
    const routing = mocks.exposeWireToWindows.mock.calls[0][1] as Controller;
    registerDesktopWireControllers(bundleWith({ projects: stubController() }));

    await expect(routing.call('unknown.path', {})).rejects.toThrow(
      "Unknown desktop wire path 'unknown.path'"
    );
  });
});
