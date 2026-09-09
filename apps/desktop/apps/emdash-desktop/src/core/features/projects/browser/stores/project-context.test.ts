import { ok } from '@emdash/shared';
import { deferred } from '@emdash/shared/testing';
import { cell, flushStateTurn, type RemoteModel } from '@emdash/wire/state';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProjectAttachmentState, projectsWireContract } from '@core/features/projects/api';
import { ProjectContext as BrowserProjectContext } from '@core/features/projects/browser/stores/project-context';
import type { ProjectScopedStoreContext } from '@core/features/projects/contributions/project-stores';
import {
  contributeScopedStore,
  scopedStoreToken,
  type ScopedStoreContribution,
} from '@core/primitives/scoped-stores/browser';
import type { hostsContract, HostAvailabilityState } from '@core/services/hosts/api';

const mocks = vi.hoisted(() => ({
  mementoReportError: vi.fn(),
  mementoSubject: vi.fn(),
  projectStoreContributions: [] as ScopedStoreContribution<ProjectScopedStoreContext>[],
}));

vi.mock('@core/primitives/mementos/browser', () => ({
  getMementoClient: () => ({
    reportError: mocks.mementoReportError,
    subject: mocks.mementoSubject,
  }),
}));

const ProjectContext = {
  hydrate: (record: unknown) =>
    BrowserProjectContext.hydrate(record, mocks.projectStoreContributions),
};

function availabilityModel(
  state: HostAvailabilityState | ReturnType<typeof cell<HostAvailabilityState>> = {
    kind: 'ready',
    generation: 1,
  },
  onRelease: () => void = () => {}
): RemoteModel<typeof hostsContract.availability> {
  const availability = 'set' in state ? state : cell(state);
  const member = {
    states: { state: availability },
    mutations: {},
  };
  return Object.assign(() => member, {
    retain: vi.fn(() => onRelease),
    peekMember: vi.fn(() => member),
    dispose: vi.fn(async () => {}),
  }) as unknown as RemoteModel<typeof hostsContract.availability>;
}

function attachmentModel(
  state: ProjectAttachmentState | ReturnType<typeof cell<ProjectAttachmentState>> = {
    kind: 'absent',
  }
): RemoteModel<typeof projectsWireContract.attachments> {
  const attachment = 'set' in state ? state : cell(state);
  const member = {
    states: { state: attachment },
    mutations: {},
  };
  return Object.assign(() => member, {
    retain: vi.fn(() => vi.fn()),
    peekMember: vi.fn(() => member),
    dispose: vi.fn(async () => {}),
  }) as unknown as RemoteModel<typeof projectsWireContract.attachments>;
}

describe('ProjectContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.projectStoreContributions.length = 0;
  });

  it('rejects an invalid durable record before acquiring desktop resources', async () => {
    const result = await ProjectContext.hydrate({
      type: 'ssh',
      id: 'project-id',
      name: 'Project',
      connectionId: 'ssh-1',
    });

    expect(result).toEqual({
      success: false,
      error: {
        type: 'invalid-project-record',
        message: expect.any(String),
      },
    });
    expect(mocks.mementoSubject).not.toHaveBeenCalled();
  });

  it('hydrates one desktop space and activates stores only after readiness', async () => {
    const events: string[] = [];
    let resolveSpace: () => void = () => {};
    let resolveStore: () => void = () => {};
    const space = {
      ready: new Promise<void>((resolve) => {
        resolveSpace = () => {
          events.push('space:ready');
          resolve();
        };
      }),
      release: vi.fn(),
    };
    const token = scopedStoreToken<{ id: string }>('test.store');
    let scopedHost: unknown;
    mocks.projectStoreContributions.push(
      contributeScopedStore({
        token,
        create: (context: { host: unknown }) => {
          scopedHost = context.host;
          events.push('store:create');
          return { id: 'store' };
        },
        ready: () =>
          new Promise<void>((resolve) => {
            resolveStore = () => {
              events.push('store:ready');
              resolve();
            };
          }),
        activate: () => events.push('store:activate'),
      })
    );
    mocks.mementoSubject.mockReturnValue(space);

    const hydration = ProjectContext.hydrate({
      type: 'local',
      id: 'project-id',
      name: 'Project',
      path: '/project',
      baseRef: 'main',
      repositoryWorkspaceId: null,
      createdAt: '2026-08-13T00:00:00.000Z',
      updatedAt: '2026-08-13T00:00:00.000Z',
    });

    expect(events).toEqual(['store:create']);
    resolveStore();
    await Promise.resolve();
    expect(events).toEqual(['store:create', 'store:ready']);
    resolveSpace();
    const result = await hydration;

    expect(result.success).toBe(true);
    if (!result.success) return;
    expect(events).toEqual(['store:create', 'store:ready', 'space:ready', 'store:activate']);
    expect(mocks.mementoSubject).toHaveBeenCalledOnce();
    expect(result.data.get(token)).toEqual({ id: 'store' });
    expect(scopedHost).toBe(result.data.host);
  });

  it('classifies memento hydration failure as a desktop context error', async () => {
    const release = vi.fn().mockResolvedValue(undefined);
    mocks.mementoSubject.mockReturnValue({
      ready: Promise.reject(new Error('memento unavailable')),
      release,
    });

    const result = await ProjectContext.hydrate({
      type: 'local',
      id: 'project-id',
      name: 'Project',
      path: '/project',
      baseRef: 'main',
      repositoryWorkspaceId: null,
      createdAt: '2026-08-13T00:00:00.000Z',
      updatedAt: '2026-08-13T00:00:00.000Z',
    });

    expect(result).toEqual({
      success: false,
      error: {
        type: 'context-initialization-failed',
        stage: 'memento',
        message: 'memento unavailable',
      },
    });
    expect(release).toHaveBeenCalledOnce();
  });

  it('classifies scoped-store readiness failure as a desktop context error', async () => {
    const release = vi.fn().mockResolvedValue(undefined);
    const dispose = vi.fn();
    mocks.mementoSubject.mockReturnValue({
      ready: Promise.resolve(),
      release,
    });
    mocks.projectStoreContributions.push(
      contributeScopedStore({
        token: scopedStoreToken('test.failing'),
        create: () => ({}),
        ready: async () => {
          throw new Error('store unavailable');
        },
        dispose,
      })
    );

    const result = await ProjectContext.hydrate({
      type: 'local',
      id: 'project-id',
      name: 'Project',
      path: '/project',
      baseRef: 'main',
      repositoryWorkspaceId: null,
      createdAt: '2026-08-13T00:00:00.000Z',
      updatedAt: '2026-08-13T00:00:00.000Z',
    });

    expect(result).toEqual({
      success: false,
      error: {
        type: 'context-initialization-failed',
        stage: 'scoped-stores',
        message: 'store unavailable',
      },
    });
    expect(dispose).toHaveBeenCalledOnce();
    expect(release).toHaveBeenCalledOnce();
  });

  it('releases attachment tracking before stores and the subject space', async () => {
    const events: string[] = [];
    const releaseSpace = vi.fn(async () => {
      events.push('space:release');
    });
    mocks.mementoSubject.mockReturnValue({
      ready: Promise.resolve(),
      release: releaseSpace,
    });
    mocks.projectStoreContributions.push(
      contributeScopedStore({
        token: scopedStoreToken('test.disposable'),
        create: () => ({}),
        dispose: () => events.push('store:dispose'),
      })
    );
    const result = await ProjectContext.hydrate({
      type: 'local',
      id: 'project-id',
      name: 'Project',
      path: '/project',
      baseRef: 'main',
      repositoryWorkspaceId: null,
      createdAt: '2026-08-13T00:00:00.000Z',
      updatedAt: '2026-08-13T00:00:00.000Z',
    });
    if (!result.success) throw new Error('Expected context hydration to succeed');
    const attachment = cell<ProjectAttachmentState>({ kind: 'absent' });
    const member = {
      states: { state: attachment },
      mutations: {},
    };
    const model = Object.assign(() => member, {
      retain: vi.fn(() => () => events.push('attachment:release')),
      peekMember: vi.fn(() => member),
      dispose: vi.fn(async () => {}),
    }) as unknown as RemoteModel<typeof projectsWireContract.attachments>;

    result.data.trackHostAccess(
      availabilityModel({ kind: 'ready', generation: 1 }, () =>
        events.push('availability:release')
      ),
      model
    );
    expect(result.data.host.state).toEqual({
      kind: 'degraded',
      situation: 'attaching',
      recovery: 'automatic',
    });
    await result.data.dispose();
    await result.data.dispose();

    expect(events).toEqual([
      'attachment:release',
      'availability:release',
      'store:dispose',
      'space:release',
    ]);
    expect(result.data.host.state).toEqual({
      kind: 'degraded',
      situation: 'offline',
      recovery: 'automatic',
    });
    expect(model.retain).toHaveBeenCalledOnce();
    expect(releaseSpace).toHaveBeenCalledOnce();
  });

  it('does not release the old attachment twice when replacement binding fails', async () => {
    mocks.mementoSubject.mockReturnValue({
      ready: Promise.resolve(),
      release: vi.fn().mockResolvedValue(undefined),
    });
    const result = await ProjectContext.hydrate({
      type: 'local',
      id: 'project-id',
      name: 'Project',
      path: '/project',
      baseRef: 'main',
      repositoryWorkspaceId: null,
      createdAt: '2026-08-13T00:00:00.000Z',
      updatedAt: '2026-08-13T00:00:00.000Z',
    });
    if (!result.success) throw new Error('Expected context hydration to succeed');
    const firstRelease = vi.fn();
    const firstState = cell({ kind: 'absent' as const });
    const firstModel = Object.assign(() => ({ states: { state: firstState }, mutations: {} }), {
      retain: vi.fn(() => firstRelease),
      peekMember: vi.fn(),
      dispose: vi.fn(async () => {}),
    }) as unknown as RemoteModel<typeof projectsWireContract.attachments>;
    const failedRelease = vi.fn();
    const failedModel = Object.assign(
      () => {
        throw new Error('binding failed');
      },
      {
        retain: vi.fn(() => failedRelease),
        peekMember: vi.fn(),
        dispose: vi.fn(async () => {}),
      }
    ) as unknown as RemoteModel<typeof projectsWireContract.attachments>;

    result.data.trackHostAccess(availabilityModel(), firstModel);
    expect(() => result.data.trackHostAccess(availabilityModel(), failedModel)).toThrow(
      'binding failed'
    );
    await result.data.dispose();

    expect(firstRelease).toHaveBeenCalledOnce();
    expect(failedRelease).toHaveBeenCalledOnce();
    expect(result.data.host.state).toEqual({
      kind: 'degraded',
      situation: 'offline',
      recovery: 'automatic',
    });
  });

  it('derives live Host access without replacing the Project context', async () => {
    mocks.mementoSubject.mockReturnValue({
      ready: Promise.resolve(),
      release: vi.fn().mockResolvedValue(undefined),
    });
    const result = await ProjectContext.hydrate({
      type: 'local',
      id: 'project-id',
      name: 'Project',
      path: '/project',
      baseRef: 'main',
      repositoryWorkspaceId: null,
      createdAt: '2026-08-13T00:00:00.000Z',
      updatedAt: '2026-08-13T00:00:00.000Z',
    });
    if (!result.success) throw new Error('Expected context hydration to succeed');

    const availability = cell<HostAvailabilityState>({
      kind: 'unavailable',
      recovery: 'eligible',
    });
    const availabilityMember = {
      states: { state: availability },
      mutations: {},
    };
    const availabilityModel = Object.assign(() => availabilityMember, {
      retain: vi.fn(() => vi.fn()),
      peekMember: vi.fn(() => availabilityMember),
      dispose: vi.fn(async () => {}),
    }) as unknown as RemoteModel<typeof hostsContract.availability>;
    const attachment = cell<ProjectAttachmentState>({ kind: 'absent' });
    const attachmentMember = {
      states: { state: attachment },
      mutations: {},
    };
    const attachmentModel = Object.assign(() => attachmentMember, {
      retain: vi.fn(() => vi.fn()),
      peekMember: vi.fn(() => attachmentMember),
      dispose: vi.fn(async () => {}),
    }) as unknown as RemoteModel<typeof projectsWireContract.attachments>;
    const context = result.data;

    context.trackHostAccess(availabilityModel, attachmentModel);
    expect(context.host.state).toEqual({
      kind: 'degraded',
      situation: 'offline',
      recovery: 'automatic',
    });

    availability.set({ kind: 'ready', generation: 2 });
    attachment.set({ kind: 'attaching', hostGeneration: 2, attemptId: 'attempt-1' });
    flushStateTurn();
    expect(context.host.state).toEqual({
      kind: 'degraded',
      situation: 'attaching',
      recovery: 'automatic',
    });

    attachment.set({ kind: 'attached', establishedHostGeneration: 2 });
    flushStateTurn();
    expect(context.host.state).toEqual({ kind: 'ready', hostGeneration: 2 });
    expect(
      context.host.observe({ kind: 'observed', value: { linesAdded: 3 }, observedAt: 123 })
    ).toEqual({
      kind: 'fresh',
      value: { linesAdded: 3 },
      observedAt: 123,
    });
    expect(result.data).toBe(context);

    availability.set({ kind: 'suspended', reason: 'user-disconnected' });
    flushStateTurn();
    expect(context.host.state).toEqual({
      kind: 'degraded',
      situation: 'suspended',
      recovery: 'manual',
    });
    expect(
      context.host.observe({ kind: 'observed', value: { linesAdded: 3 }, observedAt: 123 })
    ).toEqual({
      kind: 'stale',
      value: { linesAdded: 3 },
      observedAt: 123,
    });
    expect(context.host.observe({ kind: 'never-observed' })).toEqual({ kind: 'unavailable' });
    expect(result.data).toBe(context);

    availability.set({ kind: 'ready', generation: 3 });
    flushStateTurn();
    expect(context.host.state).toEqual({ kind: 'ready', hostGeneration: 3 });
    expect(
      context.host.observe({ kind: 'observed', value: { linesAdded: 3 }, observedAt: 123 })
    ).toEqual({
      kind: 'fresh',
      value: { linesAdded: 3 },
      observedAt: 123,
    });
    expect(result.data).toBe(context);
  });

  it('acknowledges and coalesces recovery without claiming Host access is live', async () => {
    mocks.mementoSubject.mockReturnValue({
      ready: Promise.resolve(),
      release: vi.fn().mockResolvedValue(undefined),
    });
    const result = await ProjectContext.hydrate({
      type: 'local',
      id: 'project-id',
      name: 'Project',
      path: '/project',
      baseRef: 'main',
      repositoryWorkspaceId: null,
      createdAt: '2026-08-13T00:00:00.000Z',
      updatedAt: '2026-08-13T00:00:00.000Z',
    });
    if (!result.success) throw new Error('Expected context hydration to succeed');
    const request = deferred<ReturnType<typeof ok<void>>>();
    const recover = vi.fn(() => request.promise);
    const context = result.data;

    context.trackHostAccess(
      availabilityModel({ kind: 'unavailable', recovery: 'manual' }),
      attachmentModel(),
      recover
    );

    expect(context.host.liveAction).toEqual({
      kind: 'disabled',
      state: {
        kind: 'degraded',
        situation: 'attention',
        recovery: 'manual',
      },
    });
    expect(context.host.requireLive()).toMatchObject({
      success: false,
      error: { type: 'host-unavailable', reason: 'offline' },
    });

    const first = context.host.recover();
    const repeated = context.host.recover();

    expect(repeated).toBe(first);
    expect(recover).toHaveBeenCalledOnce();
    expect(context.host.state).toEqual({
      kind: 'degraded',
      situation: 'attention',
      recovery: 'manual',
    });
    request.resolve(ok());
    await expect(first).resolves.toEqual(ok());
    expect(context.host.requireLive().success).toBe(false);
  });

  it('maps retained Host observations to unavailable, stale, and fresh without clearing values', async () => {
    mocks.mementoSubject.mockReturnValue({
      ready: Promise.resolve(),
      release: vi.fn().mockResolvedValue(undefined),
    });
    const result = await ProjectContext.hydrate({
      type: 'local',
      id: 'project-id',
      name: 'Project',
      path: '/project',
      baseRef: 'main',
      repositoryWorkspaceId: null,
      createdAt: '2026-08-13T00:00:00.000Z',
      updatedAt: '2026-08-13T00:00:00.000Z',
    });
    if (!result.success) throw new Error('Expected context hydration to succeed');
    const availability = cell<HostAvailabilityState>({
      kind: 'unavailable',
      recovery: 'eligible',
    });
    const attachment = cell<ProjectAttachmentState>({ kind: 'absent' });
    const context = result.data;
    context.trackHostAccess(availabilityModel(availability), attachmentModel(attachment));

    expect(context.host.observe({ kind: 'never-observed' })).toEqual({ kind: 'unavailable' });
    expect(
      context.host.observe({ kind: 'observed', value: ['main'], observedAt: 1_723_500_000_000 })
    ).toEqual({
      kind: 'stale',
      value: ['main'],
      observedAt: 1_723_500_000_000,
    });

    availability.set({ kind: 'ready', generation: 2 });
    attachment.set({ kind: 'attached', establishedHostGeneration: 2 });
    flushStateTurn();
    expect(
      context.host.observe({ kind: 'observed', value: ['main'], observedAt: 1_723_500_000_000 })
    ).toEqual({
      kind: 'fresh',
      value: ['main'],
      observedAt: 1_723_500_000_000,
    });
  });

  it('reports a missing durable Project without publishing a stable banner state', async () => {
    mocks.mementoSubject.mockReturnValue({
      ready: Promise.resolve(),
      release: vi.fn().mockResolvedValue(undefined),
    });
    const result = await ProjectContext.hydrate({
      type: 'local',
      id: 'project-id',
      name: 'Project',
      path: '/project',
      baseRef: 'main',
      repositoryWorkspaceId: null,
      createdAt: '2026-08-13T00:00:00.000Z',
      updatedAt: '2026-08-13T00:00:00.000Z',
    });
    if (!result.success) throw new Error('Expected context hydration to succeed');
    const attachment = cell<ProjectAttachmentState>({
      kind: 'attaching',
      hostGeneration: 2,
      attemptId: 'attempt-1',
    });
    const onProjectMissing = vi.fn();
    const context = result.data;
    const attachmentMember = {
      states: { state: attachment },
      mutations: {},
    };
    const projectAttachmentModel = Object.assign(() => attachmentMember, {
      retain: vi.fn(() => vi.fn()),
      peekMember: vi.fn(() => attachmentMember),
      dispose: vi.fn(async () => {}),
    }) as unknown as RemoteModel<typeof projectsWireContract.attachments>;

    context.trackHostAccess(
      availabilityModel({ kind: 'ready', generation: 2 }),
      projectAttachmentModel,
      undefined,
      onProjectMissing
    );
    expect(context.host.state).toEqual({
      kind: 'degraded',
      situation: 'attaching',
      recovery: 'automatic',
    });

    attachment.set({
      kind: 'absent',
      lastFailure: { type: 'project-missing', projectId: 'project-id' },
      attemptedHostGeneration: 2,
    });
    flushStateTurn();

    expect(onProjectMissing).toHaveBeenCalledOnce();
    expect(context.host.state).toEqual({
      kind: 'degraded',
      situation: 'attaching',
      recovery: 'automatic',
    });
  });
});
