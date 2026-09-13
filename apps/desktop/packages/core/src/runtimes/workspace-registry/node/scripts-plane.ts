import { createScope, type Scope } from '@emdash/shared/concurrency';
import { noopLogger, type Logger } from '@emdash/shared/logger';
import type { ContractClient } from '@emdash/wire/rpc';
import { observe, remote, type RemoteModel } from '@emdash/wire/state';
// oxlint-disable-next-line emdash/core-module-boundaries -- the registry sequences lifecycle scripts through the scripts runtime (activation-scripts-via-terminals spec); the contract has no services-level home yet
import { scriptsContract } from '#runtimes/scripts/api';
// oxlint-disable-next-line emdash/core-module-boundaries -- see above
import type { ScriptKind, ScriptRunState, ScriptWorkspaceFacts } from '#runtimes/scripts/api';

export type ScriptsClient = ContractClient<typeof scriptsContract>;

export const DEFAULT_SCRIPT_TIMEOUT_MS = 5 * 60 * 1000;
const FAILURE_TAIL_EXCERPT_LENGTH = 600;

/**
 * The activation manager's runner seam. The scripts-plane runner below is the one
 * production implementation (spec: activation-scripts-via-terminals — one execution
 * plane); tests inject fakes.
 */
export type WorkspaceScriptRunInput = {
  id: string;
  command: string;
  shellSetup: string;
  cwd: string;
  signal?: AbortSignal;
  timeoutMs?: number;
};

export type WorkspaceScriptRunOutcome =
  | { status: 'succeeded'; outputTail: string }
  | {
      status: 'failed' | 'timed-out' | 'cancelled';
      message: string;
      exitCode?: number;
      outputTail: string;
    };

export type WorkspaceScriptRunner = {
  run(input: WorkspaceScriptRunInput): Promise<WorkspaceScriptRunOutcome>;
};

/** For registries constructed without a scripts client (tests): fail honestly. */
export function unavailableScriptRunner(): WorkspaceScriptRunner {
  return {
    async run(input) {
      return {
        status: 'failed',
        message: `Script "${input.id}" could not run: no scripts runtime is available`,
        outputTail: '',
      };
    },
  };
}

/** Folds the tail of a failed run's output into its human-facing message. */
export function failureMessageWithTail(message: string, outputTail: string): string {
  const tail = outputTail.trim();
  if (tail.length === 0) return message;
  const excerpt =
    tail.length > FAILURE_TAIL_EXCERPT_LENGTH
      ? `…${tail.slice(-FAILURE_TAIL_EXCERPT_LENGTH)}`
      : tail;
  return `${message}\n${excerpt}`;
}

/**
 * The activation manager's runner, backed by the scripts runtime (spec:
 * activation-scripts-via-terminals — one execution plane). Start + wait carry the
 * run; an abort maps onto the stop verb, so deactivation kills through the same
 * control everyone else uses. Facts are the registry's record facts — the env the
 * script sees is identical to a manual run's by construction.
 */
export function createScriptsPlaneRunner(options: {
  client: ScriptsClient;
  factsFor: (workspacePath: string) => Promise<ScriptWorkspaceFacts>;
  logger?: Logger;
}): WorkspaceScriptRunner {
  const logger = options.logger ?? noopLogger;
  return {
    async run(input): Promise<WorkspaceScriptRunOutcome> {
      const script = input.id as ScriptKind;
      const key = { workspacePath: input.cwd, script };
      const stop = () => {
        void Promise.resolve(options.client.stop(key)).catch((error) => {
          logger.warn?.(`stopping script '${script}' failed`, { error });
        });
      };
      const facts = await options.factsFor(input.cwd);
      input.signal?.addEventListener('abort', stop, { once: true });
      try {
        const started = await options.client.start({
          ...key,
          command: input.command,
          shellSetup: input.shellSetup,
          provenance: 'activation',
          facts,
          timeoutMs: input.timeoutMs ?? DEFAULT_SCRIPT_TIMEOUT_MS,
        });
        if (!started.success) {
          return {
            status: 'failed',
            message: started.error.message,
            outputTail: '',
          };
        }
        // The abort may have landed between start and the listener firing.
        if (input.signal?.aborted) stop();
        const settled = await options.client.wait({ ...key, runId: started.data.runId });
        if (!settled.success) {
          return { status: 'failed', message: settled.error.message, outputTail: '' };
        }
        return toRunnerOutcome(script, settled.data);
      } finally {
        input.signal?.removeEventListener('abort', stop);
      }
    },
  };
}

function toRunnerOutcome(script: ScriptKind, run: ScriptRunState): WorkspaceScriptRunOutcome {
  if (run.status === 'succeeded') return { status: 'succeeded', outputTail: run.outputTail };
  const status = run.status === 'running' ? 'failed' : run.status;
  const message = run.message ?? `Script "${script}" ${status}`;
  return {
    status,
    message: failureMessageWithTail(message, run.outputTail),
    ...(run.exitCode !== null && run.exitCode !== undefined ? { exitCode: run.exitCode } : {}),
    outputTail: run.outputTail,
  };
}

export type ObservedScriptRun = {
  workspacePath: string;
  script: ScriptKind;
  runId: string;
  status: ScriptRunState['status'];
  provenance: ScriptRunState['provenance'];
  message?: string;
  outputTail: string;
};

/**
 * The single step-writer's eye (spec: observation is the single step-writer): watches
 * the scripts runtime's per-workspace run state and surfaces every transition —
 * whoever started the run — so the registry mirrors activation, manual, and retry
 * runs into durable lifecycle steps with no special routing. A run vanishing from
 * the model without settling (scripts worker restart) surfaces as a synthetic
 * cancelled transition, so the timeline never shows a phantom in-flight run.
 */
export class ScriptRunsObserver {
  private readonly client: ScriptsClient;
  private readonly onRun: (run: ObservedScriptRun) => void;
  private readonly scope: Scope;
  private readonly runs: RemoteModel<typeof scriptsContract.runs>;
  private readonly watched = new Map<string, Scope>();
  /** Last seen run per workspacePath\0script — the transition filter. */
  private readonly seen = new Map<
    string,
    { runId: string; provenance: ScriptRunState['provenance']; status: ScriptRunState['status'] }
  >();

  constructor(options: { client: ScriptsClient; onRun: (run: ObservedScriptRun) => void }) {
    this.client = options.client;
    this.onRun = options.onRun;
    this.scope = createScope({ label: 'workspace-registry:script-runs-observer' });
    this.runs = remote(scriptsContract.runs, this.client.runs, { scope: this.scope });
  }

  /** Reconciles the watched set of workspace paths; extra watchers are released. */
  sync(paths: ReadonlySet<string>): void {
    for (const [path, scope] of this.watched) {
      if (!paths.has(path)) {
        this.watched.delete(path);
        for (const key of this.seen.keys()) {
          if (key.startsWith(`${path}\u0000`)) this.seen.delete(key);
        }
        void scope.dispose();
      }
    }
    for (const path of paths) {
      if (this.watched.has(path)) continue;
      const scope = createScope({ label: `script-runs:${path}` });
      this.watched.set(path, scope);
      const model = this.runs({ workspacePath: path });
      observe(
        model.states.current,
        (snapshot) => {
          if (snapshot.status === 'loading') return;
          this.apply(path, snapshot.value ?? {});
        },
        { scope, immediate: true }
      );
    }
  }

  dispose(): void {
    for (const scope of this.watched.values()) void scope.dispose();
    this.watched.clear();
    this.seen.clear();
    void this.scope.dispose();
  }

  private apply(workspacePath: string, runs: Record<string, ScriptRunState>): void {
    const present = new Set<string>();
    for (const run of Object.values(runs)) {
      const key = `${workspacePath}\u0000${run.script}`;
      present.add(run.script);
      const previous = this.seen.get(key);
      if (previous?.runId === run.runId && previous.status === run.status) continue;
      this.seen.set(key, { runId: run.runId, provenance: run.provenance, status: run.status });
      this.onRun({
        workspacePath,
        script: run.script,
        runId: run.runId,
        status: run.status,
        provenance: run.provenance,
        ...(run.message !== undefined ? { message: run.message } : {}),
        outputTail: run.outputTail,
      });
    }
    // A previously seen run gone from the model without settling: the scripts worker
    // restarted underneath us. Settle it as cancelled so the step never hangs.
    for (const [key, previous] of [...this.seen.entries()]) {
      if (!key.startsWith(`${workspacePath}\u0000`)) continue;
      const script = key.slice(workspacePath.length + 1) as ScriptKind;
      if (present.has(script)) continue;
      this.seen.delete(key);
      if (previous.status === 'running') {
        this.onRun({
          workspacePath,
          script,
          runId: previous.runId,
          status: 'cancelled',
          provenance: previous.provenance,
          message: 'Interrupted by a scripts runtime restart',
          outputTail: '',
        });
      }
    }
  }
}
