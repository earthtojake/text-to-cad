import { ok } from '@emdash/shared';
import {
  createEventStreamHost,
  LiveJobCancelledError,
  LiveJobFailedError,
} from '@emdash/wire/live';
import type * as WireLive from '@emdash/wire/live';
import { cell, expose } from '@emdash/wire/state';
import { createTestWire } from '@emdash/wire/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  projectsWireContract,
  type ProjectAttachmentState,
  type ProjectCreationProgress,
  type ProjectListData,
} from '@core/features/projects/api';
import {
  createRegisteredProject,
  createUnregisteredProject,
  isUnregisteredProject,
} from '@core/features/projects/api/browser/stores/project';
import { ProjectManagerStore as BrowserProjectManagerStore } from '@core/features/projects/api/browser/stores/project-manager';
import type { ProjectScopedStoreContext } from '@core/features/projects/contributions/project-stores';
import { taskManagerStoreToken } from '@core/features/tasks/contributions/browser/project-store-tokens';
import type { LocalProject, SshProject } from '@core/primitives/projects/api';
import type { ScopedStoreContribution } from '@core/primitives/scoped-stores/browser';
import { hostsContract, type HostAvailabilityState } from '@core/services/hosts/api';

const mocks = vi.hoisted(() => ({
  attachmentTrack: vi.fn(),
  hostAvailabilityTrack: vi.fn(),
  createGithubRepository: vi.fn(),
  createLiveJobReplicaCache: vi.fn(),
  createProject: vi.fn(),
  deleteGithubRepository: vi.fn(),
  inspectProjectPath: vi.fn(),
  logError: vi.fn(),
  projectWireCreate: vi.fn(),
  projectWireCancel: vi.fn(),
  projectWireDelete: vi.fn(),
  projectWireProgressCallbacks: [] as Array<(progress: ProjectCreationProgress) => void>,
  projectWireResult: undefined as Promise<LocalProject | SshProject> | undefined,
  recoverAttachment: vi.fn(),
  resolveRepositoryDestination: vi.fn(),
  deleteMementoSubject: vi.fn(),
  mementoReportError: vi.fn(),
  mementoSubject: vi.fn(),
  mementoSubjectRelease: vi.fn(),
  projectContextStoreDispose: vi.fn(),
  contextReady: Promise.resolve(),
  navigationCurrentRef: { viewId: 'home', params: {}, key: 'home' } as {
    viewId: string;
    params: Record<string, string>;
    key: string;
  },
  navigationHistoryPrune: vi.fn(),
  navigationInvalidateSubject: vi.fn(),
  navigationNavigate: vi.fn(),
  taskListLoad: vi.fn(),
  taskProvision: vi.fn(),
  updateProjectConnection: vi.fn(),
  updateProjectSettings: vi.fn(),
}));

let projectListState: ReturnType<typeof cell<ProjectListData>>;
let attachmentState: ReturnType<typeof cell<ProjectAttachmentState>>;
let wire: ReturnType<typeof createProjectWire> | undefined;
let hostAvailabilityState: ReturnType<typeof cell<HostAvailabilityState>>;
let hostsWire: ReturnType<typeof createHostsWire> | undefined;

const projectStoreContributions = [
  {
    token: taskManagerStoreToken,
    create: () => ({
      tasks: new Map(),
      loadTasks: mocks.taskListLoad,
      provisionTask: mocks.taskProvision,
    }),
    dispose: mocks.projectContextStoreDispose,
  },
] satisfies readonly ScopedStoreContribution<ProjectScopedStoreContext>[];

class ProjectManagerStore extends BrowserProjectManagerStore {
  constructor() {
    super(projectStoreContributions);
  }
}

vi.mock('@core/features/github/api/browser/client', () => ({
  getGithubClient: async () => ({
    createRepository: mocks.createGithubRepository,
    deleteRepository: mocks.deleteGithubRepository,
  }),
}));

vi.mock('@emdash/wire/live', async (importOriginal) => {
  const actual = await importOriginal<typeof WireLive>();
  return {
    ...actual,
    createLiveJobReplicaCache: mocks.createLiveJobReplicaCache,
  };
});

vi.mock('@core/features/projects/api/browser/client', () => ({
  getProjectsWireClient: async () => wire!.client,
}));

vi.mock('@core/services/hosts/api/client', () => ({
  getHostsClient: async () => hostsWire!.client,
}));

vi.mock('@core/primitives/mementos/browser', () => ({
  getMementoClient: () => ({
    deleteBySubject: mocks.deleteMementoSubject,
    reportError: mocks.mementoReportError,
    subject: mocks.mementoSubject,
  }),
}));

vi.mock('@core/primitives/navigation/browser/navigation-selectors', () => ({
  getNavigation: () => ({
    currentViewId: 'home',
    get currentRef() {
      return mocks.navigationCurrentRef;
    },
    navigate: mocks.navigationNavigate,
    invalidateSubject: mocks.navigationInvalidateSubject,
  }),
  getNavigationHistory: () => ({ prune: mocks.navigationHistoryPrune }),
}));

vi.mock('@core/features/conversations/browser/acp/acp-chat-store', () => ({
  AcpChatStore: class {
    conversationId = '';
    dispose() {}
    bootstrap() {}
  },
}));

vi.mock('@core/features/conversations/browser/acp/acp-chat-panel', () => ({
  AcpChatPanel: () => null,
}));

vi.mock('@core/primitives/telemetry/browser/telemetry-client', () => ({
  captureTelemetry: vi.fn(),
}));

vi.mock('@core/primitives/logging/browser/logger', () => ({
  log: { error: mocks.logError, info: vi.fn() },
}));

function localProject(overrides: Partial<LocalProject> = {}): LocalProject {
  return {
    type: 'local',
    id: 'project-id',
    name: 'Project',
    path: '/project',
    baseRef: 'main',
    repositoryWorkspaceId: null,
    createdAt: '2026-05-28T00:00:00.000Z',
    updatedAt: '2026-05-28T00:00:00.000Z',
    ...overrides,
  };
}

function sshProject(overrides: Partial<SshProject> = {}): SshProject {
  return {
    type: 'ssh',
    id: 'ssh-project-id',
    name: 'SSH Project',
    path: '/project',
    baseRef: 'main',
    connectionId: 'ssh-1',
    repositoryWorkspaceId: null,
    createdAt: '2026-05-28T00:00:00.000Z',
    updatedAt: '2026-05-28T00:00:00.000Z',
    ...overrides,
  };
}

function okProject(project: LocalProject) {
  return { success: true as const, data: project };
}

describe('ProjectManagerStore contract', () => {
  it('does not expose renderer-driven Project mounting', () => {
    const manager = new ProjectManagerStore();
    expect(manager).not.toHaveProperty('mountProject');
    manager.dispose();
  });
});

function createProjectWire() {
  const events = createEventStreamHost(projectsWireContract.events);
  const projectListProvider = expose(projectsWireContract.projectList, {
    list: projectListState,
  });
  const projectConfigProvider = expose(projectsWireContract.projectConfig, {
    current: () => cell(undefined as never),
  });
  const creationProvider = expose(projectsWireContract.creation, {
    state: () => cell({ phase: 'error' as const, message: 'unused' }),
  });
  const directoryTreeProvider = expose(projectsWireContract.directoryTree, {
    tree: () => cell(undefined as never),
  });
  const attachmentsProvider = expose(projectsWireContract.attachments, {
    state: (key) => {
      mocks.attachmentTrack(key);
      return attachmentState;
    },
  });
  const testWire = createTestWire(projectsWireContract, {
    createProject: (input: unknown) => mocks.createProject(input),
    inspectProjectPath: (input: unknown) => mocks.inspectProjectPath(input),
    initializeRepository: vi.fn(),
    getHostHomeDir: vi.fn(),
    getDefaultRepositoriesRoot: vi.fn(),
    ensureDefaultRepositoriesRoot: vi.fn(),
    createHostDirectory: vi.fn(),
    resolveRepositoryDestination: (input: unknown) => mocks.resolveRepositoryDestination(input),
    deleteProject: vi.fn(),
    getProjectSettingsPage: vi.fn(),
    shareProjectSettingsToConfig: vi.fn(),
    migrateProjectConfig: vi.fn(),
    countProjectsUsingGithubAccount: vi.fn(),
    recoverAttachment: (input: unknown) => mocks.recoverAttachment(input),
    events,
    projectList: projectListProvider,
    attachments: attachmentsProvider,
    projectConfig: projectConfigProvider,
    creation: creationProvider,
    directoryTree: directoryTreeProvider,
    create: {
      run: async () => ({
        success: false as const,
        error: { type: 'unused', message: 'unused' },
      }),
    },
    updateProjectConnection: (input: unknown) => mocks.updateProjectConnection(input),
    updateProjectSettings: (input: unknown) => mocks.updateProjectSettings(input),
    delete: (input: unknown) => mocks.projectWireDelete(input),
  } as never);
  return {
    ...testWire,
    async dispose() {
      await testWire.dispose();
      events.dispose();
    },
  };
}

function createHostsWire() {
  const availabilityProvider = expose(hostsContract.availability, {
    state: (key) => {
      mocks.hostAvailabilityTrack(key);
      return hostAvailabilityState;
    },
  });
  return createTestWire(hostsContract, {
    availability: availabilityProvider,
    disconnect: vi.fn(),
    requestReady: vi.fn(),
    serverStates: expose(hostsContract.serverStates, {
      runtime: () => cell({}),
    }),
    refreshServerState: vi.fn(),
    installServer: vi.fn(),
    startServer: vi.fn(),
    stopServer: vi.fn(),
    restartServer: vi.fn(),
    updateServer: vi.fn(),
  });
}

describe('ProjectManagerStore project creation', () => {
  afterEach(async () => {
    await wire?.dispose();
    wire = undefined;
    await hostsWire?.dispose();
    hostsWire = undefined;
    vi.unstubAllGlobals();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.navigationCurrentRef = { viewId: 'home', params: {}, key: 'home' };
    projectListState = cell({ projects: [] });
    attachmentState = cell({ kind: 'absent' });
    wire = createProjectWire();
    hostAvailabilityState = cell({ kind: 'unavailable', recovery: 'eligible' });
    hostsWire = createHostsWire();
    mocks.inspectProjectPath.mockResolvedValue({ isDirectory: true, isGitRepo: true });
    mocks.resolveRepositoryDestination.mockImplementation(
      async ({ chosenDir, name }: { chosenDir: string; name: string }) =>
        ({ success: true, data: `${chosenDir}/${name}` }) as const
    );
    mocks.createProject.mockResolvedValue(okProject(localProject()));
    mocks.contextReady = Promise.resolve();
    mocks.mementoSubject.mockImplementation(() => ({
      ready: mocks.contextReady,
      release: mocks.mementoSubjectRelease,
    }));
    mocks.mementoSubjectRelease.mockResolvedValue(undefined);
    mocks.taskListLoad.mockResolvedValue(undefined);
    mocks.taskProvision.mockResolvedValue(undefined);
    mocks.updateProjectConnection.mockResolvedValue(undefined);
    mocks.projectWireProgressCallbacks.length = 0;
    mocks.projectWireCancel.mockResolvedValue(undefined);
    mocks.projectWireDelete.mockResolvedValue({ success: true, data: {} });
    mocks.recoverAttachment.mockResolvedValue(ok());
    mocks.deleteMementoSubject.mockResolvedValue(1);
    mocks.projectWireResult = undefined;
    mocks.createLiveJobReplicaCache.mockReturnValue({
      start: async (input: {
        projectId: string;
        host: { type: 'local' } | { type: 'ssh'; connectionId: string };
        targetPath: string;
        name: string;
        repositoryUrl: string;
      }) => {
        mocks.projectWireCreate(input);
        return {
          ready: async () => ({
            result:
              mocks.projectWireResult ??
              Promise.resolve(
                input.host.type === 'ssh'
                  ? sshProject({
                      id: input.projectId,
                      name: input.name,
                      path: input.targetPath,
                      connectionId: input.host.connectionId,
                    })
                  : localProject({
                      id: input.projectId,
                      name: input.name,
                      path: input.targetPath,
                    })
              ),
            onProgress: (cb: (progress: ProjectCreationProgress) => void) => {
              mocks.projectWireProgressCallbacks.push(cb);
              return vi.fn();
            },
            cancel: mocks.projectWireCancel,
          }),
          release: async () => {},
        };
      },
      dispose: async () => {},
    });
    mocks.createGithubRepository.mockResolvedValue({
      success: true,
      repoUrl: 'https://github.com/acme/project.git',
      cloneUrl: 'https://github.com/acme/project.git',
      nameWithOwner: 'acme/project',
    });
    mocks.deleteGithubRepository.mockResolvedValue({ success: true });
    mocks.updateProjectSettings.mockResolvedValue({
      success: true,
      data: { githubAccountId: 'github.com:42' },
    });
  });

  it('discards project and child task mementos before disposing a deleted project', async () => {
    const manager = new ProjectManagerStore();
    const dispose = vi.fn();
    const project = createRegisteredProject(localProject());
    project.context = {
      kind: 'available',
      context: {
        get: () => ({
          tasks: new Map([
            ['task-1', {}],
            ['task-2', {}],
          ]),
        }),
        dispose,
      } as never,
    };
    manager.projects.set('project-id', project);

    await manager.deleteProject('project-id');

    expect(mocks.deleteMementoSubject.mock.calls.map(([subject]) => subject)).toEqual([
      { kind: 'project', key: 'project-id' },
      { kind: 'task', key: 'task-1' },
      { kind: 'task', key: 'task-2' },
    ]);
    expect(dispose).toHaveBeenCalledOnce();
    manager.dispose();
  });

  it('disposes an available desktop context after project deletion', async () => {
    const project = localProject();
    projectListState.set({ projects: [project] });
    const manager = new ProjectManagerStore();
    await manager.load();
    await vi.waitFor(() =>
      expect(manager.projects.get(project.id)?.context?.kind).toBe('available')
    );

    await manager.deleteProject(project.id);

    expect(manager.projects.has(project.id)).toBe(false);
    expect(mocks.mementoSubjectRelease).toHaveBeenCalledOnce();
  });

  it('resumes Project-context hydration when deletion rolls back', async () => {
    const project = localProject();
    let resolveHydration = () => {};
    mocks.contextReady = new Promise<void>((resolve) => {
      resolveHydration = resolve;
    });
    mocks.mementoSubject.mockImplementation(() => ({
      ready: mocks.contextReady,
      release: mocks.mementoSubjectRelease,
    }));
    mocks.projectWireDelete.mockRejectedValueOnce(new Error('delete failed'));
    const manager = new ProjectManagerStore();
    projectListState.set({ projects: [project] });
    await manager.load();
    await vi.waitFor(() =>
      expect(manager.projects.get(project.id)?.context?.kind).toBe('hydrating')
    );

    await expect(manager.deleteProject(project.id)).rejects.toThrow('delete failed');
    resolveHydration();
    await vi.waitFor(() =>
      expect(manager.projects.get(project.id)?.context?.kind).toBe('available')
    );
  });

  it('returns an existing project without starting creation', async () => {
    const existingProject = localProject({ id: 'existing-project' });
    mocks.inspectProjectPath.mockResolvedValueOnce({
      isDirectory: true,
      isGitRepo: true,
      existingProject,
    });
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'local' },
      { mode: 'pick', name: 'Project', path: '/project' },
      { id: 'optimistic-project' }
    );

    expect(result).toEqual({ kind: 'existing', projectId: 'existing-project' });
    expect(mocks.createProject).not.toHaveBeenCalled();
    expect(store.projects.has('optimistic-project')).toBe(false);
    expect(store.pendingCreationIds.has('optimistic-project')).toBe(false);
  });

  it('creates unregistered project state before returning creating', async () => {
    let resolveCreateProject: (project: LocalProject) => void = () => {};
    mocks.createProject.mockReturnValueOnce(
      new Promise<ReturnType<typeof okProject>>((resolve) => {
        resolveCreateProject = (project) => resolve(okProject(project));
      })
    );
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'local' },
      { mode: 'pick', name: 'Project', path: '/project' },
      { id: 'optimistic-project' }
    );

    expect(result.kind).toBe('creating');
    const pendingProject = store.projects.get('optimistic-project');
    expect(pendingProject && isUnregisteredProject(pendingProject)).toBe(true);
    expect(pendingProject?.creation).toEqual({ kind: 'running', stage: 'registering' });
    expect(store.pendingCreationIds.has('optimistic-project')).toBe(true);
    expect(mocks.inspectProjectPath).toHaveBeenCalledTimes(1);

    resolveCreateProject(localProject({ id: 'optimistic-project' }));
    if (result.kind === 'creating') await result.completion;

    expect(mocks.inspectProjectPath).toHaveBeenCalledTimes(1);
    expect(store.pendingCreationIds.has('optimistic-project')).toBe(false);
    await vi.waitFor(() =>
      expect(store.projects.get('optimistic-project')?.context?.kind).toBe('available')
    );
  });

  it('keeps one Project context when the live list arrives before creation returns', async () => {
    const project = localProject({ id: 'optimistic-project' });
    let resolveCreation: (result: ReturnType<typeof okProject>) => void = () => {};
    mocks.createProject.mockReturnValueOnce(
      new Promise<ReturnType<typeof okProject>>((resolve) => {
        resolveCreation = resolve;
      })
    );
    let resolveTaskList: () => void = () => {};
    mocks.taskListLoad.mockReturnValueOnce(
      new Promise<void>((resolve) => {
        resolveTaskList = resolve;
      })
    );
    const store = new ProjectManagerStore();

    const creation = await store.startProjectCreation(
      { type: 'local' },
      { mode: 'pick', name: project.name, path: project.path },
      { id: project.id }
    );
    projectListState.set({ projects: [project] });
    const load = store.load();
    await vi.waitFor(() => expect(store.projects.get(project.id)?.context?.kind).toBe('available'));
    const context = store.projects.get(project.id)?.context;

    resolveCreation(okProject(project));
    if (creation.kind === 'creating') await creation.completion;

    expect(store.projects.get(project.id)?.context).toBe(context);
    expect(mocks.mementoSubject).toHaveBeenCalledOnce();

    resolveTaskList();
    await load;
  });

  it('reuses context hydration started by creation when the live list observes it afterward', async () => {
    const project = localProject({ id: 'optimistic-project' });
    mocks.createProject.mockResolvedValueOnce(okProject(project));
    let resolveContext = () => {};
    mocks.contextReady = new Promise<void>((resolve) => {
      resolveContext = resolve;
    });
    mocks.mementoSubject.mockImplementation(() => ({
      ready: mocks.contextReady,
      release: mocks.mementoSubjectRelease,
    }));
    const store = new ProjectManagerStore();

    const creation = await store.startProjectCreation(
      { type: 'local' },
      { mode: 'pick', name: project.name, path: project.path },
      { id: project.id }
    );
    if (creation.kind === 'creating') await creation.completion;
    await vi.waitFor(() => expect(store.projects.get(project.id)?.context?.kind).toBe('hydrating'));

    projectListState.set({ projects: [project] });
    const load = store.load();

    expect(mocks.mementoSubject).toHaveBeenCalledOnce();
    resolveContext();
    await load;
    await vi.waitFor(() => expect(store.projects.get(project.id)?.context?.kind).toBe('available'));
  });

  it('refreshes durable Project data without replacing its context', async () => {
    const project = localProject({ id: 'optimistic-project' });
    mocks.createProject.mockResolvedValueOnce(okProject(project));
    const store = new ProjectManagerStore();

    const creation = await store.startProjectCreation(
      { type: 'local' },
      { mode: 'pick', name: project.name, path: project.path },
      { id: project.id }
    );
    if (creation.kind === 'creating') await creation.completion;
    const registeredStore = store.projects.get(project.id)!;
    await vi.waitFor(() => expect(registeredStore.context?.kind).toBe('available'));
    const context =
      registeredStore.context?.kind === 'available' ? registeredStore.context.context : null;
    const data = registeredStore.data;

    projectListState.set({ projects: [{ ...project, name: 'Renamed Project' }] });
    const load = store.load();
    await load;

    expect(store.projects.get(project.id)).toBe(registeredStore);
    expect(registeredStore.context).toEqual({ kind: 'available', context });
    expect(registeredStore.data).toBe(data);
    expect(registeredStore.name).toBe('Renamed Project');
    expect(registeredStore.data?.name).toBe('Renamed Project');
    expect(mocks.projectContextStoreDispose).not.toHaveBeenCalled();
  });

  it('publishes Project context before background Task hydration finishes', async () => {
    const project = localProject();
    let resolveTaskList: () => void = () => {};
    mocks.taskListLoad.mockReturnValueOnce(
      new Promise<void>((resolve) => {
        resolveTaskList = resolve;
      })
    );
    const store = new ProjectManagerStore();
    projectListState.set({ projects: [project] });
    await store.load();

    await vi.waitFor(() => expect(store.projects.get(project.id)?.context?.kind).toBe('available'));
    resolveTaskList();
  });

  it('hydrates desktop context before retaining attachment tracking', async () => {
    const project = localProject();
    let resolveContextSpace: () => void = () => {};
    mocks.contextReady = new Promise<void>((resolve) => {
      resolveContextSpace = resolve;
    });
    mocks.mementoSubject.mockImplementation(() => ({
      ready: mocks.contextReady,
      release: mocks.mementoSubjectRelease,
    }));
    projectListState.set({ projects: [project] });
    const store = new ProjectManagerStore();

    await store.load();

    expect(store.projects.get(project.id)?.context).toEqual({
      kind: 'hydrating',
      project: store.projects.get(project.id)?.data,
    });
    expect(mocks.attachmentTrack).not.toHaveBeenCalled();
    resolveContextSpace();
    await vi.waitFor(() => expect(store.projects.get(project.id)?.context?.kind).toBe('available'));
    await vi.waitFor(() =>
      expect(mocks.attachmentTrack).toHaveBeenCalledWith({ projectId: project.id })
    );
    await vi.waitFor(() =>
      expect(mocks.hostAvailabilityTrack).toHaveBeenCalledWith({
        host: { type: 'local', id: 'local' },
      })
    );
    expect(mocks.taskListLoad).toHaveBeenCalledOnce();
    expect(store.projects.get(project.id)?.context?.kind).toBe('available');
  });

  it('recovers one Project context through Host readiness and attachment in place', async () => {
    const project = sshProject();
    projectListState.set({ projects: [project] });
    const store = new ProjectManagerStore();
    await store.load();
    await vi.waitFor(() => expect(store.projects.get(project.id)?.context?.kind).toBe('available'));
    const lifecycle = store.projects.get(project.id)?.context;
    if (lifecycle?.kind !== 'available') throw new Error('Expected available Project context');
    const context = lifecycle.context;
    const tasks = context.get(taskManagerStoreToken);
    mocks.recoverAttachment.mockImplementationOnce(async () => {
      hostAvailabilityState.set({
        kind: 'preparing',
        phase: 'connecting',
        attempt: 1,
      });
      return ok();
    });

    await expect(context.host.recover()).resolves.toEqual(ok());

    expect(mocks.recoverAttachment).toHaveBeenCalledWith({ projectId: project.id });
    expect(context.host.requireLive().success).toBe(false);
    await vi.waitFor(() =>
      expect(context.host.state).toEqual({
        kind: 'degraded',
        situation: 'connecting',
        recovery: 'automatic',
      })
    );

    hostAvailabilityState.set({ kind: 'preparing', phase: 'provisioning', attempt: 1 });
    await vi.waitFor(() =>
      expect(context.host.state).toEqual({
        kind: 'degraded',
        situation: 'provisioning',
        recovery: 'automatic',
      })
    );
    hostAvailabilityState.set({ kind: 'preparing', phase: 'handshaking', attempt: 1 });
    await vi.waitFor(() =>
      expect(context.host.state).toEqual({
        kind: 'degraded',
        situation: 'handshaking',
        recovery: 'automatic',
      })
    );
    hostAvailabilityState.set({ kind: 'ready', generation: 1 });
    attachmentState.set({ kind: 'attaching', hostGeneration: 1, attemptId: 'attempt-1' });
    await vi.waitFor(() =>
      expect(context.host.state).toEqual({
        kind: 'degraded',
        situation: 'attaching',
        recovery: 'automatic',
      })
    );
    attachmentState.set({ kind: 'attached', establishedHostGeneration: 1 });
    await vi.waitFor(() =>
      expect(context.host.state).toEqual({ kind: 'ready', hostGeneration: 1 })
    );

    expect(context.host.liveAction).toEqual({ kind: 'enabled' });
    expect(context.host.requireLive()).toEqual(ok());
    expect(store.projects.get(project.id)?.context).toEqual({ kind: 'available', context });
    expect(context.get(taskManagerStoreToken)).toBe(tasks);
  });

  it('rejects stale context hydration after project-list removal', async () => {
    const project = localProject();
    let resolveContextSpace: () => void = () => {};
    mocks.contextReady = new Promise<void>((resolve) => {
      resolveContextSpace = resolve;
    });
    mocks.mementoSubject.mockImplementation(() => ({
      ready: mocks.contextReady,
      release: mocks.mementoSubjectRelease,
    }));
    projectListState.set({ projects: [project] });
    const store = new ProjectManagerStore();
    await store.load();
    expect(store.projects.get(project.id)?.context?.kind).toBe('hydrating');

    projectListState.set({ projects: [] });
    await vi.waitFor(() => expect(store.projects.has(project.id)).toBe(false));
    resolveContextSpace();

    await vi.waitFor(() => expect(mocks.mementoSubjectRelease).toHaveBeenCalledOnce());
    expect(store.projects.has(project.id)).toBe(false);
    expect(mocks.attachmentTrack).not.toHaveBeenCalled();
  });

  it('disposes stale Project context when attachment reports the durable Project missing', async () => {
    const project = localProject();
    projectListState.set({ projects: [project] });
    const store = new ProjectManagerStore();

    await store.load();
    await vi.waitFor(() => expect(store.projects.get(project.id)?.context?.kind).toBe('available'));
    await vi.waitFor(() => expect(mocks.attachmentTrack).toHaveBeenCalledOnce());
    mocks.navigationCurrentRef = {
      viewId: 'project',
      params: { projectId: project.id },
      key: `project:${project.id}`,
    };

    attachmentState.set({
      kind: 'absent',
      lastFailure: { type: 'project-missing', projectId: project.id },
      attemptedHostGeneration: 1,
    });

    await vi.waitFor(() => expect(store.projects.has(project.id)).toBe(false));
    await vi.waitFor(() => expect(mocks.mementoSubjectRelease).toHaveBeenCalledOnce());
    expect(mocks.projectContextStoreDispose).toHaveBeenCalledOnce();
    expect(mocks.navigationNavigate).toHaveBeenCalledWith(
      expect.objectContaining({ viewId: 'home' })
    );
    expect(mocks.navigationInvalidateSubject).toHaveBeenCalledWith({
      kind: 'project',
      key: project.id,
    });
  });

  it('rejects context hydration that completes after project deletion', async () => {
    const project = localProject();
    let resolveContextSpace: () => void = () => {};
    mocks.contextReady = new Promise<void>((resolve) => {
      resolveContextSpace = resolve;
    });
    projectListState.set({ projects: [project] });
    const store = new ProjectManagerStore();
    await store.load();
    expect(store.projects.get(project.id)?.context?.kind).toBe('hydrating');

    await store.deleteProject(project.id);
    resolveContextSpace();

    await vi.waitFor(() => expect(mocks.mementoSubjectRelease).toHaveBeenCalledOnce());
    store.dispose();
    expect(store.projects.has(project.id)).toBe(false);
    expect(mocks.attachmentTrack).not.toHaveBeenCalled();
    expect(mocks.mementoSubjectRelease).toHaveBeenCalledOnce();
  });

  it('publishes typed desktop context failure without tracking attachment', async () => {
    const project = localProject();
    mocks.mementoSubject.mockReturnValue({
      ready: Promise.reject(new Error('memento unavailable')),
      release: mocks.mementoSubjectRelease,
    });
    projectListState.set({ projects: [project] });
    const store = new ProjectManagerStore();

    await store.load();

    await vi.waitFor(() =>
      expect(store.projects.get(project.id)?.context).toEqual({
        kind: 'failed',
        project: store.projects.get(project.id)?.data,
        error: {
          type: 'context-initialization-failed',
          stage: 'memento',
          message: 'memento unavailable',
        },
      })
    );
    expect(mocks.attachmentTrack).not.toHaveBeenCalled();
  });

  it('preserves desktop context and record identity when relinking a project', async () => {
    const project = sshProject();
    projectListState.set({ projects: [project] });
    const store = new ProjectManagerStore();
    await store.load();
    await vi.waitFor(() => expect(store.projects.get(project.id)?.context?.kind).toBe('available'));
    const projectStore = store.projects.get(project.id)!;
    const lifecycle = projectStore.context;
    if (lifecycle?.kind !== 'available') throw new Error('Expected available context');
    const context = lifecycle.context;
    const record = context.project;

    await store.updateProjectConnection(project.id, 'ssh-2');
    await vi.waitFor(() => {
      const current = store.projects.get(project.id);
      expect(current?.data?.type === 'ssh' ? current.data.connectionId : null).toBe('ssh-2');
    });
    await vi.waitFor(() =>
      expect(mocks.hostAvailabilityTrack).toHaveBeenCalledWith({
        host: { type: 'remote', id: 'ssh-2' },
      })
    );

    expect(store.projects.get(project.id)).toBe(projectStore);
    expect(projectStore.context).toEqual({ kind: 'available', context });
    expect(context.project).toBe(record);
    expect(record.type === 'ssh' ? record.connectionId : null).toBe('ssh-2');
  });

  it('inspects the final clone path instead of the parent directory', async () => {
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'local' },
      {
        mode: 'clone',
        name: 'child-project',
        path: '/parent',
        repositoryUrl: 'https://github.com/acme/child-project.git',
      },
      { id: 'optimistic-project' }
    );

    if (result.kind === 'creating') void result.completion;
    expect(mocks.inspectProjectPath).toHaveBeenCalledWith({
      type: 'local',
      path: '/parent/child-project',
    });
  });

  it('uses the destination allocated by the main-process placement policy', async () => {
    mocks.resolveRepositoryDestination.mockResolvedValueOnce({
      success: true,
      data: '/parent/child-project-2',
    });
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'local' },
      {
        mode: 'clone',
        name: 'child-project',
        path: '/parent',
        repositoryUrl: 'https://github.com/acme/child-project.git',
      },
      { id: 'optimistic-project' }
    );

    if (result.kind === 'creating') await result.completion;
    expect(mocks.inspectProjectPath).toHaveBeenCalledWith({
      type: 'local',
      path: '/parent/child-project-2',
    });
    expect(mocks.projectWireCreate).toHaveBeenCalledWith(
      expect.objectContaining({ targetPath: '/parent/child-project-2' })
    );
  });

  it('starts the clone job with an SSH host for remote clones', async () => {
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'ssh', connectionId: 'ssh-1' },
      {
        mode: 'clone',
        name: 'child-project',
        path: '/parent',
        repositoryUrl: 'https://github.com/acme/child-project.git',
      },
      { id: 'optimistic-project' }
    );

    expect(result.kind).toBe('creating');
    if (result.kind === 'creating') {
      await expect(result.completion).resolves.toEqual({ success: true });
    }
    expect(mocks.inspectProjectPath).toHaveBeenCalledWith({
      type: 'ssh',
      connectionId: 'ssh-1',
      path: '/parent/child-project',
    });
    expect(mocks.projectWireCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        host: { type: 'ssh', connectionId: 'ssh-1' },
        targetPath: '/parent/child-project',
      })
    );
    await vi.waitFor(() =>
      expect(store.projects.get('optimistic-project')?.context?.kind).toBe('available')
    );
  });

  it('stores remote creation progress on the pending project', async () => {
    let resolveResult: (project: LocalProject) => void = () => {};
    mocks.projectWireResult = new Promise<LocalProject>((resolve) => {
      resolveResult = resolve;
    });
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'local' },
      {
        mode: 'clone',
        name: 'child-project',
        path: '/parent',
        repositoryUrl: 'https://github.com/acme/child-project.git',
      },
      { id: 'optimistic-project' }
    );

    await vi.waitFor(() => expect(mocks.projectWireProgressCallbacks).toHaveLength(1));

    const progress: ProjectCreationProgress = {
      phase: 'cloning',
      percent: 42,
      message: 'Receiving objects: 42%',
    };
    mocks.projectWireProgressCallbacks[0]?.(progress);

    const pendingProject = store.projects.get('optimistic-project');
    expect(pendingProject && isUnregisteredProject(pendingProject)).toBe(true);
    if (pendingProject && isUnregisteredProject(pendingProject)) {
      expect(pendingProject.creation).toEqual({
        kind: 'running',
        stage: 'cloning',
        progressMessage: 'Receiving objects: 42%',
        progressPercent: 42,
      });
    }

    resolveResult(
      localProject({
        id: 'optimistic-project',
        name: 'child-project',
        path: '/parent/child-project',
      })
    );
    if (result.kind === 'creating') await result.completion;
  });

  it('keeps the first creation failure and its captured stage', () => {
    const project = createUnregisteredProject(
      'optimistic-project',
      'Project',
      { kind: 'running', stage: 'cloning' },
      'clone'
    );

    project.failCreation('Clone failed');
    project.failCreation('Registration failed');

    expect(project.creation).toEqual({
      kind: 'failed',
      stage: 'cloning',
      message: 'Clone failed',
    });
  });

  it('cancels remote creation and removes the pending project', async () => {
    let rejectResult: (error: unknown) => void = () => {};
    mocks.projectWireResult = new Promise<LocalProject>((_, reject) => {
      rejectResult = reject;
    });
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'local' },
      {
        mode: 'clone',
        name: 'child-project',
        path: '/parent',
        repositoryUrl: 'https://github.com/acme/child-project.git',
      },
      { id: 'optimistic-project' }
    );

    await vi.waitFor(() => expect(mocks.projectWireProgressCallbacks).toHaveLength(1));
    store.cancelProjectCreation('optimistic-project');
    rejectResult(new LiveJobCancelledError());

    expect(mocks.projectWireCancel).toHaveBeenCalledOnce();
    if (result.kind === 'creating') {
      await expect(result.completion).resolves.toEqual({
        success: false,
        error: { type: 'cancelled', message: 'Project creation was cancelled' },
      });
    }
    expect(store.projects.has('optimistic-project')).toBe(false);
  });

  it('inspects the final new-project path instead of the parent directory', async () => {
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'local' },
      {
        mode: 'new',
        name: 'child-project',
        path: '/parent',
        repositoryName: 'child-project',
        repositoryOwner: 'acme',
        repositoryVisibility: 'private',
      },
      { id: 'optimistic-project' }
    );

    if (result.kind === 'creating') void result.completion;
    expect(mocks.inspectProjectPath).toHaveBeenCalledWith({
      type: 'local',
      path: '/parent/child-project',
    });
  });

  it('does not let a project registered at the clone parent path short-circuit creation', async () => {
    const parentProject = localProject({ id: 'parent-project', path: '/parent' });
    mocks.inspectProjectPath.mockImplementation(async ({ path }: { path: string }) => ({
      isDirectory: true,
      isGitRepo: true,
      existingProject: path === '/parent' ? parentProject : undefined,
    }));
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'local' },
      {
        mode: 'clone',
        name: 'child-project',
        path: '/parent',
        repositoryUrl: 'https://github.com/acme/child-project.git',
      },
      { id: 'optimistic-project' }
    );

    if (result.kind === 'creating') void result.completion;
    expect(result.kind).toBe('creating');
    expect(store.projects.has('optimistic-project')).toBe(true);
  });

  it('does not let a project registered at the new-project parent path short-circuit creation', async () => {
    const parentProject = localProject({ id: 'parent-project', path: '/parent' });
    mocks.inspectProjectPath.mockImplementation(async ({ path }: { path: string }) => ({
      isDirectory: true,
      isGitRepo: true,
      existingProject: path === '/parent' ? parentProject : undefined,
    }));
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'local' },
      {
        mode: 'new',
        name: 'child-project',
        path: '/parent',
        repositoryName: 'child-project',
        repositoryOwner: 'acme',
        repositoryVisibility: 'private',
      },
      { id: 'optimistic-project' }
    );

    if (result.kind === 'creating') void result.completion;
    expect(result.kind).toBe('creating');
    expect(store.projects.has('optimistic-project')).toBe(true);
  });

  it('persists the selected GitHub account after registering a new project', async () => {
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'local' },
      {
        mode: 'new',
        name: 'Project',
        path: '/parent',
        repositoryName: 'project',
        repositoryOwner: 'acme',
        repositoryVisibility: 'private',
        githubAccountId: 'github.com:42',
      },
      { id: 'optimistic-project' }
    );

    if (result.kind === 'creating') await result.completion;

    expect(mocks.updateProjectSettings).toHaveBeenCalledWith({
      projectId: 'optimistic-project',
      patch: {
        gitIdentity: {
          stored: {
            githubAccount: { kind: 'account', accountId: 'github.com:42' },
          },
        },
      },
    });
    await vi.waitFor(() =>
      expect(store.projects.get('optimistic-project')?.context?.kind).toBe('available')
    );
  });

  it('does not write GitHub account settings when creation did not specify one', async () => {
    mocks.createProject.mockResolvedValueOnce(
      okProject(localProject({ id: 'optimistic-project' }))
    );
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'local' },
      { mode: 'pick', name: 'Project', path: '/project' },
      { id: 'optimistic-project' }
    );

    if (result.kind === 'creating') await result.completion;

    expect(mocks.updateProjectSettings).not.toHaveBeenCalled();
  });

  it('marks project creation as failed when the project RPC returns a typed error', async () => {
    mocks.createProject.mockResolvedValueOnce({
      success: false,
      error: {
        type: 'not-repository',
        path: '/project',
      },
    });
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'local' },
      { mode: 'pick', name: 'Project', path: '/project' },
      { id: 'optimistic-project' }
    );

    expect(result.kind).toBe('creating');
    if (result.kind === 'creating') {
      await expect(result.completion).resolves.toEqual({
        success: false,
        error: { type: 'not-repository', path: '/project' },
      });
    }

    const project = store.projects.get('optimistic-project');
    expect(project && isUnregisteredProject(project)).toBe(true);
    if (project && isUnregisteredProject(project)) {
      expect(project.creation).toEqual({
        kind: 'failed',
        stage: 'registering',
        message:
          'Directory is not a git repository. Enable "Initialize git repository" to continue.',
      });
    }
  });

  it('marks project creation with an inspection failure message', async () => {
    mocks.createProject.mockResolvedValueOnce({
      success: false,
      error: {
        type: 'inspect-failed',
        path: '/Volumes/Data/dev/myapp',
        message: 'Permission denied',
      },
    });
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'local' },
      { mode: 'pick', name: 'Project', path: '/Volumes/Data/dev/myapp' },
      { id: 'optimistic-project' }
    );

    expect(result.kind).toBe('creating');
    if (result.kind === 'creating') {
      await expect(result.completion).resolves.toEqual({
        success: false,
        error: {
          type: 'inspect-failed',
          path: '/Volumes/Data/dev/myapp',
          message: 'Permission denied',
        },
      });
    }

    const project = store.projects.get('optimistic-project');
    expect(project && isUnregisteredProject(project)).toBe(true);
    if (project && isUnregisteredProject(project)) {
      expect(project.creation).toEqual({
        kind: 'failed',
        stage: 'registering',
        message: 'Could not inspect directory: Permission denied',
      });
    }
  });

  it('persists the default GitHub account after initializing a picked folder', async () => {
    mocks.createProject.mockResolvedValueOnce(
      okProject(localProject({ id: 'optimistic-project' }))
    );
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'local' },
      {
        mode: 'pick',
        name: 'Project',
        path: '/project',
        initGitRepository: true,
        githubAccountId: 'github.com:42',
      },
      { id: 'optimistic-project' }
    );

    if (result.kind === 'creating') await result.completion;

    expect(mocks.updateProjectSettings).toHaveBeenCalledWith({
      projectId: 'optimistic-project',
      patch: {
        gitIdentity: {
          stored: {
            githubAccount: { kind: 'account', accountId: 'github.com:42' },
          },
        },
      },
    });
  });

  it('does not persist a GitHub account for picked repositories that were already git repos', async () => {
    mocks.createProject.mockResolvedValueOnce(
      okProject(localProject({ id: 'optimistic-project' }))
    );
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'local' },
      {
        mode: 'pick',
        name: 'Project',
        path: '/project',
        githubAccountId: 'github.com:42',
      },
      { id: 'optimistic-project' }
    );

    if (result.kind === 'creating') await result.completion;

    expect(mocks.updateProjectSettings).not.toHaveBeenCalled();
  });

  it('uses the selected GitHub account when creating a repository for a new project', async () => {
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'local' },
      {
        mode: 'new',
        name: 'Project',
        path: '/parent',
        repositoryName: 'project',
        repositoryOwner: 'acme',
        repositoryVisibility: 'private',
        githubAccountId: 'github.com:42',
      },
      { id: 'optimistic-project' }
    );

    if (result.kind === 'creating') void result.completion;

    await vi.waitFor(() =>
      expect(mocks.createGithubRepository).toHaveBeenCalledWith(
        expect.objectContaining({ accountId: 'github.com:42' })
      )
    );
  });

  it('clones a newly created repository from the API-provided clone URL', async () => {
    mocks.createGithubRepository.mockResolvedValueOnce({
      success: true,
      repoUrl: 'https://ghe.example.com/acme/project',
      cloneUrl: 'https://ghe.example.com/acme/project.git',
      nameWithOwner: 'acme/project',
    });
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'local' },
      {
        mode: 'new',
        name: 'Project',
        path: '/parent',
        repositoryName: 'project',
        repositoryOwner: 'acme',
        repositoryVisibility: 'private',
        githubAccountId: 'ghe.example.com:168',
      },
      { id: 'optimistic-project' }
    );

    if (result.kind === 'creating') await result.completion;

    expect(mocks.projectWireCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        repositoryUrl: 'https://ghe.example.com/acme/project.git',
        targetPath: '/parent/Project',
      })
    );
  });

  it('deletes a newly created GitHub repository with the selected account if clone fails', async () => {
    let rejectResult: (error: unknown) => void = () => {};
    mocks.projectWireResult = new Promise<LocalProject>((_, reject) => {
      rejectResult = reject;
    });
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'local' },
      {
        mode: 'new',
        name: 'Project',
        path: '/parent',
        repositoryName: 'project',
        repositoryOwner: 'acme',
        repositoryVisibility: 'private',
        githubAccountId: 'github.com:42',
      },
      { id: 'optimistic-project' }
    );

    expect(result.kind).toBe('creating');
    await vi.waitFor(() => expect(mocks.projectWireProgressCallbacks).toHaveLength(1));
    mocks.projectWireProgressCallbacks[0]?.({ phase: 'cloning' });
    rejectResult(new LiveJobFailedError({ type: 'clone-failed', message: 'Clone failed' }));
    if (result.kind === 'creating') {
      await expect(result.completion).resolves.toEqual({
        success: false,
        error: { type: 'clone-failed', message: 'Clone failed' },
      });
    }
    expect(store.projects.get('optimistic-project')?.creation).toEqual({
      kind: 'failed',
      stage: 'cloning',
      message: 'Clone failed',
    });

    expect(mocks.deleteGithubRepository).toHaveBeenCalledWith({
      owner: 'acme',
      name: 'project',
      accountId: 'github.com:42',
    });
    expect(mocks.createProject).not.toHaveBeenCalled();
  });

  it('starts new-project cloning on the SSH host and rolls back GitHub if it fails', async () => {
    mocks.projectWireResult = Promise.reject(
      new LiveJobFailedError({ type: 'clone-failed', message: 'Remote clone failed' })
    );
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'ssh', connectionId: 'ssh-1' },
      {
        mode: 'new',
        name: 'Project',
        path: '/remote/parent',
        repositoryName: 'project',
        repositoryOwner: 'acme',
        repositoryVisibility: 'private',
        githubAccountId: 'github.com:42',
      },
      { id: 'optimistic-project' }
    );

    expect(result.kind).toBe('creating');
    if (result.kind === 'creating') {
      await expect(result.completion).resolves.toEqual({
        success: false,
        error: { type: 'clone-failed', message: 'Remote clone failed' },
      });
    }

    expect(mocks.inspectProjectPath).toHaveBeenCalledWith({
      type: 'ssh',
      connectionId: 'ssh-1',
      path: '/remote/parent/Project',
    });
    expect(mocks.projectWireCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        host: { type: 'ssh', connectionId: 'ssh-1' },
        mode: 'new',
        repositoryUrl: 'https://github.com/acme/project.git',
        targetPath: '/remote/parent/Project',
      })
    );
    expect(mocks.deleteGithubRepository).toHaveBeenCalledWith({
      owner: 'acme',
      name: 'project',
      accountId: 'github.com:42',
    });
  });

  it('does not attempt GitHub repository rollback when repository creation fails', async () => {
    mocks.createGithubRepository.mockResolvedValueOnce({
      success: false,
      error: 'Repository creation failed',
    });
    const store = new ProjectManagerStore();

    const result = await store.startProjectCreation(
      { type: 'local' },
      {
        mode: 'new',
        name: 'Project',
        path: '/parent',
        repositoryName: 'project',
        repositoryOwner: 'acme',
        repositoryVisibility: 'private',
        githubAccountId: 'github.com:42',
      },
      { id: 'optimistic-project' }
    );

    expect(result.kind).toBe('creating');
    if (result.kind === 'creating') {
      await expect(result.completion).resolves.toEqual({
        success: false,
        error: { type: 'repository-create-failed', message: 'Repository creation failed' },
      });
    }

    expect(mocks.deleteGithubRepository).not.toHaveBeenCalled();
  });
});
