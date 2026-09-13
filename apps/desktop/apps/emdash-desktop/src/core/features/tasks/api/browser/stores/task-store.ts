import { err, type Result } from '@emdash/shared';
import { makeAutoObservable, observable } from 'mobx';
import type { TaskScopedStoreContext } from '@core/features/tasks/contributions/browser/task-stores';
import { taskPersistentStoreContributions } from '@core/manifests/browser/task-persistent-stores';
import { taskStoreContributions } from '@core/manifests/browser/task-scoped-stores';
import type { LinkedIssue } from '@core/primitives/linked-issues/api';
import { log } from '@core/primitives/logging/browser/logger';
import {
  ScopedStoreHost,
  type ScopedStoreLookup,
  type ScopedStoreToken,
  type ScopedStoreValue,
} from '@core/primitives/scoped-stores/browser';
import {
  registeredTaskData,
  type RegisteredTaskData,
  type TaskState,
  type UnprovisionedTaskPhase,
  type UnregisteredTaskData,
  type UnregisteredTaskPhase,
} from '@core/primitives/task-state/browser/task-state';
import type {
  RenameTaskError,
  RenameTaskSuccess,
  Task,
  TaskLifecycleStatus,
  WorkspaceLifecycleStepInfo,
  WorkspaceObservedPrFacts,
} from '@core/primitives/tasks/api';

export type TaskStoreMutations = {
  rename(
    task: RegisteredTaskData,
    name: string
  ): Promise<Result<RenameTaskSuccess, RenameTaskError>>;
  updateStatus(task: RegisteredTaskData, status: TaskLifecycleStatus): Promise<void>;
  setPinned(task: RegisteredTaskData, isPinned: boolean): Promise<void>;
  updateLinkedIssue(task: RegisteredTaskData, issue?: LinkedIssue): Promise<void>;
  convertAutomationTask(task: RegisteredTaskData): Promise<void>;
};

export class TaskStore implements TaskState {
  state: 'unregistered' | 'unprovisioned' | 'provisioned';
  data: UnregisteredTaskData | RegisteredTaskData;
  phase: UnregisteredTaskPhase | UnprovisionedTaskPhase | null;
  errorMessage: string | undefined = undefined;

  /** The workspace ID for this task session — null when unprovisioned. */
  workspaceId: string | null = null;
  workspacePath: string | null = null;
  workspaceSshConnectionId: string | undefined;
  workspaceObservedStatus: 'present' | 'missing' | null = null;
  /** In-flight createWorktree stage streamed from the host records overlay. */
  workspaceCreation: { stage: string; startedAt: number } | null = null;
  /** Durable outcome of the last createWorktree run for this task's workspace. */
  workspaceCreateOutcome: {
    status: 'started' | 'succeeded' | 'failed';
    stage?: string;
    message?: string;
  } | null = null;
  /** Lifecycle steps (creation, background, and script steps) from the host overlay. */
  workspaceLifecycle: WorkspaceLifecycleStepInfo[] | null = null;
  /** Observed PR-association facts (mirror observedGit v2); null when unobserved. */
  workspaceObservedPr: WorkspaceObservedPrFacts | null = null;
  private persistentStores: ScopedStoreHost<TaskScopedStoreContext>;
  private stores: ScopedStoreHost<TaskScopedStoreContext>;

  get displayName(): string {
    return this.data.name;
  }

  /** True only while creation/provisioning is actively running — error phases are settled, not busy. */
  get isBootstrapping(): boolean {
    return (
      (this.state === 'unregistered' && this.phase === 'creating') ||
      (this.state === 'unprovisioned' && this.phase === 'provision')
    );
  }

  constructor(
    data: UnregisteredTaskData | Task | RegisteredTaskData,
    state: TaskStore['state'],
    phase: UnregisteredTaskPhase | UnprovisionedTaskPhase | null = null,
    projectId: string = 'projectId' in data ? data.projectId : '',
    projectStores: ScopedStoreLookup = unavailableProjectStores,
    private readonly mutations: TaskStoreMutations = unavailableMutations
  ) {
    this.state = state;
    this.data = state === 'unregistered' ? data : withoutPullRequests(data as Task);
    this.phase = phase;
    makeAutoObservable<TaskStore, 'persistentStores' | 'stores'>(this, {
      workspaceId: observable,
      workspacePath: observable,
      workspaceSshConnectionId: observable,
      workspaceObservedStatus: observable,
      workspaceCreation: observable,
      workspaceCreateOutcome: observable,
      workspaceLifecycle: observable,
      workspaceObservedPr: observable,
      persistentStores: false,
      stores: false,
      /** Deep observable so nested fields (e.g. `status`) notify observers (e.g. sidebar). */
      data: observable,
    });
    const context = { projectId, taskId: data.id, task: this, projectStores };
    this.persistentStores = new ScopedStoreHost(context, taskPersistentStoreContributions);
    try {
      this.stores = new ScopedStoreHost(context, taskStoreContributions);
    } catch (error) {
      this.persistentStores.dispose();
      throw error;
    }
  }

  setWorkspaceProjection(projection?: {
    path: string | null;
    observedStatus: 'present' | 'missing' | null;
    creation?: { stage: string; startedAt: number } | null;
    lastCreateOutcome?: {
      status: 'started' | 'succeeded' | 'failed';
      stage?: string;
      message?: string;
    } | null;
    lifecycle?: WorkspaceLifecycleStepInfo[] | null;
    observedPr?: WorkspaceObservedPrFacts | null;
  }): void {
    this.workspacePath = projection?.path ?? this.workspacePath;
    this.workspaceObservedStatus = projection?.observedStatus ?? null;
    this.workspaceCreation = projection?.creation ?? null;
    this.workspaceCreateOutcome = projection?.lastCreateOutcome ?? null;
    this.workspaceLifecycle = projection?.lifecycle ?? null;
    this.workspaceObservedPr = projection?.observedPr ?? null;
  }

  get<Token extends ScopedStoreToken<unknown>>(token: Token): ScopedStoreValue<Token> {
    if (this.persistentStores.has(token)) return this.persistentStores.get(token);
    return this.stores.get(token);
  }

  ready(): Promise<void> {
    return this.stores.ready();
  }

  transitionToProvisioned(
    data: Task | RegisteredTaskData,
    path: string,
    workspaceId: string,
    sshConnectionId?: string
  ): void {
    this.data = { ...withoutPullRequests(data), workspaceId };
    this.workspaceId = workspaceId;
    this.workspacePath = path;
    this.workspaceSshConnectionId = sshConnectionId;
    this.state = 'provisioned';
    this.phase = null;
    this.errorMessage = undefined;
  }

  refreshWorkspaceBinding(
    data: Task | RegisteredTaskData,
    path: string,
    workspaceId: string,
    sshConnectionId?: string
  ): void {
    this.data = { ...withoutPullRequests(data), workspaceId };
    this.workspaceId = workspaceId;
    this.workspacePath = path;
    this.workspaceSshConnectionId = sshConnectionId;
  }

  transitionToUnprovisioned(
    data: Task | RegisteredTaskData,
    phase: UnprovisionedTaskPhase = 'idle'
  ): void {
    this.workspaceId = null;
    this.workspacePath = null;
    this.workspaceSshConnectionId = undefined;
    this.data = withoutPullRequests(data);
    this.state = 'unprovisioned';
    this.phase = phase;
    this.errorMessage = undefined;
  }

  transitionToDryUnprovisioned(
    data: Task | RegisteredTaskData,
    phase: UnprovisionedTaskPhase = 'idle'
  ): void {
    this.stores.dispose();
    this.workspaceId = null;
    this.workspacePath = null;
    this.workspaceSshConnectionId = undefined;
    this.data = withoutPullRequests(data);
    this.state = 'unprovisioned';
    this.phase = phase;
    this.errorMessage = undefined;
  }

  transitionToUnregistered(data: UnregisteredTaskData): void {
    this.workspaceId = null;
    this.workspacePath = null;
    this.workspaceSshConnectionId = undefined;
    this.data = data;
    this.state = 'unregistered';
    this.phase = 'creating';
    this.errorMessage = undefined;
  }

  activate(): void {
    this.stores.activate();
  }

  dispose(): void {
    this.stores.dispose();
    this.persistentStores.dispose();
    this.workspaceId = null;
    this.workspacePath = null;
    this.workspaceSshConnectionId = undefined;
  }

  async rename(name: string): Promise<Result<RenameTaskSuccess, RenameTaskError>> {
    const task = registeredTaskData(this);
    if (!task) return err({ type: 'task-not-found', taskId: this.data.id });
    try {
      return await this.mutations.rename(task, name);
    } catch (e) {
      log.error(e);
      throw e;
    }
  }

  async updateStatus(status: TaskLifecycleStatus): Promise<void> {
    const task = registeredTaskData(this);
    if (!task) return;
    try {
      await this.mutations.updateStatus(task, status);
    } catch (e) {
      log.error(e);
      throw e;
    }
  }

  async setPinned(isPinned: boolean): Promise<void> {
    if (this.state === 'unregistered') return;
    const task = registeredTaskData(this);
    if (!task) return;
    try {
      await this.mutations.setPinned(task, isPinned);
    } catch (e) {
      log.error(e);
      throw e;
    }
  }

  async updateLinkedIssue(issue?: LinkedIssue): Promise<void> {
    if (this.state === 'unregistered') return;
    const task = registeredTaskData(this);
    if (!task) return;
    try {
      await this.mutations.updateLinkedIssue(task, issue);
    } catch (e) {
      log.error(e);
      throw e;
    }
  }

  async convertAutomationTask(): Promise<void> {
    if (this.state === 'unregistered') return;
    const task = registeredTaskData(this);
    if (!task || task.type !== 'automation-run') return;
    try {
      await this.mutations.convertAutomationTask(task);
    } catch (e) {
      log.error(e);
      throw e;
    }
  }
}

export function createUnregisteredTask(
  data: UnregisteredTaskData,
  projectId: string,
  projectStores?: ScopedStoreLookup,
  mutations?: TaskStoreMutations
): TaskStore {
  return new TaskStore(data, 'unregistered', 'creating', projectId, projectStores, mutations);
}

export function createUnprovisionedTask(
  data: Task | RegisteredTaskData,
  projectStores?: ScopedStoreLookup,
  mutations?: TaskStoreMutations
): TaskStore {
  return new TaskStore(data, 'unprovisioned', 'idle', data.projectId, projectStores, mutations);
}

function withoutPullRequests(data: Task | RegisteredTaskData): RegisteredTaskData {
  if (!('prs' in data)) return data;
  const { prs: _prs, ...task } = data;
  return task;
}

const unavailableProjectStores: ScopedStoreLookup = {
  get(token): never {
    throw new Error(`Project scoped store '${token.id}' is unavailable`);
  },
  has: () => false,
};

const unavailableMutations: TaskStoreMutations = {
  rename: async (task) => err({ type: 'task-not-found', taskId: task.id }),
  updateStatus: async () => {
    throw new Error('Task mutations are unavailable');
  },
  setPinned: async () => {
    throw new Error('Task mutations are unavailable');
  },
  updateLinkedIssue: async () => {
    throw new Error('Task mutations are unavailable');
  },
  convertAutomationTask: async () => {
    throw new Error('Task mutations are unavailable');
  },
};
