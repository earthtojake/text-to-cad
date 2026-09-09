import crypto from 'node:crypto';
import { err, ok, type Result } from '@emdash/shared';
import { noopLogger, type Logger } from '@emdash/shared/logger';
import { LiveLogSource } from '@emdash/wire/live';
import type { LeasedLiveModelProvider, LiveSource } from '@emdash/wire/rpc';
import { cell, expose, family, peek, type Cell } from '@emdash/wire/state';
import { buildTerminalEnv, PtyRegistry, type PtySpawner } from '#services/pty/api';
import type { UserShellEnv } from '#services/shell-env/api';
import { scriptsContract } from '../api/contract';
import type { ScriptRunNotFoundError, StartScriptRunError } from '../api/errors';
import type {
  ScriptKind,
  ScriptRunInput,
  ScriptRunKey,
  ScriptRunResizeInput,
  ScriptRunState,
  ScriptRuns,
  StartScriptRunInput,
  StopScriptRunInput,
  WaitScriptRunInput,
} from '../api/schemas';
import { buildScriptEnv } from './env';

const DEFAULT_COLS = 80;
const DEFAULT_ROWS = 24;
const OUTPUT_TAIL_CAP = 16 * 1024;

export type ScriptsRuntimeOptions = {
  spawner: PtySpawner;
  userEnv: () => Promise<UserShellEnv>;
  now?: () => number;
  logger?: Logger;
};

type ActiveRun = {
  runId: string;
  settled: Promise<ScriptRunState>;
  timer: NodeJS.Timeout | null;
  stopRequested: boolean;
  timedOut: boolean;
  kill: () => void;
};

/**
 * The single script execution plane (spec: activation-scripts-via-terminals). Owns
 * script runs end-to-end: PTY spawning via the shared PTY services, a
 * per-(workspace, script) guard, per-run timeouts, an explicit stop verb,
 * provenance attribution, and transient result retention (last run per key, all
 * in-memory). Runs are detached from the starting caller — they die only on stop,
 * self-exit, or host shutdown. No idle sweeping: a long-running script keeps
 * running when every observer disconnects.
 */
export class ScriptsRuntime {
  private readonly runStates = family<{ workspacePath: string }, Cell<ScriptRuns>>(
    () => cell<ScriptRuns>({}),
    { name: 'script-run-states' }
  );
  readonly runsHost: LeasedLiveModelProvider<typeof scriptsContract.runs> = expose(
    scriptsContract.runs,
    {
      current: (key, scope) => {
        scope.add(this.runStates.retain(key));
        return this.runStates(key);
      },
    }
  );

  private readonly registry: PtyRegistry;
  private readonly loadUserEnv: () => Promise<UserShellEnv>;
  private readonly now: () => number;
  private readonly logger: Logger;
  private readonly logs = new Map<string, LiveLogSource>();
  private readonly active = new Map<string, ActiveRun>();
  private disposed = false;

  constructor(options: ScriptsRuntimeOptions) {
    this.registry = new PtyRegistry(options.spawner);
    this.loadUserEnv = options.userEnv;
    this.now = options.now ?? Date.now;
    this.logger = options.logger ?? noopLogger;
  }

  async start(input: StartScriptRunInput): Promise<Result<ScriptRunState, StartScriptRunError>> {
    const runKey = runKeyFor(input);
    if (this.active.has(runKey)) {
      return err({
        type: 'run-in-flight',
        message: `Script '${input.script}' is already running for this workspace — stop it first`,
      });
    }

    const log = this.logFor(input);
    log.reseed();

    const runId = crypto.randomUUID();
    let outputTail = '';
    let resolveSettled: (state: ScriptRunState) => void;
    const settled = new Promise<ScriptRunState>((resolve) => {
      resolveSettled = resolve;
    });

    let session;
    try {
      // User-shell env + the host-derived EMDASH_* vars; deliberately no CI=1
      // injection (spec: env parity — a documented breaking change).
      const env = buildTerminalEnv({
        baseEnv: await this.loadUserEnv(),
        overrides: buildScriptEnv(input.workspacePath, input.facts),
      });
      session = await this.registry.create(
        runKey,
        spawnSpec({
          command: input.command,
          shellSetup: input.shellSetup,
          cwd: input.workspacePath,
          env,
          cols: input.cols ?? DEFAULT_COLS,
          rows: input.rows ?? DEFAULT_ROWS,
        }),
        {
          output: log,
          onData: (chunk) => {
            outputTail = appendOutputTail(outputTail, chunk);
            this.updateRun(input, runId, (run) => ({ ...run, outputTail }));
          },
          onExit: (info) => {
            const run = this.active.get(runKey);
            if (run?.runId === runId) {
              if (run.timer) clearTimeout(run.timer);
              this.active.delete(runKey);
            }
            const finishedAt = this.now();
            this.updateRun(input, runId, (current) => {
              const next: ScriptRunState = {
                ...current,
                status: run?.stopRequested
                  ? 'cancelled'
                  : run?.timedOut
                    ? 'timed-out'
                    : info.exitCode === 0 && info.signal === null
                      ? 'succeeded'
                      : 'failed',
                finishedAt,
                exitCode: info.exitCode,
                signal: info.signal,
                outputTail,
                message: run?.stopRequested
                  ? 'Stopped'
                  : run?.timedOut
                    ? `Timed out after ${input.timeoutMs}ms`
                    : info.exitCode === 0 && info.signal === null
                      ? undefined
                      : info.signal !== null
                        ? `Exited with signal ${info.signal}`
                        : `Exited with code ${info.exitCode ?? 'unknown'}`,
              };
              resolveSettled(next);
              return next;
            });
          },
        }
      );
    } catch (error) {
      return err({
        type: 'spawn-failed',
        message: error instanceof Error ? error.message : String(error),
      });
    }

    const activeRun: ActiveRun = {
      runId,
      settled,
      timer: null,
      stopRequested: false,
      timedOut: false,
      kill: () => session.kill(),
    };
    if (input.timeoutMs !== undefined) {
      activeRun.timer = setTimeout(() => {
        activeRun.timedOut = true;
        this.logger.info?.(
          `script '${input.script}' timed out after ${input.timeoutMs}ms — killing`,
          { workspacePath: input.workspacePath }
        );
        session.kill();
      }, input.timeoutMs);
    }
    this.active.set(runKey, activeRun);

    const initial: ScriptRunState = {
      runId,
      script: input.script,
      provenance: input.provenance,
      status: 'running',
      startedAt: this.now(),
      pid: session.getPid(),
      outputTail: '',
    };
    this.runStates({ workspacePath: input.workspacePath }).update((previous) => ({
      ...previous,
      [input.script]: initial,
    }));
    return ok(initial);
  }

  async wait(input: WaitScriptRunInput): Promise<Result<ScriptRunState, ScriptRunNotFoundError>> {
    const runKey = runKeyFor(input);
    const active = this.active.get(runKey);
    if (active && (input.runId === undefined || active.runId === input.runId)) {
      return ok(await active.settled);
    }
    const last = this.lastRun(input);
    if (last && (input.runId === undefined || last.runId === input.runId)) {
      return ok(last);
    }
    return err({
      type: 'not-found',
      message: `No run for script '${input.script}' in this workspace`,
    });
  }

  stop(input: StopScriptRunInput): Result<void, ScriptRunNotFoundError> {
    const runKey = runKeyFor(input);
    const active = this.active.get(runKey);
    if (!active) {
      return err({
        type: 'not-found',
        message: `Script '${input.script}' is not running for this workspace`,
      });
    }
    active.stopRequested = true;
    if (active.timer) clearTimeout(active.timer);
    active.kill();
    return ok(undefined);
  }

  sendInput(input: ScriptRunInput): Result<void, ScriptRunNotFoundError> {
    if (!this.registry.write(runKeyFor(input), input.data)) {
      return err(notRunning(input.script));
    }
    return ok(undefined);
  }

  resize(input: ScriptRunResizeInput): Result<void, ScriptRunNotFoundError> {
    if (!this.registry.resize(runKeyFor(input), input.cols, input.rows)) {
      return err(notRunning(input.script));
    }
    return ok(undefined);
  }

  outputLog(key: ScriptRunKey): LiveSource {
    return this.logFor(key);
  }

  dispose(): void {
    this.disposed = true;
    for (const run of this.active.values()) {
      if (run.timer) clearTimeout(run.timer);
    }
    this.registry.killAll();
    this.active.clear();
    this.logs.clear();
    void this.runsHost.dispose();
    void this.runStates.dispose();
  }

  private updateRun(
    key: ScriptRunKey,
    runId: string,
    update: (current: ScriptRunState) => ScriptRunState
  ): void {
    // PTY data/exit events may arrive after killAll returns. The state family is
    // already gone during shutdown, so those late callbacks are intentionally inert.
    if (this.disposed) return;
    this.runStates({ workspacePath: key.workspacePath }).update((previous) => {
      const current = previous[key.script];
      // A newer run may have replaced this one; never clobber it with stale data.
      if (!current || current.runId !== runId) return previous;
      return { ...previous, [key.script]: update(current) };
    });
  }

  private lastRun(key: ScriptRunKey): ScriptRunState | undefined {
    return peek(this.runStates({ workspacePath: key.workspacePath }))[key.script];
  }

  private logFor(key: ScriptRunKey): LiveLogSource {
    const id = runKeyFor(key);
    let log = this.logs.get(id);
    if (!log) {
      log = new LiveLogSource();
      this.logs.set(id, log);
    }
    return log;
  }
}

function runKeyFor(key: ScriptRunKey): string {
  return `${key.workspacePath}\u0000${key.script}`;
}

function notRunning(script: ScriptKind): ScriptRunNotFoundError {
  return {
    type: 'not-found',
    message: `Script '${script}' is not running for this workspace`,
  };
}

function spawnSpec(input: {
  command: string;
  shellSetup: string;
  cwd: string;
  env: Record<string, string>;
  cols: number;
  rows: number;
}) {
  const command = input.shellSetup ? `${input.shellSetup}\n${input.command}` : input.command;
  if (process.platform === 'win32') {
    return {
      command: input.env.ComSpec ?? 'cmd.exe',
      args: ['/d', '/s', '/c', command],
      cwd: input.cwd,
      env: input.env,
      cols: input.cols,
      rows: input.rows,
    };
  }
  return {
    command: input.env.SHELL ?? '/bin/sh',
    args: ['-lc', command],
    cwd: input.cwd,
    env: input.env,
    cols: input.cols,
    rows: input.rows,
  };
}

function stripTerminalControls(value: string): string {
  return value
    .replace(/\x1b\[[0-9;]*[A-Za-z]/g, '')
    .replace(/\x1b\][^\x07]*\x07/g, '')
    .replace(/\x1b\][^\x1b]*\x1b\\/g, '')
    .replace(/\r/g, '');
}

function appendOutputTail(current: string, chunk: string): string {
  const next = current + stripTerminalControls(chunk);
  return next.length > OUTPUT_TAIL_CAP ? next.slice(-OUTPUT_TAIL_CAP) : next;
}
