import { hostRef, LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import { runtimeHostUnavailable } from '@emdash/core/primitives/runtime-resolution/api';
import { RuntimeBroker, type HostRuntimesClient } from '@emdash/core/services/runtime-broker/api';
import { err, ok } from '@emdash/shared';
import { createScope } from '@emdash/shared/concurrency';
import { deferred } from '@emdash/shared/testing';
import type { Connection } from '@emdash/wire/rpc';
import { peek } from '@emdash/wire/state';
import { describe, expect, it, vi } from 'vitest';
import type { ProjectProvider } from '@core/features/projects/api/node/project-provider';
import type { Project } from '@core/primitives/projects/api';
import { createHostAvailability } from '@core/services/hosts/node/availability';
import {
  createProjectAttachmentManager,
  type ProjectAttachmentAdapter,
} from './project-attachment-manager';

describe('ProjectAttachmentManager', () => {
  it('does not expose legacy open, close, or Provider lookup adapters', async () => {
    const scope = createScope({ label: 'project-attachment-manager-contract-test' });
    const manager = createProjectAttachmentManager({
      scope,
      availability: createHostAvailability({
        scope,
        readiness: { prepare: async () => ok() },
      }),
      adapter: {
        loadProject: async () => undefined,
        statRepository: async () => ok({ type: 'directory' as const }),
        open: async () => ok(projectProvider()),
      },
    });

    expect(manager).not.toHaveProperty('openProject');
    expect(manager).not.toHaveProperty('closeProject');
    expect(manager).not.toHaveProperty('getProject');

    await scope.dispose();
  });

  it('attaches a tracked Project once when its Host reaches a ready generation', async () => {
    const scope = createScope({ label: 'project-attachment-manager-test' });
    const readiness = deferred<ReturnType<typeof ok<void>>>();
    const availability = createHostAvailability({
      scope,
      readiness: { prepare: () => readiness.promise },
    });
    const demand = vi.spyOn(availability, 'demand');
    const project = sshProject();
    const provider = projectProvider();
    const open = vi.fn(async () => ok(provider));
    const manager = createProjectAttachmentManager({
      scope,
      availability,
      adapter: {
        loadProject: async () => project,
        statRepository: async () => ok({ type: 'directory' as const }),
        open,
      },
      createAttemptId: () => 'attempt-1',
    });
    const owner = createScope({ label: 'project-owner' });

    const state = manager.track(project.id, owner);

    expect(peek(state)).toEqual({ kind: 'absent' });
    await vi.waitFor(() =>
      expect(availability.stateFor(project.host)).toMatchObject({
        kind: 'preparing',
      })
    );

    readiness.resolve(ok());
    await vi.waitFor(() =>
      expect(peek(state)).toEqual({
        kind: 'attached',
        establishedHostGeneration: 1,
      })
    );

    expect(open).toHaveBeenCalledOnce();
    expect(manager.requireAttached(project.id)).toEqual(ok(provider));
    expect(demand).toHaveBeenCalledOnce();
    expect(demand).toHaveBeenCalledWith(project.host, 'automatic', expect.anything());
    expect(demand.mock.results[0]?.value.mode).toBe('automatic');

    await owner.dispose();
    await scope.dispose();
  });

  it('retains its Provider across explicit Host suspension and Connect', async () => {
    const scope = createScope({ label: 'project-attachment-manager-test' });
    const availability = createHostAvailability({
      scope,
      readiness: { prepare: async () => ok() },
    });
    const project = sshProject();
    const provider = projectProvider();
    const open = vi.fn(async () => ok(provider));
    const manager = createProjectAttachmentManager({
      scope,
      availability,
      adapter: {
        loadProject: async () => project,
        statRepository: async () => ok({ type: 'directory' as const }),
        open,
      },
    });
    const opened = vi.fn();
    const closed = vi.fn();
    manager.on('projectOpened', opened);
    manager.on('projectClosed', closed);
    const owner = createScope({ label: 'project-owner' });
    const state = manager.track(project.id, owner);
    await vi.waitFor(() => expect(peek(state).kind).toBe('attached'));

    availability.suspend(project.host);

    expect(peek(state)).toEqual({
      kind: 'attached',
      establishedHostGeneration: 1,
    });
    expect(manager.requireAttached(project.id)).toMatchObject({
      success: false,
      error: { type: 'host-unavailable', reason: 'offline' },
    });
    expect(provider.dispose).not.toHaveBeenCalled();

    await expect(manager.recover(project.id)).resolves.toEqual(ok());
    await vi.waitFor(() => expect(availability.stateFor(project.host).kind).toBe('ready'));

    expect(manager.requireAttached(project.id)).toEqual(ok(provider));
    expect(peek(state)).toEqual({
      kind: 'attached',
      establishedHostGeneration: 1,
    });
    expect(open).toHaveBeenCalledOnce();
    expect(opened).toHaveBeenCalledOnce();
    expect(closed).not.toHaveBeenCalled();

    await owner.dispose();
    await vi.waitFor(() => expect(closed).toHaveBeenCalledOnce());
    await scope.dispose();
  });

  it('keeps a retained Provider bound to the recovered Host runtime without hook churn', async () => {
    const scope = createScope({ label: 'project-attachment-manager-test' });
    const project = sshProject();
    const firstCall = vi.fn(async () => 'first');
    const secondCall = vi.fn(async () => 'second');
    let runtime = runtimeConnection(firstCall);
    const broker = new RuntimeBroker({
      resolve: () =>
        ok({
          client: {} as HostRuntimesClient,
          connection: runtime,
        }),
    });
    const availability = createHostAvailability({
      scope,
      readiness: {
        async prepare(host) {
          const resolved = await broker.client(host);
          return resolved.success ? ok() : err(resolved.error);
        },
      },
    });
    const provider = projectProvider() as ProjectProvider & { probe(): Promise<string> };
    const open = vi.fn<ProjectAttachmentAdapter['open']>(async () => {
      const resolved = await broker.client(project.host);
      if (!resolved.success) return err(resolved.error);
      const retainedRuntime = resolved.data;
      provider.probe = () =>
        retainedRuntime.files.getHomeDir(undefined) as unknown as Promise<string>;
      return ok(provider);
    });
    const manager = createProjectAttachmentManager({
      scope,
      availability,
      adapter: {
        loadProject: async () => project,
        statRepository: async () => ok({ type: 'directory' as const }),
        open,
      },
    });
    const opened = vi.fn();
    const closed = vi.fn();
    manager.on('projectOpened', opened);
    manager.on('projectClosed', closed);
    const owner = createScope({ label: 'project-owner' });
    const state = manager.track(project.id, owner);
    await vi.waitFor(() => expect(peek(state).kind).toBe('attached'));
    expect(await provider.probe()).toBe('first');

    runtime = runtimeConnection(secondCall);
    availability.invalidate(project.host);
    await vi.waitFor(() =>
      expect(availability.stateFor(project.host)).toEqual({ kind: 'ready', generation: 2 })
    );

    expect(manager.requireAttached(project.id)).toEqual(ok(provider));
    await expect(provider.probe()).resolves.toBe('second');
    expect(open).toHaveBeenCalledOnce();
    expect(opened).toHaveBeenCalledOnce();
    expect(closed).not.toHaveBeenCalled();

    await owner.dispose();
    await scope.dispose();
  });

  it('keeps an attached Project automatic after a manual outcome so SSH can recover it', async () => {
    const scope = createScope({ label: 'project-attachment-manager-test' });
    const project = sshProject();
    const failure = runtimeHostUnavailable(
      project.host,
      'install-failed',
      'Host runtime installation failed'
    );
    const prepare = vi
      .fn()
      .mockResolvedValueOnce(ok())
      .mockResolvedValueOnce(err(failure))
      .mockResolvedValueOnce(ok());
    const availability = createHostAvailability({
      scope,
      readiness: { prepare },
    });
    const demand = vi.spyOn(availability, 'demand');
    const provider = projectProvider();
    const open = vi.fn(async () => ok(provider));
    const manager = createProjectAttachmentManager({
      scope,
      availability,
      adapter: {
        loadProject: async () => project,
        statRepository: async () => ok({ type: 'directory' as const }),
        open,
      },
    });
    const owner = createScope({ label: 'project-owner' });
    const state = manager.track(project.id, owner);
    await vi.waitFor(() => expect(peek(state).kind).toBe('attached'));

    availability.invalidate(project.host);
    await vi.waitFor(() =>
      expect(availability.stateFor(project.host)).toEqual({
        kind: 'unavailable',
        issue: failure,
        recovery: 'manual',
      })
    );
    expect(demand.mock.results[0]?.value.mode).toBe('automatic');

    availability.wakeDemanded('online');
    availability.wakeDemanded('focus');
    await Promise.resolve();
    expect(prepare).toHaveBeenCalledTimes(2);

    availability.wake(project.host, 'ssh-edge');
    await vi.waitFor(() =>
      expect(availability.stateFor(project.host)).toEqual({
        kind: 'ready',
        generation: 2,
      })
    );

    expect(manager.requireAttached(project.id)).toEqual(ok(provider));
    expect(peek(state).kind).toBe('attached');
    expect(open).toHaveBeenCalledOnce();
    expect(provider.dispose).not.toHaveBeenCalled();

    await owner.dispose();
    await scope.dispose();
  });

  it('degrades every attached Project on a suspended Host without disposing Providers', async () => {
    const scope = createScope({ label: 'project-attachment-manager-test' });
    const prepare = vi.fn(async () => ok<void>());
    const availability = createHostAvailability({
      scope,
      readiness: { prepare },
    });
    const first = sshProject();
    const second = {
      ...sshProject(),
      id: 'project-2',
      name: 'Second Project',
      path: '/second-repo',
    };
    const projects = new Map([
      [first.id, first],
      [second.id, second],
    ]);
    const providers = new Map([
      [first.id, projectProvider()],
      [second.id, projectProvider()],
    ]);
    const manager = createProjectAttachmentManager({
      scope,
      availability,
      adapter: {
        loadProject: async (projectId) => projects.get(projectId),
        statRepository: async () => ok({ type: 'directory' as const }),
        open: async (project) => {
          const provider = providers.get(project.id);
          if (!provider) throw new Error('Missing test Provider');
          return ok(provider);
        },
      },
    });
    const owner = createScope({ label: 'project-owner' });
    const firstState = manager.track(first.id, owner);
    const secondState = manager.track(second.id, owner);
    await vi.waitFor(() => expect(peek(firstState).kind).toBe('attached'));
    await vi.waitFor(() => expect(peek(secondState).kind).toBe('attached'));

    availability.suspend(first.host);

    expect(peek(firstState).kind).toBe('attached');
    expect(peek(secondState).kind).toBe('attached');
    expect(manager.requireAttached(first.id)).toMatchObject({
      success: false,
      error: { type: 'host-unavailable', reason: 'offline' },
    });
    expect(manager.requireAttached(second.id)).toMatchObject({
      success: false,
      error: { type: 'host-unavailable', reason: 'offline' },
    });
    expect(providers.get(first.id)?.dispose).not.toHaveBeenCalled();
    expect(providers.get(second.id)?.dispose).not.toHaveBeenCalled();
    expect(prepare).toHaveBeenCalledOnce();

    await owner.dispose();
    await scope.dispose();
  });

  it('cancels an in-flight attachment on Host suspension and disposes a late Provider', async () => {
    const scope = createScope({ label: 'project-attachment-manager-test' });
    const availability = createHostAvailability({
      scope,
      readiness: { prepare: async () => ok() },
    });
    const project = sshProject();
    const provider = projectProvider();
    const opened = deferred<ReturnType<typeof ok<ProjectProvider>>>();
    const manager = createProjectAttachmentManager({
      scope,
      availability,
      adapter: {
        loadProject: async () => project,
        statRepository: async () => ok({ type: 'directory' as const }),
        open: () => opened.promise,
      },
    });
    const owner = createScope({ label: 'project-owner' });
    const state = manager.track(project.id, owner);
    await vi.waitFor(() => expect(peek(state).kind).toBe('attaching'));

    availability.suspend(project.host);

    await vi.waitFor(() =>
      expect(peek(state)).toEqual({
        kind: 'absent',
        attemptedHostGeneration: 1,
      })
    );
    opened.resolve(ok(provider));
    await vi.waitFor(() => expect(provider.dispose).toHaveBeenCalledOnce());
    expect(manager.requireAttached(project.id).success).toBe(false);

    await owner.dispose();
    await scope.dispose();
  });

  it.each([
    ['SSH Connect', sshProject(), 'connect'],
    ['local Retry', localProject(), 'retry'],
  ] as const)(
    'starts %s as the matching explicit Host readiness request',
    async (_label, project, cause) => {
      const scope = createScope({ label: 'project-attachment-manager-test' });
      const availability = createHostAvailability({
        scope,
        readiness: { prepare: async () => ok() },
      });
      const requestReady = vi.spyOn(availability, 'requestReady');
      const manager = createProjectAttachmentManager({
        scope,
        availability,
        adapter: {
          loadProject: async () => project,
          statRepository: async () => ok({ type: 'directory' as const }),
          open: async () => ok(projectProvider()),
        },
      });

      await expect(manager.recover(project.id)).resolves.toEqual(ok());

      expect(requestReady).toHaveBeenCalledWith(project.host, cause);
      await scope.dispose();
    }
  );

  it('joins concurrent manual recovery requests without restarting Host readiness', async () => {
    const scope = createScope({ label: 'project-attachment-manager-test' });
    const readiness = deferred<ReturnType<typeof ok<void>>>();
    const availability = createHostAvailability({
      scope,
      readiness: { prepare: () => readiness.promise },
    });
    const project = sshProject();
    const loaded = deferred<Project | undefined>();
    const loadProject = vi.fn(() => loaded.promise);
    const manager = createProjectAttachmentManager({
      scope,
      availability,
      adapter: {
        loadProject,
        statRepository: async () => ok({ type: 'directory' as const }),
        open: async () => ok(projectProvider()),
      },
    });

    const first = manager.recover(project.id);
    const repeated = manager.recover(project.id);

    expect(repeated).toBe(first);
    expect(loadProject).toHaveBeenCalledOnce();

    loaded.resolve(project);
    await expect(first).resolves.toEqual(ok());
    expect(availability.stateFor(project.host).kind).toBe('preparing');

    readiness.resolve(ok());
    await scope.dispose();
  });

  it('retries a Project-specific failure in the current ready generation only when recovered', async () => {
    const scope = createScope({ label: 'project-attachment-manager-test' });
    const availability = createHostAvailability({
      scope,
      readiness: { prepare: async () => ok() },
    });
    const project = sshProject();
    const provider = projectProvider();
    const statRepository = vi
      .fn()
      .mockResolvedValueOnce(err({ type: 'not-found', path: '/repo' }))
      .mockResolvedValueOnce(ok({ type: 'directory' as const }));
    const open = vi.fn(async () => ok(provider));
    const manager = createProjectAttachmentManager({
      scope,
      availability,
      adapter: {
        loadProject: async () => project,
        statRepository,
        open,
      },
    });
    const owner = createScope({ label: 'project-owner' });
    const state = manager.track(project.id, owner);
    await vi.waitFor(() =>
      expect(peek(state)).toEqual({
        kind: 'absent',
        lastFailure: { type: 'repository-missing', path: '/repo' },
        attemptedHostGeneration: 1,
      })
    );

    expect(manager.requireAttached(project.id)).toEqual(
      err({ type: 'repository-missing', path: '/repo' })
    );
    expect(statRepository).toHaveBeenCalledOnce();

    await expect(manager.recover(project.id)).resolves.toEqual(ok());
    await vi.waitFor(() => expect(peek(state).kind).toBe('attached'));

    expect(statRepository).toHaveBeenCalledTimes(2);
    expect(open).toHaveBeenCalledOnce();

    await owner.dispose();
    await scope.dispose();
  });

  it('disposes a late Provider when the durable Project revision changed during attachment', async () => {
    const scope = createScope({ label: 'project-attachment-manager-test' });
    const availability = createHostAvailability({
      scope,
      readiness: { prepare: async () => ok() },
    });
    let project = sshProject();
    const provider = projectProvider();
    const opened = deferred<ReturnType<typeof ok<ProjectProvider>>>();
    const open = vi.fn(() => opened.promise);
    const manager = createProjectAttachmentManager({
      scope,
      availability,
      adapter: {
        loadProject: async () => ({ ...project }),
        statRepository: async () => ok({ type: 'directory' as const }),
        open,
      },
    });
    const owner = createScope({ label: 'project-owner' });
    const state = manager.track(project.id, owner);
    await vi.waitFor(() => expect(peek(state).kind).toBe('attaching'));
    project = {
      ...project,
      updatedAt: '2026-08-13T00:00:01.000Z',
    };

    opened.resolve(ok(provider));

    await vi.waitFor(() => expect(provider.dispose).toHaveBeenCalledOnce());
    expect(peek(state)).toEqual({
      kind: 'absent',
      attemptedHostGeneration: 1,
    });
    expect(manager.requireAttached(project.id).success).toBe(false);

    await owner.dispose();
    await scope.dispose();
  });

  it('releases and disposes retained Provider ownership at most once during shutdown', async () => {
    const scope = createScope({ label: 'project-attachment-manager-test' });
    const availability = createHostAvailability({
      scope,
      readiness: { prepare: async () => ok() },
    });
    const project = sshProject();
    const provider = projectProvider();
    const manager = createProjectAttachmentManager({
      scope,
      availability,
      adapter: {
        loadProject: async () => project,
        statRepository: async () => ok({ type: 'directory' as const }),
        open: async () => ok(provider),
      },
    });
    const owner = createScope({ label: 'project-owner' });
    const state = manager.track(project.id, owner);
    await vi.waitFor(() => expect(peek(state).kind).toBe('attached'));

    await manager.release();
    await manager.release();
    expect(provider.release).toHaveBeenCalledOnce();

    await manager.dispose();
    await manager.dispose();
    expect(provider.dispose).toHaveBeenCalledOnce();

    await owner.dispose();
    await scope.dispose();
  });

  it('holds Provider ownership until the final tracking lease releases', async () => {
    const scope = createScope({ label: 'project-attachment-manager-test' });
    const availability = createHostAvailability({
      scope,
      readiness: { prepare: async () => ok() },
    });
    const project = sshProject();
    const provider = projectProvider();
    const manager = createProjectAttachmentManager({
      scope,
      availability,
      adapter: {
        loadProject: async () => project,
        statRepository: async () => ok({ type: 'directory' as const }),
        open: async () => ok(provider),
      },
    });
    const firstOwner = createScope({ label: 'first-project-owner' });
    const secondOwner = createScope({ label: 'second-project-owner' });
    const firstState = manager.track(project.id, firstOwner);
    const secondState = manager.track(project.id, secondOwner);
    expect(secondState).toBe(firstState);
    await vi.waitFor(() => expect(peek(firstState).kind).toBe('attached'));

    await firstOwner.dispose();
    expect(provider.dispose).not.toHaveBeenCalled();
    expect(manager.requireAttached(project.id)).toEqual(ok(provider));

    await secondOwner.dispose();
    expect(provider.dispose).toHaveBeenCalledOnce();
    expect(manager.requireAttached(project.id)).toEqual(
      err({ type: 'project-missing', projectId: project.id })
    );

    await scope.dispose();
  });

  it('disposes a Provider that completes after its final tracking lease released', async () => {
    const scope = createScope({ label: 'project-attachment-manager-test' });
    const availability = createHostAvailability({
      scope,
      readiness: { prepare: async () => ok() },
    });
    const project = sshProject();
    const provider = projectProvider();
    const opened = deferred<ReturnType<typeof ok<ProjectProvider>>>();
    const manager = createProjectAttachmentManager({
      scope,
      availability,
      adapter: {
        loadProject: async () => project,
        statRepository: async () => ok({ type: 'directory' as const }),
        open: () => opened.promise,
      },
    });
    const projectOpened = vi.fn();
    manager.on('projectOpened', projectOpened);
    const owner = createScope({ label: 'project-owner' });
    const state = manager.track(project.id, owner);
    await vi.waitFor(() => expect(peek(state).kind).toBe('attaching'));

    await owner.dispose();
    opened.resolve(ok(provider));

    await vi.waitFor(() => expect(provider.dispose).toHaveBeenCalledOnce());
    expect(projectOpened).not.toHaveBeenCalled();
    expect(manager.requireAttached(project.id)).toEqual(
      err({ type: 'project-missing', projectId: project.id })
    );

    await scope.dispose();
  });

  it('rejects an old-generation completion and attaches only the current Host generation', async () => {
    const scope = createScope({ label: 'project-attachment-manager-test' });
    const availability = createHostAvailability({
      scope,
      readiness: { prepare: async () => ok() },
    });
    const project = sshProject();
    const staleProvider = projectProvider();
    const currentProvider = projectProvider();
    const staleOpen = deferred<ReturnType<typeof ok<ProjectProvider>>>();
    const open = vi
      .fn()
      .mockImplementationOnce(() => staleOpen.promise)
      .mockResolvedValueOnce(ok(currentProvider));
    const manager = createProjectAttachmentManager({
      scope,
      availability,
      adapter: {
        loadProject: async () => project,
        statRepository: async () => ok({ type: 'directory' as const }),
        open,
      },
    });
    const owner = createScope({ label: 'project-owner' });
    const state = manager.track(project.id, owner);
    await vi.waitFor(() =>
      expect(peek(state)).toMatchObject({
        kind: 'attaching',
        hostGeneration: 1,
      })
    );

    availability.invalidate(project.host);
    await availability.ensureReady(project.host, 'retry');
    await vi.waitFor(() =>
      expect(peek(state)).toEqual({
        kind: 'attached',
        establishedHostGeneration: 2,
      })
    );

    staleOpen.resolve(ok(staleProvider));
    await vi.waitFor(() => expect(staleProvider.dispose).toHaveBeenCalledOnce());
    expect(manager.requireAttached(project.id)).toEqual(ok(currentProvider));
    expect(open).toHaveBeenCalledTimes(2);

    await owner.dispose();
    await scope.dispose();
  });

  it('preserves typed waiting, repository, runtime, and unexpected failures', async () => {
    const project = sshProject();

    await expectAttachmentFailure({
      project,
      statRepository: async () => err({ type: 'permission-denied' as const, path: '/repo' }),
      expected: {
        type: 'repository-unavailable',
        path: '/repo',
        message: 'permission-denied: /repo',
      },
    });

    const runtimeFailure = runtimeHostUnavailable(
      project.host,
      'install-failed',
      'Host runtime installation failed'
    );
    await expectAttachmentFailure({
      project,
      statRepository: async () => err(runtimeFailure),
      expected: runtimeFailure,
    });

    await expectAttachmentFailure({
      project,
      statRepository: async () => ok({ type: 'directory' as const }),
      open: async () => err({ type: 'error' as const, message: 'provider failed' }),
      expected: {
        type: 'unexpected',
        stage: 'session-open',
        message: 'provider failed',
      },
    });

    await expectAttachmentFailure({
      project,
      statRepository: async () => {
        throw new Error('stat exploded');
      },
      expected: {
        type: 'unexpected',
        stage: 'repository-stat',
        message: 'stat exploded',
      },
    });
  });

  it('recovers an automatically eligible attachment runtime failure on a fresh Host generation', async () => {
    const scope = createScope({ label: 'project-attachment-manager-test' });
    const project = sshProject();
    const prepare = vi.fn(async () => ok<void>());
    const availability = createHostAvailability({
      scope,
      readiness: { prepare },
    });
    const runtimeFailure = runtimeHostUnavailable(
      project.host,
      'runtime-unavailable',
      'Host runtime is unavailable'
    );
    const statRepository = vi
      .fn<ProjectAttachmentAdapter['statRepository']>()
      .mockResolvedValueOnce(err(runtimeFailure))
      .mockResolvedValueOnce(ok({ type: 'directory' }));
    const provider = projectProvider();
    const manager = createProjectAttachmentManager({
      scope,
      availability,
      adapter: {
        loadProject: async () => project,
        statRepository,
        open: async () => ok(provider),
      },
    });
    const owner = createScope({ label: 'project-owner' });
    const state = manager.track(project.id, owner);

    await vi.waitFor(() =>
      expect(peek(state)).toEqual({
        kind: 'attached',
        establishedHostGeneration: 2,
      })
    );
    expect(prepare).toHaveBeenCalledTimes(2);
    expect(statRepository).toHaveBeenCalledTimes(2);
    expect(manager.requireAttached(project.id)).toEqual(ok(provider));

    await owner.dispose();
    await scope.dispose();
  });

  it('keeps repository failures passive across Host generations until explicit recovery', async () => {
    const scope = createScope({ label: 'project-attachment-manager-test' });
    const availability = createHostAvailability({
      scope,
      readiness: { prepare: async () => ok() },
    });
    const demand = vi.spyOn(availability, 'demand');
    const project = sshProject();
    const provider = projectProvider();
    const statRepository = vi
      .fn()
      .mockResolvedValueOnce(err({ type: 'not-found', path: '/repo' }))
      .mockResolvedValueOnce(ok({ type: 'directory' as const }));
    const manager = createProjectAttachmentManager({
      scope,
      availability,
      adapter: {
        loadProject: async () => project,
        statRepository,
        open: async () => ok(provider),
      },
    });
    const owner = createScope({ label: 'project-owner' });
    const state = manager.track(project.id, owner);
    await vi.waitFor(() => expect(peek(state).kind).toBe('absent'));
    await vi.waitFor(() => expect(statRepository).toHaveBeenCalledOnce());
    expect(demand.mock.results[0]?.value.mode).toBe('passive');
    const ensureReady = vi.spyOn(availability, 'ensureReady');
    ensureReady.mockClear();

    availability.wakeDemanded('online');
    availability.wakeDemanded('focus');

    expect(ensureReady).not.toHaveBeenCalled();

    availability.invalidate(project.host);
    availability.wake(project.host, 'ssh-edge');
    await vi.waitFor(() =>
      expect(availability.stateFor(project.host)).toEqual({ kind: 'ready', generation: 2 })
    );

    expect(statRepository).toHaveBeenCalledOnce();
    expect(peek(state)).toMatchObject({
      kind: 'absent',
      lastFailure: { type: 'repository-missing' },
    });

    await manager.recover(project.id);
    await vi.waitFor(() => expect(peek(state).kind).toBe('attached'));
    expect(statRepository).toHaveBeenCalledTimes(2);

    await owner.dispose();
    await scope.dispose();
  });

  it.each([
    ['manual', 'install-failed'],
    ['blocked', 'unsupported-platform'],
  ] as const)(
    'makes an absent Project passive after a %s Host recovery outcome',
    async (recovery, reason) => {
      const scope = createScope({ label: 'project-attachment-manager-test' });
      const project = sshProject();
      const failure = runtimeHostUnavailable(project.host, reason, `semantic:${reason}`);
      const prepare = vi.fn(async () => err(failure));
      const availability = createHostAvailability({
        scope,
        readiness: { prepare },
      });
      const demand = vi.spyOn(availability, 'demand');
      const manager = createProjectAttachmentManager({
        scope,
        availability,
        adapter: {
          loadProject: async () => project,
          statRepository: async () => ok({ type: 'directory' as const }),
          open: async () => ok(projectProvider()),
        },
      });
      const owner = createScope({ label: 'project-owner' });

      manager.track(project.id, owner);
      await vi.waitFor(() =>
        expect(availability.stateFor(project.host)).toMatchObject({
          kind: 'unavailable',
          recovery,
        })
      );

      expect(demand.mock.results[0]?.value.mode).toBe('passive');
      const ensureReady = vi.spyOn(availability, 'ensureReady');
      ensureReady.mockClear();
      availability.wakeDemanded('online');
      availability.wakeDemanded('focus');
      expect(ensureReady).not.toHaveBeenCalled();
      expect(prepare).toHaveBeenCalledOnce();

      await owner.dispose();
      await scope.dispose();
    }
  );

  it('rejects recovery and releases attachment when the durable Project is gone', async () => {
    const scope = createScope({ label: 'project-attachment-manager-test' });
    const availability = createHostAvailability({
      scope,
      readiness: { prepare: async () => ok() },
    });
    let project: Project | undefined = sshProject();
    const provider = projectProvider();
    const manager = createProjectAttachmentManager({
      scope,
      availability,
      adapter: {
        loadProject: async () => project,
        statRepository: async () => ok({ type: 'directory' as const }),
        open: async () => ok(provider),
      },
    });
    const owner = createScope({ label: 'project-owner' });
    const state = manager.track('project-1', owner);
    await vi.waitFor(() => expect(peek(state).kind).toBe('attached'));
    project = undefined;

    await expect(manager.recover('project-1')).resolves.toEqual(
      err({ type: 'project-missing', projectId: 'project-1' })
    );
    await vi.waitFor(() => expect(provider.dispose).toHaveBeenCalledOnce());
    expect(peek(state)).toEqual({
      kind: 'absent',
      lastFailure: { type: 'project-missing', projectId: 'project-1' },
    });

    await owner.dispose();
    await scope.dispose();
  });

  it('rejects a superseded attempt after relink and attaches the replacement Host identity', async () => {
    const scope = createScope({ label: 'project-attachment-manager-test' });
    const availability = createHostAvailability({
      scope,
      readiness: { prepare: async () => ok() },
    });
    let project = sshProject();
    const staleProvider = projectProvider();
    const currentProvider = projectProvider();
    const staleOpen = deferred<ReturnType<typeof ok<ProjectProvider>>>();
    const open = vi
      .fn()
      .mockImplementationOnce(() => staleOpen.promise)
      .mockResolvedValueOnce(ok(currentProvider));
    const manager = createProjectAttachmentManager({
      scope,
      availability,
      adapter: {
        loadProject: async () => project,
        statRepository: async () => ok({ type: 'directory' as const }),
        open,
      },
      createAttemptId: vi
        .fn()
        .mockReturnValueOnce('old-attempt')
        .mockReturnValueOnce('new-attempt'),
    });
    const owner = createScope({ label: 'project-owner' });
    const state = manager.track(project.id, owner);
    await vi.waitFor(() =>
      expect(peek(state)).toEqual({
        kind: 'attaching',
        hostGeneration: 1,
        attemptId: 'old-attempt',
      })
    );
    project = {
      ...project,
      connectionId: 'ssh-2',
      updatedAt: '2026-08-13T00:00:01.000Z',
      host: hostRef('remote', 'ssh-2'),
    };

    await manager.invalidate(project.id, 'relink');
    await vi.waitFor(() =>
      expect(peek(state)).toEqual({
        kind: 'attached',
        establishedHostGeneration: 2,
      })
    );

    staleOpen.resolve(ok(staleProvider));
    await vi.waitFor(() => expect(staleProvider.dispose).toHaveBeenCalledOnce());
    expect(manager.requireAttached(project.id)).toEqual(ok(currentProvider));
    expect(open).toHaveBeenCalledTimes(2);

    await owner.dispose();
    await scope.dispose();
  });

  it('rebinds after relink even when destructive disposal of the old Provider fails', async () => {
    const scope = createScope({ label: 'project-attachment-manager-test' });
    const availability = createHostAvailability({
      scope,
      readiness: { prepare: async () => ok() },
    });
    let project = sshProject();
    const staleProvider = projectProvider();
    vi.mocked(staleProvider.dispose).mockRejectedValue(new Error('dispose failed'));
    const currentProvider = projectProvider();
    const open = vi
      .fn()
      .mockResolvedValueOnce(ok(staleProvider))
      .mockResolvedValueOnce(ok(currentProvider));
    const manager = createProjectAttachmentManager({
      scope,
      availability,
      adapter: {
        loadProject: async () => project,
        statRepository: async () => ok({ type: 'directory' as const }),
        open,
      },
    });
    const closed = vi.fn();
    manager.on('projectClosed', closed);
    const owner = createScope({ label: 'project-owner' });
    const state = manager.track(project.id, owner);
    await vi.waitFor(() => expect(peek(state).kind).toBe('attached'));
    project = {
      ...project,
      connectionId: 'ssh-2',
      updatedAt: '2026-08-13T00:00:01.000Z',
      host: hostRef('remote', 'ssh-2'),
    };

    await expect(manager.invalidate(project.id, 'relink')).resolves.toBeUndefined();
    await vi.waitFor(() =>
      expect(peek(state)).toEqual({
        kind: 'attached',
        establishedHostGeneration: 2,
      })
    );

    expect(staleProvider.dispose).toHaveBeenCalledOnce();
    expect(closed).toHaveBeenCalledOnce();
    expect(manager.requireAttached(project.id)).toEqual(ok(currentProvider));

    await owner.dispose();
    await scope.dispose();
  });

  it('cancels in-flight ownership before the shutdown release phase completes', async () => {
    const scope = createScope({ label: 'project-attachment-manager-test' });
    const availability = createHostAvailability({
      scope,
      readiness: { prepare: async () => ok() },
    });
    const project = sshProject();
    const provider = projectProvider();
    const opened = deferred<ReturnType<typeof ok<ProjectProvider>>>();
    const manager = createProjectAttachmentManager({
      scope,
      availability,
      adapter: {
        loadProject: async () => project,
        statRepository: async () => ok({ type: 'directory' as const }),
        open: () => opened.promise,
      },
    });
    const owner = createScope({ label: 'project-owner' });
    const state = manager.track(project.id, owner);
    await vi.waitFor(() => expect(peek(state).kind).toBe('attaching'));

    await manager.release();
    opened.resolve(ok(provider));

    await vi.waitFor(() => expect(provider.dispose).toHaveBeenCalledOnce());
    expect(manager.requireAttached(project.id).success).toBe(false);
    expect(peek(state).kind).toBe('absent');

    await manager.dispose();
    await owner.dispose();
    await scope.dispose();
  });
});

type TestSshProject = Extract<Project, { type: 'ssh' }> & {
  host: ReturnType<typeof hostRef>;
};

function sshProject(): TestSshProject {
  return {
    type: 'ssh',
    id: 'project-1',
    name: 'Project',
    path: '/repo',
    baseRef: 'main',
    connectionId: 'ssh-1',
    repositoryWorkspaceId: 'repository-1',
    createdAt: '2026-08-13T00:00:00.000Z',
    updatedAt: '2026-08-13T00:00:00.000Z',
    host: hostRef('remote', 'ssh-1'),
  };
}

function localProject(): Project & { host: typeof LOCAL_HOST_REF } {
  return {
    type: 'local',
    id: 'local-project',
    name: 'Local Project',
    path: '/repo',
    baseRef: 'main',
    repositoryWorkspaceId: 'repository-1',
    createdAt: '2026-08-13T00:00:00.000Z',
    updatedAt: '2026-08-13T00:00:00.000Z',
    host: LOCAL_HOST_REF,
  };
}

function projectProvider(): ProjectProvider {
  return {
    release: vi.fn(),
    dispose: vi.fn(),
  } as unknown as ProjectProvider;
}

function runtimeConnection(call: Connection['call']): Connection {
  return {
    call,
    openBlobConsumer: vi.fn(),
    openBlobProducer: vi.fn(),
    snapshot: vi.fn(),
    attach: vi.fn(),
    onDisconnect: vi.fn(() => () => {}),
    dispose: vi.fn(),
  } as unknown as Connection;
}

async function expectAttachmentFailure(options: {
  project: TestSshProject;
  statRepository: ProjectAttachmentAdapter['statRepository'];
  open?: ProjectAttachmentAdapter['open'];
  expected: object;
}): Promise<void> {
  const scope = createScope({ label: 'project-attachment-failure-test' });
  const availability = createHostAvailability({
    scope,
    readiness: { prepare: async () => ok() },
  });
  const manager = createProjectAttachmentManager({
    scope,
    availability,
    adapter: {
      loadProject: async () => options.project,
      statRepository: options.statRepository,
      open: options.open ?? (async () => ok(projectProvider())),
    },
  });
  const owner = createScope({ label: 'project-owner' });
  const state = manager.track(options.project.id, owner);

  await vi.waitFor(() =>
    expect(peek(state)).toEqual({
      kind: 'absent',
      lastFailure: options.expected,
      attemptedHostGeneration: 1,
    })
  );
  expect(manager.requireAttached(options.project.id)).toEqual(err(options.expected));

  await owner.dispose();
  await scope.dispose();
}
