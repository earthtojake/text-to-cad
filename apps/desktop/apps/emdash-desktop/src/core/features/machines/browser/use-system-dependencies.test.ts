import {
  GIT_DEPENDENCY_DESCRIPTOR,
  type HostDependencySnapshot,
  type HostDependencyView,
} from '@emdash/core/services/host-dependencies/api';
import { ok } from '@emdash/shared';
import { createScope } from '@emdash/shared/concurrency';
import { deferred } from '@emdash/shared/testing';
import { cell, expose, flushStateTurn, peek, query } from '@emdash/wire/state';
import { createTestWire } from '@emdash/wire/testing';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { machinesContract } from '../api';
import { useSystemDependencies } from './use-system-dependencies';
import { resetSystemDependenciesRemoteForTests } from './use-system-dependency-snapshot';

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

let activeFixture: ReturnType<typeof createMachinesWire> | undefined;

vi.mock('@core/features/machines/api/browser/client', () => ({
  getMachinesClient: async () => activeFixture!.wire.client,
}));

vi.mock('@emdash/ui/react/primitives', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  toast: Object.assign(vi.fn(), { error: vi.fn() }),
}));

describe('useSystemDependencies', () => {
  let dom: JSDOM;
  let root: Root;
  let container: HTMLDivElement;
  let queryClient: QueryClient;

  beforeEach(() => {
    dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>');
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
    vi.stubGlobal('window', dom.window);
    vi.stubGlobal('document', dom.window.document);
    vi.stubGlobal('HTMLElement', dom.window.HTMLElement);

    queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    container = dom.window.document.getElementById('root') as HTMLDivElement;
    root = createRoot(container);
  });

  afterEach(async () => {
    act(() => root.unmount());
    await resetSystemDependenciesRemoteForTests();
    await activeFixture?.scope.dispose();
    await activeFixture?.wire.dispose();
    activeFixture = undefined;
    queryClient.clear();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    dom.window.close();
  });

  it('stays loading until the demand-gated first probe settles, then streams updates', async () => {
    const fixture = createMachinesWire();
    activeFixture = fixture;

    await act(async () => {
      root.render(
        React.createElement(
          QueryClientProvider,
          { client: queryClient },
          React.createElement(Probe)
        )
      );
    });

    expect(container.querySelector('[data-testid="loading"]')?.textContent).toBe('true');
    expect(container.querySelector('[data-testid="dependencies"]')?.textContent).toBe('');

    fixture.resolveFirstProbe(
      hostDependencySnapshot([
        hostDependencyView(GIT_DEPENDENCY_DESCRIPTOR, { resolvedPath: '/usr/bin/git' }),
        hostDependencyView({
          id: 'fake-agent',
          name: 'Fake Agent',
          category: 'agent',
          binaryNames: ['fake-agent'],
          status: 'active',
        }),
      ])
    );

    await vi.waitFor(() => {
      expect(container.querySelector('[data-testid="dependencies"]')?.textContent).toBe('Git');
    });
    expect(container.querySelector('[data-testid="loading"]')?.textContent).toBe('false');
    expect(fixture.refresh).not.toHaveBeenCalled();

    fixture.snapshot.settle(
      hostDependencySnapshot(
        [hostDependencyView(GIT_DEPENDENCY_DESCRIPTOR, { resolvedPath: '/usr/bin/git' })],
        2
      )
    );
    flushStateTurn();
    await vi.waitFor(() => {
      expect(container.querySelector('[data-testid="generation"]')?.textContent).toBe('2');
    });
  });
});

function Probe() {
  const result = useSystemDependencies(undefined, true, {
    installSystemDependencies: vi.fn(),
  });
  return React.createElement(
    'div',
    {},
    React.createElement('span', { 'data-testid': 'loading' }, String(result.isLoading)),
    React.createElement(
      'span',
      { 'data-testid': 'dependencies' },
      result.data?.map((dependency) => dependency.name).join(',') ?? ''
    ),
    React.createElement(
      'span',
      { 'data-testid': 'generation' },
      String(result.snapshot?.generation ?? '')
    )
  );
}

function createMachinesWire() {
  const firstProbe = deferred<HostDependencySnapshot>();
  const scope = createScope({ label: 'use-system-dependencies-test' });
  const snapshot = query<HostDependencySnapshot>({
    fetch: () => firstProbe.promise,
    scope,
  });
  const refresh = vi.fn(async () => {
    const current = peek(snapshot);
    if (!current) throw new Error('refresh before first snapshot');
    return ok(current);
  });
  const systemDependencies = expose(
    machinesContract.systemDependencies,
    { current: snapshot },
    { mutations: { refresh } }
  );
  const hostSettings = expose(machinesContract.hostSettings, {
    current: () => cell({ settings: {}, parseError: false }),
  });
  const wire = createTestWire(machinesContract, {
    getMachines: async () => [],
    getMachineUsage: async () => ({}),
    getMachineMetrics: async () => null as never,
    systemDependencies,
    hostSettings,
    updateHostSettings: async () => ok({ settings: {}, parseError: false }),
    installSystemDependencies: {
      run: async () => ok({}),
      toError: (error: unknown) => ({
        type: 'io' as const,
        message: error instanceof Error ? error.message : String(error),
      }),
    },
    saveMachine: vi.fn(),
    deleteMachine: vi.fn(),
    renameMachine: vi.fn(),
  } as never);
  return { wire, scope, snapshot, refresh, resolveFirstProbe: firstProbe.resolve };
}

function hostDependencySnapshot(
  views: HostDependencyView[],
  generation = 1
): HostDependencySnapshot {
  return {
    hostId: 'test-host',
    generation,
    hostElevation: null,
    dependencies: Object.fromEntries(views.map((view) => [view.definition.id, view])),
  };
}

function hostDependencyView(
  definition: HostDependencyView['definition'],
  options: { resolvedPath?: string | null } = {}
): HostDependencyView {
  const resolvedPath = options.resolvedPath ?? null;
  return {
    hostId: 'test-host',
    definition,
    installOptions: definition.installCommands?.macos ?? [],
    selection: null,
    candidates: [],
    resolved: resolvedPath
      ? {
          id: definition.id,
          command: definition.binaryNames[0] ?? definition.id,
          path: resolvedPath,
          realpath: resolvedPath,
          source: { kind: 'auto' },
        }
      : null,
    status: resolvedPath ? 'available' : 'missing',
    checkedAt: 1,
  };
}
