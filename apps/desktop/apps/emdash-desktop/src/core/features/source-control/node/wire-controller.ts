import { err, ok, type Result } from '@emdash/shared';
import {
  createLiveJobReplicaCache,
  LiveJobFailedError,
  type LiveJobContext,
} from '@emdash/wire/live';
import {
  type JobError,
  type JobInput,
  type JobProgress,
  type JobResult,
  type LiveModelProvider,
  type LiveJobClientHandle,
  type LiveJobEndpointDef,
  type LiveSource,
} from '@emdash/wire/rpc';
import { createController, type CallMeta, type Controller } from '@emdash/wire/rpc';
import type {
  GitOperationCredentialsLease,
  GitCredentialsService,
} from '@core/features/github/api/node/services/git-credentials-service';
import type { ProjectAttachmentError } from '@core/features/projects/api';
import {
  requireAttachedProjectOrThrow,
  withAttachedProject,
} from '@core/features/projects/api/node/attached-project';
import type { ProjectAttachmentManager } from '@core/features/projects/api/node/project-attachment-manager';
import type { ProjectProvider } from '@core/features/projects/api/node/project-provider';
import { hostPathFromNative } from '@core/primitives/desktop-runtime/api';
import { forwardModelMutation } from '@core/services/runtime-clients/node/forward-live-model';
import { sourceControlContract } from '../api';
import {
  sourceControlGitRuntimeContract as gitContract,
  throwSourceControlRuntimeResolveError,
  type SourceControlHostRuntimesClient as HostRuntimesClient,
  type SourceControlRuntimeBroker,
  type SourceControlRuntimeResolveError as RuntimeResolveError,
  type SourceControlWorkspaceIdentity as WorkspaceIdentity,
  type SourceControlWorkspaceIdentityResolver,
} from '../api/runtime-adapter';

export type CreateSourceControlWireControllerOptions = Readonly<{
  runtimes: SourceControlRuntimeBroker;
  workspaceIdentity: SourceControlWorkspaceIdentityResolver;
  projects: Pick<ProjectAttachmentManager, 'requireAttached'>;
  /**
   * Operation-scoped emdash credential helper for network git jobs
   * (spec: github-git-settings §4): emdash's own fetch/push/pull/publish
   * authenticate as the project's effective account on its host.
   */
  mintOperationCredentials: GitCredentialsService['mintOperationCredentials'];
}>;

export function createSourceControlWireController(
  options: CreateSourceControlWireControllerOptions
): Controller {
  const repositoryModel = createRepositoryModelProvider(options);
  const checkoutModel = createCheckoutModelProvider(options);

  return createController(sourceControlContract, {
    repository: {
      model: repositoryModel,
      listWorktrees: (input, meta) =>
        withRepositoryRuntime(options, input, (git, mapped) =>
          git.repository.listWorktrees(mapped, callOptions(meta))
        ),
      getDefaultBranch: (input, meta) =>
        withRepositoryRuntime(options, input, (git, mapped) =>
          git.repository.getDefaultBranch(mapped, callOptions(meta))
        ),
      fetch: job<typeof sourceControlContract.repository.fetch>((input, context) =>
        runRepositoryJob(
          options,
          gitContract.repository.fetch,
          input,
          context,
          (git) => git.repository.fetch
        )
      ),
      fetchPrForReview: job<typeof sourceControlContract.repository.fetchPrForReview>(
        (input, context) =>
          runRepositoryJob(
            options,
            gitContract.repository.fetchPrForReview,
            input,
            context,
            (git) => git.repository.fetchPrForReview
          )
      ),
    },
    checkout: {
      model: checkoutModel,
      getChangedFiles: (input, meta) =>
        withCheckoutRuntime(options, input, (git, mapped) =>
          git.checkout.getChangedFiles(mapped, callOptions(meta))
        ),
      getFile: (input, meta) =>
        withCheckoutRuntime(options, input, (git, mapped) =>
          git.checkout.getFile(mapped, callOptions(meta))
        ),
      download: async (input, meta) => {
        const result = await withCheckoutRuntime(options, input, (git, mapped) =>
          git.checkout.download(mapped, callOptions(meta))
        );
        if (!result.success) return result;
        return ok({ meta: result.data.meta, source: result.data.chunks() });
      },
      getLog: (input, meta) =>
        withCheckoutRuntime(options, input, (git, mapped) =>
          git.checkout.getLog(mapped, callOptions(meta))
        ),
      getCommit: (input, meta) =>
        withCheckoutRuntime(options, input, (git, mapped) =>
          git.checkout.getCommit(mapped, callOptions(meta))
        ),
      getCommitFiles: (input, meta) =>
        withCheckoutRuntime(options, input, (git, mapped) =>
          git.checkout.getCommitFiles(mapped, callOptions(meta))
        ),
      blame: (input, meta) =>
        withCheckoutRuntime(options, input, (git, mapped) =>
          git.checkout.blame(mapped, callOptions(meta))
        ),
      push: job<typeof sourceControlContract.checkout.push>((input, context) =>
        runCheckoutJob(
          options,
          gitContract.checkout.push,
          input,
          context,
          (git) => git.checkout.push
        )
      ),
      publish: job<typeof sourceControlContract.checkout.publish>((input, context) =>
        runCheckoutJob(
          options,
          gitContract.checkout.publish,
          input,
          context,
          (git) => git.checkout.publish
        )
      ),
      pull: job<typeof sourceControlContract.checkout.pull>((input, context) =>
        runCheckoutJob(
          options,
          gitContract.checkout.pull,
          input,
          context,
          (git) => git.checkout.pull
        )
      ),
    },
  });
}

function createRepositoryModelProvider({
  projects,
}: CreateSourceControlWireControllerOptions): LiveModelProvider<
  typeof sourceControlContract.repository.model
> {
  const contract = sourceControlContract.repository.model;
  return {
    kind: 'liveModelProvider',
    contract,
    resolveState: (key, name) =>
      resolveProjectSource(projects, key.projectId, (project) =>
        project.git.repository.model.state(project.repository, name).asLiveSource()
      ),
    async runMutation(name, envelope) {
      return withAttachedProject(projects, envelope.key.projectId, (project) =>
        forwardModelMutation(
          project.git.repository.model,
          sourceControlContract.repository.model,
          name,
          envelope,
          project.repository
        )
      ) as ReturnType<LiveModelProvider<typeof contract>['runMutation']>;
    },
  };
}

function createCheckoutModelProvider({
  runtimes,
  workspaceIdentity,
}: CreateSourceControlWireControllerOptions): LiveModelProvider<
  typeof sourceControlContract.checkout.model
> {
  const contract = sourceControlContract.checkout.model;
  return {
    kind: 'liveModelProvider',
    contract,
    resolveState: (key, name) =>
      resolveRuntimeSource(
        runtimes,
        workspaceIdentity.resolve(key.workspaceId),
        (client, identity) =>
          client.git.checkout.model
            .state({ checkout: hostPathFromNative(identity.path) }, name)
            .asLiveSource()
      ),
    async runMutation(name, envelope) {
      return withIdentityRuntime(
        runtimes,
        workspaceIdentity.resolve(envelope.key.workspaceId),
        (client, identity) =>
          forwardModelMutation(
            client.git.checkout.model,
            sourceControlContract.checkout.model,
            name,
            envelope,
            { checkout: hostPathFromNative(identity.path) }
          )
      ) as ReturnType<LiveModelProvider<typeof contract>['runMutation']>;
    },
  };
}

async function withRepositoryRuntime<T extends { projectId: string }, R, E>(
  options: CreateSourceControlWireControllerOptions,
  input: T,
  work: (
    git: HostRuntimesClient['git'],
    mapped: Omit<T, 'projectId'> & { repository: ReturnType<typeof hostPathFromNative> }
  ) => Promise<Result<R, E>>
): Promise<Result<R, E | ProjectAttachmentError>> {
  const { projectId, ...rest } = input;
  return withAttachedProject(options.projects, projectId, (project) =>
    work(project.git, {
      ...rest,
      repository: project.repository.repository,
    })
  );
}

async function resolveProjectSource(
  projects: Pick<ProjectAttachmentManager, 'requireAttached'>,
  projectId: string,
  source: (project: ProjectProvider) => LiveSource
): Promise<LiveSource> {
  const project = requireAttachedProjectOrThrow(
    projects,
    projectId,
    (error) => new Error(`Project attachment unavailable: ${error.type}`)
  );
  return source(project);
}

async function withCheckoutRuntime<T extends { workspaceId: string }, R, E>(
  options: CreateSourceControlWireControllerOptions,
  input: T,
  work: (
    git: HostRuntimesClient['git'],
    mapped: Omit<T, 'workspaceId'> & { checkout: ReturnType<typeof hostPathFromNative> }
  ) => Promise<Result<R, E>>
): Promise<Result<R, E | RuntimeResolveError>> {
  const { workspaceId, ...rest } = input;
  return withIdentityRuntime(
    options.runtimes,
    options.workspaceIdentity.resolve(workspaceId),
    (client, identity) =>
      work(client.git, {
        ...rest,
        checkout: hostPathFromNative(identity.path),
      })
  );
}

async function withIdentityRuntime<T, E>(
  runtimes: SourceControlRuntimeBroker,
  identityPromise: Promise<WorkspaceIdentity | null>,
  work: (client: HostRuntimesClient, identity: WorkspaceIdentity) => Promise<Result<T, E>>
): Promise<Result<T, E | RuntimeResolveError>> {
  const identity = await requireIdentity(identityPromise);
  const runtime = await runtimes.client(identity.host);
  if (!runtime.success) return err(runtime.error);
  return await work(runtime.data, identity);
}

async function resolveRuntimeSource(
  runtimes: SourceControlRuntimeBroker,
  identityPromise: Promise<WorkspaceIdentity | null>,
  source: (client: HostRuntimesClient, identity: WorkspaceIdentity) => LiveSource
): Promise<LiveSource> {
  const identity = await requireIdentity(identityPromise);
  const runtime = await runtimes.client(identity.host);
  if (!runtime.success) throwSourceControlRuntimeResolveError(runtime.error);
  return source(runtime.data, identity);
}

async function requireIdentity(
  identityPromise: Promise<WorkspaceIdentity | null>
): Promise<WorkspaceIdentity> {
  const identity = await identityPromise;
  if (!identity) throw new Error('Source-control workspace identity was not found');
  return identity;
}

function callOptions(meta: CallMeta): { signal?: AbortSignal } {
  return meta.signal ? { signal: meta.signal } : {};
}

function job<Def extends LiveJobEndpointDef>(
  run: (
    input: JobInput<Def>,
    context: LiveJobContext<JobProgress<Def>>
  ) => Promise<Result<JobResult<Def>, JobError<Def>>>
): { run: typeof run } {
  return { run };
}

async function runRepositoryJob<
  Def extends LiveJobEndpointDef,
  Input extends { projectId: string },
>(
  options: CreateSourceControlWireControllerOptions,
  definition: Def,
  input: Input,
  context: LiveJobContext<JobProgress<Def>>,
  handle: (git: HostRuntimesClient['git']) => LiveJobClientHandle<Def>
): Promise<Result<JobResult<Def>, JobError<Def> | ProjectAttachmentError>> {
  const { projectId, ...rest } = input;
  return withAttachedProject(options.projects, projectId, (project) =>
    withOperationCredentials(options, project, (credentials) =>
      runUpstreamJob(
        definition,
        handle(project.git),
        {
          ...rest,
          repository: project.repository.repository,
          credentials,
        } as JobInput<Def>,
        context
      )
    )
  );
}

async function runCheckoutJob<
  Def extends LiveJobEndpointDef,
  Input extends { workspaceId: string },
>(
  options: CreateSourceControlWireControllerOptions,
  definition: Def,
  input: Input,
  context: LiveJobContext<JobProgress<Def>>,
  handle: (git: HostRuntimesClient['git']) => LiveJobClientHandle<Def>
): Promise<Result<JobResult<Def>, JobError<Def> | RuntimeResolveError>> {
  const { workspaceId, ...rest } = input;
  return withIdentityRuntime(
    options.runtimes,
    options.workspaceIdentity.resolve(workspaceId),
    (client, identity) =>
      withOperationCredentials(options, identity, (credentials) =>
        runUpstreamJob(
          definition,
          handle(client.git),
          {
            ...rest,
            checkout: hostPathFromNative(identity.path),
            credentials,
          } as JobInput<Def>,
          context
        )
      )
  );
}

/**
 * Runs a network job with an operation-scoped credential lease; the lease is
 * revoked when the job settles. Always assigned (even when undefined) so a
 * caller-supplied `credentials` field can never reach the git runtime.
 */
async function withOperationCredentials<T>(
  options: CreateSourceControlWireControllerOptions,
  identity: Pick<WorkspaceIdentity, 'projectId' | 'host'>,
  work: (credentials: GitOperationCredentialsLease['credentials'] | undefined) => Promise<T>
): Promise<T> {
  const lease = await options.mintOperationCredentials({
    projectId: identity.projectId,
    host: identity.host,
  });
  try {
    return await work(lease?.credentials);
  } finally {
    lease?.release();
  }
}

async function runUpstreamJob<Def extends LiveJobEndpointDef>(
  definition: Def,
  handle: LiveJobClientHandle<Def>,
  input: JobInput<Def>,
  context: LiveJobContext<JobProgress<Def>>
): Promise<Result<JobResult<Def>, JobError<Def>>> {
  const jobs = createLiveJobReplicaCache(definition, handle);
  const lease = await jobs.start(input);
  try {
    const running = await lease.ready();
    const unsubscribe = running.onProgress(context.progress);
    const cancel = () => void running.cancel();
    context.signal.addEventListener('abort', cancel, { once: true });
    if (context.signal.aborted) cancel();
    try {
      return ok(await running.result);
    } catch (error) {
      if (error instanceof LiveJobFailedError) return err(error.error as JobError<Def>);
      throw error;
    } finally {
      context.signal.removeEventListener('abort', cancel);
      unsubscribe();
    }
  } finally {
    await lease.release();
    await jobs.dispose();
  }
}
