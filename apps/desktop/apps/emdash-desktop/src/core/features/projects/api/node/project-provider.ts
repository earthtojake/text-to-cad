import type { HostRef } from '@emdash/core/primitives/host/api';
import type {
  GitBranchRef,
  GitRemotesState,
  LocalBranchRef,
  RepositorySelector,
} from '@emdash/core/runtimes/git/api';
import type { Unsubscribe } from '@emdash/shared';
import type { Disposable } from '@emdash/shared/concurrency';
import type { ConversationProvider } from '@core/features/conversations/api/node/types';
import type { RepoFactsSource } from '@core/features/projects/api/node/settings/effective-settings';
import type { ProjectSettingsProvider } from '@core/features/projects/api/node/settings/provider';
import type { TaskSessionManager } from '@core/features/tasks/api/node/task-session-manager';
import type { WorkspaceType } from '@core/features/workspaces/api/node/workspace-factory';
import { nativePathFromHost } from '@core/primitives/desktop-runtime/api';
import {
  projectHostRef,
  type Project,
  type ProjectRemoteState,
} from '@core/primitives/projects/api';
import type {
  GitRuntimeClient,
  TerminalsRuntimeClient,
  WorkspaceRegistryRuntimeClient,
} from '@core/services/runtime-broker/api/clients';
import type { FilesClientScope } from '@core/services/runtime-broker/node/files';

export type GitRepositoryPort = {
  subscribeRemotes(callback: (update: GitRemotesState) => void): Unsubscribe;
  /** Resolver-backed effective base remote; `null` means no remotes exist. */
  getBaseRemote(): Promise<string | null>;
  /** Resolver-backed base and push remotes from one settings snapshot. */
  getEffectiveRemotes(): Promise<{ baseRemote: string | null; pushRemote: string | null }>;
  getRemoteState(): Promise<ProjectRemoteState>;
};

export type GitRepositoryFetchPort = {
  start(): void;
  stop(): void;
};

export type ProvisionResult = {
  taskProvider: TaskProvider;
  persistData: {
    workspaceId: string;
    sshConnectionId?: string;
    worktreeGitDir?: string;
  };
};

export interface TaskProvider {
  readonly taskId: string;
  readonly taskBranch: string | undefined;
  readonly sourceBranch: GitBranchRef | undefined;
  readonly taskEnvVars: Record<string, string>;
  readonly conversations: ConversationProvider;
}

/**
 * Transport-specific dependencies: the only things that differ between local and SSH.
 * Pure data — no lifecycle methods.
 */
export type ProjectProviderTransport = {
  readonly kind: string;
  readonly defaultWorkspaceType: WorkspaceType;
  readonly files: FilesClientScope;
  readonly projectConfigPath: string;
  /**
   * Transitional desktop-owned path helper. Remove once project config reads/writes
   * are served by the workspace server/core boundary instead of main-process adapters.
   */
  readonly resolveProjectPath: (relativePath: string) => string;
  /**
   * Transitional desktop-owned path helper. Remove with resolveProjectPath when
   * config target resolution moves behind the workspace server/core boundary.
   */
  readonly configPathForDirectory: (directoryPath: string) => string;
  readonly settings: ProjectSettingsProvider;
  readonly workspaceRegistry: WorkspaceRegistryRuntimeClient;
  /** Per-project repo-facts cache (spec: github-git-settings §2). */
  readonly repoFacts: RepoFactsSource;
};

export class ProjectProvider implements Disposable {
  readonly type: string;
  readonly project: Project;
  readonly projectId: string;
  readonly repoPath: string;
  readonly settings: ProjectSettingsProvider;
  readonly repoFacts: RepoFactsSource;
  readonly git: GitRuntimeClient;
  readonly repository: RepositorySelector;
  readonly gitRepository: GitRepositoryPort;
  readonly hasRepository: boolean;
  readonly files: FilesClientScope;
  readonly projectConfigPath: string;
  readonly terminals: TerminalsRuntimeClient;
  readonly workspaceRegistry: WorkspaceRegistryRuntimeClient;
  /** Workspace type for worktree tasks on this project's host. */
  readonly defaultWorkspaceType: WorkspaceType;

  private readonly _resolveProjectPath: (relativePath: string) => string;
  private readonly _configPathForDirectory: (directoryPath: string) => string;
  private releasePromise: Promise<void> | undefined;
  private disposePromise: Promise<void> | undefined;

  constructor(
    project: Project,
    transport: ProjectProviderTransport,
    gitRepository: GitRepositoryPort,
    private readonly gitRepositoryFetchService: GitRepositoryFetchPort,
    hasRepository: boolean,
    git: GitRuntimeClient,
    terminals: TerminalsRuntimeClient,
    repository: RepositorySelector,
    private readonly taskSessions: Pick<TaskSessionManager, 'teardownAllForProject'>,
    private readonly _releaseProjectLeases: () => void | Promise<void>
  ) {
    this.type = transport.kind;
    this.project = project;
    this.projectId = project.id;
    this.repoPath = project.path;
    this.settings = transport.settings;
    this.workspaceRegistry = transport.workspaceRegistry;
    this.repoFacts = transport.repoFacts;
    this.files = transport.files;
    this.projectConfigPath = transport.projectConfigPath;
    this._resolveProjectPath = transport.resolveProjectPath;
    this._configPathForDirectory = transport.configPathForDirectory;
    this.git = git;
    this.terminals = terminals;
    this.repository = repository;
    this.gitRepository = gitRepository;
    this.hasRepository = hasRepository;
    this.defaultWorkspaceType = transport.defaultWorkspaceType;
  }

  get host(): HostRef {
    return projectHostRef(this.project);
  }

  /**
   * Transitional desktop-owned path helper. See ProjectProviderTransport.
   */
  resolveProjectPath(relativePath: string): string {
    return this._resolveProjectPath(relativePath);
  }

  /**
   * Transitional desktop-owned path helper. See ProjectProviderTransport.
   */
  configPathForDirectory(directoryPath: string): string {
    return this._configPathForDirectory(directoryPath);
  }

  getRemoteState(): Promise<ProjectRemoteState> {
    return this.gitRepository.getRemoteState();
  }

  async findTaskWorktree(taskBranch: LocalBranchRef): Promise<string | null> {
    const worktrees = await this.git.repository.listWorktrees(this.repository);
    if (!worktrees.success) {
      throw new Error(worktrees.error.message ?? `Failed to list worktrees for ${this.repoPath}`);
    }
    const worktree = worktrees.data.worktrees.find(
      (candidate) =>
        !candidate.isMain &&
        !candidate.prunable &&
        candidate.head.kind === 'branch' &&
        candidate.head.ref === taskBranch
    );
    return worktree ? nativePathFromHost(worktree.worktreePath) : null;
  }

  release(): Promise<void> {
    this.releasePromise ??= (async () => {
      this.gitRepositoryFetchService.stop();
      await this.repoFacts.dispose();
      await this._releaseProjectLeases();
    })();
    return this.releasePromise;
  }

  dispose(): Promise<void> {
    this.disposePromise ??= (async () => {
      try {
        this.gitRepositoryFetchService.stop();
        const tmux = await this.settings.resolveTmux();
        const mode = tmux.value ? 'detach' : 'terminate';
        await this.taskSessions.teardownAllForProject(this.projectId, mode);
      } finally {
        await this.release();
      }
    })();
    return this.disposePromise;
  }
}
