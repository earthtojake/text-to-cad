import { err, ok, type Result } from '@emdash/shared';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { noopLogger, type Logger } from '@emdash/shared/logger';
import { systemClock, type Clock } from '@emdash/shared/scheduling';
import { LiveLogSource } from '@emdash/wire/live';
import { type LeasedLiveModelProvider, type LiveSource } from '@emdash/wire/rpc';
import { cell, expose, peek, type Cell } from '@emdash/wire/state';
import type { IExecutionContext } from '#primitives/exec/api';
import { resourceKeyFromFileRef, type HostFileRef } from '#primitives/path/api';
import type {
  ResolvedShellProfile,
  TerminalShellAvailability,
  TerminalShellId,
  TerminalShellResolver,
} from '#primitives/terminal-shell/api';
import {
  terminalsContract,
  type KillTmuxSessionsInput,
  type ShellAvailabilityFailedError,
  type StartTerminalInput,
  type StartTerminalSpec,
  type TerminalKey,
  type TerminalNotFoundError,
  type TerminalRuntimeError,
  type TerminalSessionState,
  type TerminalStartFailedError,
} from '#runtimes/terminals/api';
import {
  buildTerminalEnv,
  killTmuxSession,
  makeTmuxSessionName,
  resolveLocalPtySpawn,
  PtyRegistry,
  type PtySession,
  type PtySpawner,
} from '#services/pty/api';
import type {
  ActivityFields,
  DeactivationCause,
  IdlePolicyConfig,
  SessionLifecycle,
  SessionSnapshotJudgment,
} from '#services/session-lifecycle/api';
import { createSessionLifecycle } from '#services/session-lifecycle/node';
import type { UserShellEnv } from '#services/shell-env/api';

const DEFAULT_COLS = 80;
const DEFAULT_ROWS = 24;

type SessionsCell = Cell<Record<string, TerminalSessionState>>;

type InteractiveTerminalConfig = {
  key: TerminalKey;
  spec: StartTerminalSpec;
};

export type TerminalsRuntimeOptions = {
  spawner: PtySpawner;
  userEnv: () => Promise<UserShellEnv>;
  exec?: IExecutionContext;
  createExecutionContext?: (env: UserShellEnv) => IExecutionContext;
  scope?: Scope;
  clock?: Clock;
  lifecycle?: TerminalsRuntimeLifecycleOptions;
  shellResolver?: TerminalShellResolver;
  createShellResolver?: (env: UserShellEnv) => TerminalShellResolver;
  logger?: Logger;
};

export type TerminalsRuntimeLifecycleOptions = {
  terminal?: IdlePolicyConfig;
  sweepIntervalMs?: number;
};

export class TerminalsRuntime {
  private readonly sessionsList: SessionsCell = cell({});
  readonly sessionsHost: LeasedLiveModelProvider<typeof terminalsContract.sessions> = expose(
    terminalsContract.sessions,
    { list: this.sessionsList },
    { publish: { list: 'diff' } }
  );

  private readonly registry: PtyRegistry;
  private readonly loadUserEnv: () => Promise<UserShellEnv>;
  private readonly exec: IExecutionContext | undefined;
  private readonly createExecutionContext: ((env: UserShellEnv) => IExecutionContext) | undefined;
  private readonly scope: Scope;
  private readonly clock: Clock;
  private readonly shellResolver: TerminalShellResolver | undefined;
  private readonly createShellResolver: ((env: UserShellEnv) => TerminalShellResolver) | undefined;
  private readonly logger: Logger;
  private readonly lifecycle: SessionLifecycle;
  private readonly logs = new Map<string, LiveLogSource>();
  private readonly sessionKeys = new Map<string, TerminalKey>();
  private readonly interactiveConfigs = new Map<string, InteractiveTerminalConfig>();
  private readonly startCounts = new Map<string, number>();

  constructor(options: TerminalsRuntimeOptions) {
    this.registry = new PtyRegistry(options.spawner, {
      onSessionChanged: (key, session) => this.syncSession(key, session),
    });
    this.loadUserEnv = options.userEnv;
    this.exec = options.exec;
    this.createExecutionContext = options.createExecutionContext;
    this.scope = options.scope ?? createScope({ label: 'terminals-runtime' });
    this.clock = options.clock ?? systemClock;
    this.shellResolver = options.shellResolver;
    this.createShellResolver = options.createShellResolver;
    this.logger = options.logger ?? noopLogger;
    this.lifecycle = createSessionLifecycle({
      name: 'TerminalsRuntime',
      logger: this.logger,
      clock: this.clock,
      scope: this.scope,
      // User shells never idle out by default; the sweeper is policy-inert by design.
      idlePolicy: options.lifecycle?.terminal ?? { kind: 'always' },
      ...(options.lifecycle?.sweepIntervalMs !== undefined
        ? { sweepIntervalMs: options.lifecycle.sweepIntervalMs }
        : {}),
      entries: () => this.sessionKeys.keys(),
      snapshot: (sessionKey) => this.lifecycleSnapshot(sessionKey),
      syncListEntry: (sessionKey, activity) => this.syncActivity(sessionKey, activity),
      deactivate: (sessionKey, cause) => this.killSession(sessionKey, cause),
      evictSteps: [
        {
          name: 'pty-registry',
          run: (key) => {
            this.registry.dispose(key);
          },
        },
        {
          name: 'output-log',
          run: (key) => {
            this.logs.delete(key);
          },
        },
        {
          name: 'session-key',
          run: (key) => {
            this.sessionKeys.delete(key);
          },
        },
        {
          name: 'interactive-config',
          run: (key) => {
            this.interactiveConfigs.delete(key);
          },
        },
        {
          name: 'start-count',
          run: (key) => {
            this.startCounts.delete(key);
          },
        },
        { name: 'sessions-list-entry', run: (key) => this.removeSessionListEntry(key) },
      ],
    });
    this.scope.add(() => this.dispose());
  }

  async start(input: StartTerminalInput): Promise<Result<void, TerminalStartFailedError>> {
    const sessionKey = sessionKeyFor(input.key);
    const existing = this.registry.get(sessionKey);
    if (existing && !existing.exited) return ok(undefined);
    if (existing) {
      // Restart of a retained exited terminal: evict-then-create. The start
      // count survives eviction so the renderer still sees a restart.
      const startCount = this.startCounts.get(sessionKey) ?? 0;
      await this.lifecycle.evict(sessionKey, { cause: 'restart' });
      if (startCount > 0) this.startCounts.set(sessionKey, startCount);
    }

    this.sessionKeys.set(sessionKey, input.key);
    this.interactiveConfigs.set(sessionKey, { key: input.key, spec: input.spec });

    try {
      await this.spawnInteractiveTerminal(sessionKey, input.key, input.spec);
      return ok(undefined);
    } catch (error) {
      await this.lifecycle.evict(sessionKey, { cause: 'start-failed' });
      return err({
        type: 'terminal-start-failed',
        message: error instanceof Error ? error.message : String(error),
      });
    }
  }

  async getShellAvailability(): Promise<
    Result<TerminalShellAvailability[], ShellAvailabilityFailedError>
  > {
    try {
      const shellResolver = await this.shellResolverFor();
      if (!shellResolver) {
        return err({
          type: 'shell-availability-failed',
          message: 'No shell resolver is configured for this terminals runtime',
        });
      }
      return ok(await shellResolver.getAvailability());
    } catch (error) {
      return err({
        type: 'shell-availability-failed',
        message: error instanceof Error ? error.message : String(error),
      });
    }
  }

  outputLog(key: TerminalKey): LiveSource {
    const source = this.logFor(key);
    const sessionKey = sessionKeyFor(key);
    return {
      snapshot: () => source.snapshot(),
      subscribe: (cb) => {
        this.lifecycle.attach(sessionKey);
        const unsubscribe = source.subscribe(cb);
        return () => {
          unsubscribe();
          this.lifecycle.detach(sessionKey);
        };
      },
    };
  }

  sendInput(key: TerminalKey, data: string): Result<void, TerminalNotFoundError> {
    const sessionKey = sessionKeyFor(key);
    if (!this.registry.write(sessionKey, data)) {
      return err({ type: 'not-found', message: `Terminal session '${key.id}' is not running` });
    }
    this.lifecycle.recordInput(sessionKey);
    return ok(undefined);
  }

  resize(key: TerminalKey, cols: number, rows: number): Result<void, TerminalNotFoundError> {
    const sessionKey = sessionKeyFor(key);
    if (!this.registry.resize(sessionKey, cols, rows)) {
      return err({ type: 'not-found', message: `Terminal session '${key.id}' is not running` });
    }
    this.sessionsList.update((previous) => {
      const session = previous[sessionKey];
      if (!session) return previous;
      return {
        ...previous,
        [sessionKey]: { ...session, cols, rows },
      };
    });
    return ok(undefined);
  }

  async kill(key: TerminalKey): Promise<Result<void, TerminalNotFoundError>> {
    const sessionKey = sessionKeyFor(key);
    if (!this.sessionKeys.has(sessionKey)) {
      return err({ type: 'not-found', message: `Terminal session '${key.id}' is not running` });
    }
    await this.killSession(sessionKey, 'user');
    return ok(undefined);
  }

  async killTmuxSessions(
    input: KillTmuxSessionsInput
  ): Promise<Result<void, TerminalRuntimeError>> {
    if (process.platform === 'win32') return ok(undefined);
    await this.withExecutionContext(async (exec) => {
      for (const name of input.sessionNames) await killTmuxSession(exec, name);
    });
    return ok(undefined);
  }

  dispose(): void {
    this.lifecycle.dispose();
    this.registry.killAll();
    this.logs.clear();
    void this.sessionsHost.dispose();
  }

  /**
   * Full teardown for close/kill, sweeper deactivation, and workspace
   * deactivation (which arrives per key through `kill`). Process *exit* does
   * NOT come here — exited entries are retained with scrollback until close,
   * restart, or workspace deactivation.
   */
  private async killSession(sessionKey: string, cause: DeactivationCause): Promise<void> {
    await this.killTmuxForSession(sessionKey);
    await this.lifecycle.evict(sessionKey, { cause });
  }

  private async spawnInteractiveTerminal(
    sessionKey: string,
    key: TerminalKey,
    spec: StartTerminalSpec
  ): Promise<PtySession> {
    const log = this.logFor(key);
    const startCount = (this.startCounts.get(sessionKey) ?? 0) + 1;
    this.startCounts.set(sessionKey, startCount);
    this.sessionKeys.set(sessionKey, key);

    const userEnv = await this.loadUserEnv();
    const shellProfile = await this.resolveShellProfile(key, spec.shellIntent, userEnv);
    const env = buildTerminalEnv({
      baseEnv: userEnv,
      shellProfile,
      overrides: spec.env,
      gitCredentials: spec.gitCredentials,
    });
    const resolved = resolveLocalPtySpawn({
      intent: {
        kind: 'interactive-shell',
        cwd: spec.cwd,
        shellProfile,
        shellSetup: spec.shellSetup,
        tmuxSessionName: spec.tmux ? makeTmuxSessionName(sessionKey) : undefined,
      },
      platform: process.platform,
      env,
    });

    return await this.registry.create(
      sessionKey,
      {
        command: resolved.command,
        args: resolved.args,
        cwd: resolved.cwd,
        env,
        cols: spec.cols ?? DEFAULT_COLS,
        rows: spec.rows ?? DEFAULT_ROWS,
      },
      {
        output: log,
        onData: () => {
          this.lifecycle.recordOutput(sessionKey);
        },
      }
    );
  }

  private async resolveShellProfile(
    key: TerminalKey,
    intent: TerminalShellId | undefined,
    userEnv: UserShellEnv
  ): Promise<ResolvedShellProfile | undefined> {
    const shellResolver = await this.shellResolverFor(userEnv);
    if (!intent || !shellResolver) return undefined;
    return await shellResolver.resolveWithSystemFallback({
      intent,
      onFallback: (event) =>
        this.logger.warn('terminals: falling back to system shell', {
          terminalId: key.id,
          shell: event.shell,
          message: event.message,
        }),
    });
  }

  private async killTmuxForSession(sessionKey: string): Promise<void> {
    const config = this.interactiveConfigs.get(sessionKey);
    if (!config?.spec.tmux || process.platform === 'win32') return;
    await this.withExecutionContext((exec) =>
      killTmuxSession(exec, makeTmuxSessionName(sessionKey))
    );
  }

  private async shellResolverFor(
    userEnv?: UserShellEnv
  ): Promise<TerminalShellResolver | undefined> {
    if (this.createShellResolver) {
      return this.createShellResolver(userEnv ?? (await this.loadUserEnv()));
    }
    return this.shellResolver;
  }

  private async withExecutionContext(
    operation: (exec: IExecutionContext) => Promise<void>
  ): Promise<void> {
    if (this.exec) {
      await operation(this.exec);
      return;
    }
    if (!this.createExecutionContext) return;

    const exec = this.createExecutionContext(await this.loadUserEnv());
    try {
      await operation(exec);
    } finally {
      exec.dispose();
    }
  }

  private logFor(key: TerminalKey): LiveLogSource {
    const id = sessionKeyFor(key);
    let log = this.logs.get(id);
    if (!log) {
      log = new LiveLogSource();
      this.logs.set(id, log);
    }
    return log;
  }

  private syncSession(key: string, session: PtySession | null): void {
    this.sessionsList.update((previous) => {
      if (!session) {
        const existing = previous[key];
        if (!existing) return previous;
        return {
          ...previous,
          [key]: {
            ...existing,
            status: 'exited',
            exitedAt: existing.exitedAt ?? this.clock.now(),
          },
        };
      }
      const terminalKey = this.sessionKeys.get(key);
      if (!terminalKey) return previous;
      const exit = session.exitStatus ?? undefined;
      const existing = previous[key];
      const activity = this.lifecycle.activity(key);
      const state: TerminalSessionState = {
        key: terminalKey,
        status: session.exited ? 'exited' : 'running',
        startCount: this.startCounts.get(key) ?? existing?.startCount ?? 1,
        tmux: this.interactiveConfigs.get(key)?.spec.tmux,
        pid: session.getPid(),
        cols: session.spec.cols,
        rows: session.spec.rows,
        startedAt: session.startedAt,
        exitedAt: session.exited ? (existing?.exitedAt ?? this.clock.now()) : undefined,
        lastInputAt: activity.lastInputAt ?? existing?.lastInputAt,
        lastOutputAt: activity.lastOutputAt ?? existing?.lastOutputAt,
        exit:
          exit !== undefined
            ? {
                exitCode: exit.exitCode,
                signal: exit.signal,
              }
            : undefined,
      };
      return {
        ...previous,
        [key]: state,
      };
    });
  }

  private syncActivity(sessionKey: string, activity: ActivityFields): void {
    this.sessionsList.update((previous) => {
      const session = previous[sessionKey];
      if (!session) return previous;
      return {
        ...previous,
        [sessionKey]: {
          ...session,
          lastInputAt: activity.lastInputAt ?? session.lastInputAt,
          lastOutputAt: activity.lastOutputAt ?? session.lastOutputAt,
        },
      };
    });
  }

  private lifecycleSnapshot(sessionKey: string): SessionSnapshotJudgment | null {
    const session = peek(this.sessionsList)[sessionKey];
    if (!session || session.status !== 'running') return null;
    return { running: true, busy: false };
  }

  private removeSessionListEntry(sessionKey: string): void {
    this.sessionsList.update((previous) => omitKey(previous, sessionKey));
  }
}

function scopeKeyFor(workspace: HostFileRef): string {
  return resourceKeyFromFileRef(workspace);
}

function sessionKeyFor(key: TerminalKey): string {
  return `${scopeKeyFor(key.workspace)}:${key.id}`;
}

function omitKey<T>(record: Record<string, T>, key: string): Record<string, T> {
  if (!(key in record)) return record;
  const { [key]: _removed, ...rest } = record;
  return rest;
}
