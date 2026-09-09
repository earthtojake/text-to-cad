import type { GitCredentialsSessionSpec } from '@emdash/core/primitives/git-credentials/api';
import { sshConnectionIdOf, type HostRef } from '@emdash/core/primitives/host/api';
import type { HostFileRef } from '@emdash/core/primitives/path/api';
import type {
  TerminalShellAvailability,
  TerminalShellId,
} from '@emdash/core/primitives/terminal-shell/api';
import { err, ok, type Result } from '@emdash/shared';
import type { Logger } from '@emdash/shared/logger';
import { type LiveSource } from '@emdash/wire/rpc';
import { createController, type CallMeta, type Controller } from '@emdash/wire/rpc';
import { and, eq, isNull, sql } from 'drizzle-orm';
import type { GitCredentialsService } from '@core/features/github/api/node/services/git-credentials-service';
import type { ProjectAttachmentError } from '@core/features/projects/api';
import {
  requireAttachedProjectOrThrow,
  withAttachedProject,
} from '@core/features/projects/api/node/attached-project';
import type { ProjectAttachmentManager } from '@core/features/projects/api/node/project-attachment-manager';
import { resolveProjectEffectiveSettings } from '@core/features/projects/api/node/settings/effective-settings';
import {
  terminalsContract,
  type TerminalCreateResult,
  type TerminalHydrateResult,
  type TerminalRuntimeKey,
  type TerminalSliceContextError,
} from '@core/features/terminals/api';
import {
  throwTerminalsRuntimeResolveError,
  type TerminalsHostRuntimesClient as HostRuntimesClient,
  type TerminalsRuntimeError as TerminalError,
  type TerminalsRuntimeBroker,
  type TerminalsRuntimeKey as TerminalKey,
  type TerminalsRuntimeResolveError as RuntimeResolveError,
  type TerminalsWorkspaceIdentity as WorkspaceIdentity,
  type TerminalsWorkspaceIdentityResolver,
} from '@core/features/terminals/api/runtime-adapter';
import { getTaskEnvVars } from '@core/features/workspaces/api/node/workspace-env';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';
import { makePtySessionId, parsePtySessionId } from '@core/primitives/pty/api';
import type { TelemetryService } from '@core/primitives/telemetry/api/telemetry';
import { lifecycleScriptNodeIdFromTerminalId, type Terminal } from '@core/primitives/terminals/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { tasks, terminals } from '@core/services/app-db/node/schema';
import type { AppSettingsService } from '@core/services/settings/node';

export type CreateTerminalsWireControllerOptions = Readonly<{
  db: AppDb;
  projects: Pick<ProjectAttachmentManager, 'requireAttached'>;
  runtimes: TerminalsRuntimeBroker;
  settings: Pick<AppSettingsService, 'get'>;
  workspaceIdentity: TerminalsWorkspaceIdentityResolver;
  logger: Logger;
  telemetry: TelemetryService;
  terminalShell: {
    getColorEnv(): Promise<Record<string, string>>;
  };
  /**
   * Per-session git credential behavior from the project's "agent git
   * credentials" setting (spec: github-git-settings §4), applied through the
   * blessed terminal-env construction in the terminals runtime.
   */
  resolveSessionGitCredentials: GitCredentialsService['resolveSessionSpec'];
}>;

type TerminalContext = Readonly<{
  identity: WorkspaceIdentity;
  workspace: HostFileRef;
  key: TerminalKey;
  tmuxEnabled: boolean;
  shellSetup?: string;
  taskEnvVars: Record<string, string>;
  gitCredentials?: GitCredentialsSessionSpec;
}>;
type TerminalControllerError =
  | TerminalError
  | RuntimeResolveError
  | ProjectAttachmentError
  | TerminalSliceContextError;

const DEFAULT_TERMINAL_SIZE = { cols: 80, rows: 24 };

export function createTerminalsWireController(
  options: CreateTerminalsWireControllerOptions
): Controller {
  return createController(terminalsContract, {
    list: (input) => listTerminals(options, input),
    create: (input) => createTerminal(options, input),
    delete: (input) => deleteTerminal(options, input),
    rename: (input) => renameTerminal(options, input),
    hydrate: (input) => hydrateTerminal(options, input),
    getShellAvailability: (input) => getShellAvailability(options, input),
    output: async (key) =>
      resolveRuntimeSource(options, key.workspaceId, (client, identity) =>
        client.terminals.output.handle(toTerminalKey(identity, key.terminalId)).asLiveSource()
      ),
    sendInput: (input, meta) =>
      withTerminalRuntime(options, input, (client, key) =>
        client.sendInput({ key, data: input.data }, callOptions(meta))
      ),
    resize: (input, meta) =>
      withTerminalRuntime(options, input, (client, key) =>
        client.resize({ key, cols: input.cols, rows: input.rows }, callOptions(meta))
      ),
    kill: (input, meta) =>
      withTerminalRuntime(options, input, (client, key) => client.kill({ key }, callOptions(meta))),
  });
}

async function listTerminals(
  options: CreateTerminalsWireControllerOptions,
  {
    projectId,
    taskId,
  }: {
    projectId: string;
    taskId: string;
  }
): Promise<Result<Terminal[], TerminalControllerError>> {
  const rows = await options.db
    .select()
    .from(terminals)
    .where(and(eq(terminals.projectId, projectId), eq(terminals.taskId, taskId)));
  return ok(rows.map(mapTerminalRowToTerminal));
}

async function createTerminal(
  options: CreateTerminalsWireControllerOptions,
  input: {
    id: string;
    projectId: string;
    taskId: string;
    name: string;
    shell?: TerminalShellId;
    initialSize?: { cols: number; rows: number };
  }
): Promise<Result<TerminalCreateResult, TerminalControllerError>> {
  const shell = input.shell ?? (await options.settings.get('terminal')).defaultShell;
  const [row] = await options.db
    .insert(terminals)
    .values({
      id: input.id,
      projectId: input.projectId,
      taskId: input.taskId,
      name: input.name,
      shellId: shell,
      ssh: 0,
      updatedAt: sql`CURRENT_TIMESTAMP`,
    })
    .returning();

  const terminal = mapTerminalRowToTerminal(row);
  const hydrated = await startRuntimeTerminal(options, terminal, input.initialSize);
  if (!hydrated.success) {
    await options.db.delete(terminals).where(eq(terminals.id, input.id)).execute();
    return hydrated;
  }

  options.telemetry.capture('terminal_created', {
    terminal_id: input.id,
    project_id: input.projectId,
    task_id: input.taskId,
  });
  return ok({ terminal, key: hydrated.data.key });
}

async function deleteTerminal(
  options: CreateTerminalsWireControllerOptions,
  {
    projectId,
    taskId,
    terminalId,
  }: {
    projectId: string;
    taskId: string;
    terminalId: string;
  }
): Promise<Result<void, TerminalControllerError>> {
  const workspaceId = await resolveWorkspaceIdForTask(options.db, projectId, taskId);
  await options.db
    .delete(terminals)
    .where(
      and(
        eq(terminals.id, terminalId),
        eq(terminals.projectId, projectId),
        eq(terminals.taskId, taskId)
      )
    );

  if (workspaceId) {
    await withTerminalRuntime(
      options,
      {
        workspaceId,
        terminalId: makePtySessionId(projectId, taskId, terminalId),
      },
      (client, key) => client.kill({ key })
    ).catch(() => {});
  }

  options.telemetry.capture('terminal_deleted', {
    terminal_id: terminalId,
    project_id: projectId,
    task_id: taskId,
  });
  return ok(undefined);
}

async function renameTerminal(
  options: CreateTerminalsWireControllerOptions,
  input: {
    terminalId: string;
    name: string;
  }
): Promise<Result<void, TerminalControllerError>> {
  await options.db
    .update(terminals)
    .set({ name: input.name, updatedAt: sql`CURRENT_TIMESTAMP` })
    .where(eq(terminals.id, input.terminalId));
  return ok(undefined);
}

async function hydrateTerminal(
  options: CreateTerminalsWireControllerOptions,
  input: {
    projectId: string;
    taskId: string;
    terminalId: string;
    initialSize?: { cols: number; rows: number };
  }
): Promise<Result<TerminalHydrateResult, TerminalControllerError>> {
  const [row] = await options.db
    .select()
    .from(terminals)
    .where(
      and(
        eq(terminals.id, input.terminalId),
        eq(terminals.projectId, input.projectId),
        eq(terminals.taskId, input.taskId)
      )
    )
    .limit(1);
  if (!row) return err(terminalError('missing-terminal', `Terminal ${input.terminalId} not found`));
  return startRuntimeTerminal(options, mapTerminalRowToTerminal(row), input.initialSize);
}

async function getShellAvailability(
  options: CreateTerminalsWireControllerOptions,
  input: { host: HostRef }
): Promise<Result<TerminalShellAvailability[], TerminalControllerError>> {
  const runtime = await options.runtimes.client(input.host);
  if (!runtime.success) return err(runtime.error);
  return runtime.data.terminals.getShellAvailability(undefined);
}

async function startRuntimeTerminal(
  options: CreateTerminalsWireControllerOptions,
  terminal: Terminal,
  initialSize: { cols: number; rows: number } = DEFAULT_TERMINAL_SIZE
): Promise<Result<TerminalHydrateResult, TerminalControllerError>> {
  const context = await resolveTerminalContext(options, terminal);
  if (!context.success) return context;

  const colorEnv = await options.terminalShell.getColorEnv();
  const result = await withWorkspaceRuntime(options, context.data.identity.workspaceId, (client) =>
    client.terminals.start({
      key: context.data.key,
      spec: {
        cwd: context.data.identity.path,
        shellIntent: terminal.shellId,
        shellSetup: context.data.shellSetup,
        tmux: context.data.tmuxEnabled,
        env: {
          ...context.data.taskEnvVars,
          ...colorEnv,
        },
        gitCredentials: context.data.gitCredentials,
        cols: initialSize.cols,
        rows: initialSize.rows,
      },
    })
  );
  if (!result.success) return result;
  return ok({
    key: {
      workspaceId: context.data.identity.workspaceId,
      terminalId: context.data.key.id,
    },
  });
}

async function resolveTerminalContext(
  options: CreateTerminalsWireControllerOptions,
  terminal: Terminal
): Promise<Result<TerminalContext, TerminalControllerError>> {
  const [taskRow] = await options.db
    .select()
    .from(tasks)
    .where(
      and(
        eq(tasks.id, terminal.taskId),
        eq(tasks.projectId, terminal.projectId),
        isNull(tasks.deletedAt)
      )
    )
    .limit(1);
  if (!taskRow) return err(terminalError('missing-task', `Task ${terminal.taskId} not found`));
  const workspaceId = taskRow.workspaceId;
  if (!workspaceId) {
    return err(terminalError('missing-workspace', `Task ${terminal.taskId} has no workspace`));
  }

  return withAttachedProject(options.projects, terminal.projectId, async (project) => {
    const identity = await options.workspaceIdentity.resolve(workspaceId);
    if (!identity) {
      return err(terminalError('missing-workspace', `Workspace ${workspaceId} was not found`));
    }

    return withWorkspaceRuntime(options, identity.workspaceId, async (client) => {
      // Effective default branch through the blessed resolver (spec:
      // github-git-settings §2); null (unresolvable) omits the env var.
      const [effective, tmux, projectConfig] = await Promise.all([
        resolveProjectEffectiveSettings({
          settings: project.settings,
          repoFacts: project.repoFacts,
        }),
        project.settings.resolveTmux(),
        client.workspaceRegistry.getProjectConfig({ workspaceId: identity.workspaceId }),
      ]);
      const defaultBranch = effective.defaultBranch.value?.branch ?? null;
      if (!projectConfig.success) {
        return err(
          terminalError(
            'missing-workspace',
            `Workspace ${identity.workspaceId} has no project configuration`
          )
        );
      }
      const gitCredentials = await options.resolveSessionGitCredentials({
        projectId: terminal.projectId,
        host: identity.host,
      });
      return ok({
        identity,
        workspace: workspaceRef(identity),
        key: toTerminalKey(
          identity,
          makePtySessionId(terminal.projectId, terminal.taskId, terminal.id)
        ),
        tmuxEnabled: tmux.value,
        shellSetup: projectConfig.data.resolved.shellSetup?.value,
        taskEnvVars: getTaskEnvVars({
          taskId: terminal.taskId,
          taskName: taskRow.name,
          taskPath: identity.path,
          projectPath: project.repoPath,
          defaultBranch,
          portSeed: identity.path,
        }),
        gitCredentials,
      });
    });
  });
}

async function withTerminalRuntime<T, E>(
  options: CreateTerminalsWireControllerOptions,
  input: TerminalRuntimeKey,
  work: (client: HostRuntimesClient['terminals'], key: TerminalKey) => Promise<Result<T, E>>
): Promise<Result<T, E | RuntimeResolveError | ProjectAttachmentError>> {
  return withWorkspaceRuntime(options, input.workspaceId, (client, identity) =>
    work(client.terminals, toTerminalKey(identity, input.terminalId))
  );
}

async function withWorkspaceRuntime<T, E>(
  options: CreateTerminalsWireControllerOptions,
  workspaceId: string,
  work: (client: HostRuntimesClient, identity: WorkspaceIdentity) => Promise<Result<T, E>>
): Promise<Result<T, E | RuntimeResolveError | ProjectAttachmentError>> {
  const identity = await requireIdentity(options.workspaceIdentity.resolve(workspaceId));
  return withAttachedProject(options.projects, identity.projectId, async () => {
    const runtime = await options.runtimes.client(identity.host);
    if (!runtime.success) return err(runtime.error);
    return await work(runtime.data, identity);
  });
}

async function resolveRuntimeSource(
  options: CreateTerminalsWireControllerOptions,
  workspaceId: string,
  source: (client: HostRuntimesClient, identity: WorkspaceIdentity) => LiveSource
): Promise<LiveSource> {
  const identity = await requireIdentity(options.workspaceIdentity.resolve(workspaceId));
  requireAttachedProjectOrThrow(options.projects, identity.projectId);
  const runtime = await options.runtimes.client(identity.host);
  if (!runtime.success) throwTerminalsRuntimeResolveError(runtime.error);
  return source(runtime.data, identity);
}

async function resolveWorkspaceIdForTask(
  db: AppDb,
  projectId: string,
  taskId: string
): Promise<string | null> {
  const [row] = await db
    .select({ workspaceId: tasks.workspaceId })
    .from(tasks)
    .where(and(eq(tasks.id, taskId), eq(tasks.projectId, projectId), isNull(tasks.deletedAt)))
    .limit(1);
  return row?.workspaceId ?? null;
}

async function requireIdentity(
  identityPromise: Promise<WorkspaceIdentity | null>
): Promise<WorkspaceIdentity> {
  const identity = await identityPromise;
  if (!identity) throw new Error('Terminal workspace identity was not found');
  return identity;
}

function workspaceRef(identity: WorkspaceIdentity): HostFileRef {
  return hostFileRefFromNativePath(identity.path, sshConnectionIdOf(identity.host));
}

function toTerminalKey(identity: WorkspaceIdentity, terminalId: string): TerminalKey {
  return {
    workspace: workspaceRef(identity),
    id: runtimeTerminalId(terminalId),
  };
}

function runtimeTerminalId(terminalId: string): string {
  const parsed = parsePtySessionId(terminalId);
  if (!parsed) return terminalId;
  return lifecycleScriptNodeIdFromTerminalId(parsed.leafId) ?? terminalId;
}

function mapTerminalRowToTerminal(row: typeof terminals.$inferSelect): Terminal {
  return {
    id: row.id,
    taskId: row.taskId,
    ssh: row.ssh === 1,
    projectId: row.projectId,
    shellId: row.shellId,
    name: row.name,
  };
}

function terminalError(
  type: TerminalSliceContextError['type'],
  message: string
): TerminalSliceContextError {
  return { type, message };
}

function callOptions(meta: CallMeta): { signal?: AbortSignal } {
  return meta.signal ? { signal: meta.signal } : {};
}
