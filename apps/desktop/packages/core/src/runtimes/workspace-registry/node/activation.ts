import { noopLogger, type Logger } from '@emdash/shared/logger';
import { systemClock, type Clock } from '@emdash/shared/scheduling';
import { type EmdashScriptsConfig } from '#primitives/emdash-config/api';
import type { WorkspaceRuntimeOverlay } from '../api/schemas';
import { readWorkspaceConfig } from './config-model';
import { DEFAULT_SCRIPT_TIMEOUT_MS, type WorkspaceScriptRunner } from './scripts-plane';

type WorkspaceActivation = NonNullable<WorkspaceRuntimeOverlay['activation']>;
type LifecycleScript = 'prepare' | 'setup' | 'run' | 'teardown';
type ScriptStepScript = 'prepare' | 'setup' | 'run';

export type ActivationLifecycleConfig = {
  scripts: EmdashScriptsConfig;
  shellSetup: string;
  autoRunSetup: boolean;
  autoRunRun: boolean;
};

/** A durable transition of one activation script's lifecycle step. */
export type WorkspaceScriptStepState = {
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped';
  message?: string;
};

export type WorkspaceDeactivationResult = {
  /** Non-null when the teardown script settled unsuccessfully. */
  teardownFailure: { message: string } | null;
};

export type WorkspaceActivationManagerOptions = {
  /** Overlay writer: null clears the activation block. */
  publishActivation: (id: string, activation: WorkspaceActivation | null) => void;
  /** Failed scripts become overlay notices; a later success clears them. */
  setNotice: (id: string, script: LifecycleScript, message: string) => void;
  clearNotice: (id: string, script: LifecycleScript) => void;
  /**
   * Resets the record's script-class lifecycle steps for a fresh activation: old
   * script steps are removed and one pending step is seeded per configured script —
   * the durable record shows the current activation's runs, never stale history.
   */
  resetScriptSteps: (id: string, scripts: ScriptStepScript[]) => void;
  /**
   * Durable step write for the one case observation cannot see: a script that never
   * started (run after a failed setup) settles as skipped. Every actual run's step
   * transitions come from the registry's observation of the scripts runtime — the
   * single step-writer (spec: activation-scripts-via-terminals).
   */
  recordScriptStep: (id: string, script: ScriptStepScript, state: WorkspaceScriptStepState) => void;
  /** Persists lastActivatedAt — the only durable trace of an activation. */
  recordActivated: (id: string, at: number) => Promise<void>;
  /**
   * The artifact gate (dependency gating): resolves once the background artifact copy
   * settled. Awaited only where scripts consume dependencies — before prepare and
   * before the setup→run chain; workspaces without those scripts never wait.
   */
  awaitArtifacts?: (id: string) => Promise<void>;
  /** The single execution plane: production wires the scripts-plane runner. */
  runner: WorkspaceScriptRunner;
  /**
   * Script resolution seam: the registry runtime serves this from its config live
   * model so no filesystem read sits inside the activation verb. The default reads
   * the file directly (standalone/test use only).
   */
  readScripts?: (id: string, workspacePath: string) => Promise<EmdashScriptsConfig>;
  /** Canonical resolver seam. Takes precedence over the legacy test-only readScripts seam. */
  resolveLifecycleConfig?: (
    id: string,
    workspacePath: string
  ) => Promise<ActivationLifecycleConfig>;
  clock?: Clock;
  logger?: Logger;
  teardownTimeoutMs?: number;
};

type ActiveState = {
  workspacePath: string;
  shellSetup: string;
  controller: AbortController;
  /** Resolves when the background setup → run chain settles (success or not). */
  background: Promise<void>;
  activation: WorkspaceActivation;
};

/**
 * The ephemeral activation plane (ADR 0005): prepare gates the verb's return, setup and
 * run continue in the background, and every script failure is a notice — never a verb
 * error. Nothing here is durable; a daemon restart leaves every workspace inactive.
 * Callers are responsible for serializing activate/deactivate per workspace.
 */
export class WorkspaceActivationManager {
  private readonly options: WorkspaceActivationManagerOptions;
  private readonly runner: WorkspaceScriptRunner;
  private readonly awaitArtifacts: (id: string) => Promise<void>;
  private readonly resolveLifecycleConfig: (
    id: string,
    workspacePath: string
  ) => Promise<ActivationLifecycleConfig>;
  private readonly clock: Clock;
  private readonly logger: Logger;
  private readonly teardownTimeoutMs: number;
  private readonly active = new Map<string, ActiveState>();

  constructor(options: WorkspaceActivationManagerOptions) {
    this.options = options;
    this.runner = options.runner;
    this.awaitArtifacts = options.awaitArtifacts ?? (async () => undefined);
    this.resolveLifecycleConfig =
      options.resolveLifecycleConfig ??
      (async (id, workspacePath) => ({
        scripts: await (options.readScripts ?? readWorkspaceScripts)(id, workspacePath),
        shellSetup: '',
        autoRunSetup: true,
        autoRunRun: true,
      }));
    this.clock = options.clock ?? systemClock;
    this.logger = options.logger ?? noopLogger;
    this.teardownTimeoutMs = options.teardownTimeoutMs ?? DEFAULT_SCRIPT_TIMEOUT_MS;
  }

  isActive(id: string): boolean {
    return this.active.has(id);
  }

  /** Resolves when prepare completes; setup/run continue in the background. */
  async activate(id: string, workspacePath: string): Promise<void> {
    if (this.active.has(id)) return;

    const policy = await this.resolveLifecycleConfig(id, workspacePath);
    const scripts: EmdashScriptsConfig = {
      ...policy.scripts,
      ...(policy.autoRunSetup ? {} : { setup: undefined }),
      ...(policy.autoRunRun ? {} : { run: undefined }),
    };
    // Overwrite, not append: the durable timeline shows this activation's runs only.
    this.options.resetScriptSteps(
      id,
      (['prepare', 'setup', 'run'] as const).filter((script) => scripts[script])
    );
    const controller = new AbortController();
    const state: ActiveState = {
      workspacePath,
      shellSetup: policy.shellSetup,
      controller,
      background: Promise.resolve(),
      activation: {
        phase: 'preparing',
        scripts: {
          prepare: scripts.prepare ? 'running' : 'skipped',
          setup: scripts.setup ? 'pending' : 'skipped',
          run: scripts.run ? 'pending' : 'skipped',
        },
        activatedAt: null,
      },
    };
    this.active.set(id, state);
    this.publish(id, state);

    if (scripts.prepare) {
      // Prepare chains after the artifact copy (spec: copy-artifacts → prepare →
      // active), so a dep-installing prepare runs against cloned node_modules. A
      // terminal clone failure resolves the gate — prepare degrades to a real install.
      await this.awaitArtifacts(id);
      if (!this.isCurrent(id, state)) return;
      const outcome = await this.runScript(id, state, 'prepare', scripts.prepare);
      if (!this.isCurrent(id, state)) return;
      state.activation.scripts.prepare = outcome === 'succeeded' ? 'succeeded' : 'failed';
    }

    const activatedAt = this.clock.now();
    state.activation.phase = 'active';
    state.activation.activatedAt = activatedAt;
    this.publish(id, state);
    await this.options.recordActivated(id, activatedAt);

    state.background = this.runBackgroundChain(id, state, scripts).catch((error) => {
      this.logger.warn?.(`background activation scripts for '${id}' failed unexpectedly`, {
        error,
      });
    });
  }

  /**
   * Aborts in-flight scripts and runs teardown, time-boxed and never throwing. No-op
   * when the workspace is not active — teardown runs at most once per activation.
   * Session killing is the caller's step; this owns only the script plane. A teardown
   * failure is reported to the caller: notice-only for plain deactivation, a removal
   * stage for the delete verbs (ADR 0006).
   */
  async deactivate(id: string): Promise<WorkspaceDeactivationResult> {
    const state = this.active.get(id);
    if (!state) return { teardownFailure: null };
    this.active.delete(id);

    state.controller.abort();
    await state.background;

    let teardownFailure: { message: string } | null = null;
    const policy = await this.resolveLifecycleConfig(id, state.workspacePath);
    const scripts = policy.scripts;
    if (scripts.teardown) {
      const outcome = await this.runner.run({
        id: 'teardown',
        command: scripts.teardown,
        shellSetup: policy.shellSetup,
        cwd: state.workspacePath,
        timeoutMs: this.teardownTimeoutMs,
      });
      if (outcome.status === 'succeeded') {
        this.options.clearNotice(id, 'teardown');
      } else {
        this.options.setNotice(id, 'teardown', outcome.message);
        teardownFailure = { message: outcome.message };
      }
    }
    this.options.publishActivation(id, null);
    return { teardownFailure };
  }

  /** Abandons all activations without teardown; used on runtime disposal only. */
  dispose(): void {
    for (const state of this.active.values()) {
      state.controller.abort();
    }
    this.active.clear();
  }

  private async runBackgroundChain(
    id: string,
    state: ActiveState,
    scripts: EmdashScriptsConfig
  ): Promise<void> {
    if (scripts.setup || scripts.run) {
      // Setup and run (dev servers) consume dependencies: wait for the artifact copy
      // to settle. Never gates activation itself — this chain is already background.
      await this.awaitArtifacts(id);
      if (!this.isCurrent(id, state)) return;
    }
    let setupSucceeded = true;
    if (scripts.setup) {
      state.activation.scripts.setup = 'running';
      this.publish(id, state);
      const outcome = await this.runScript(id, state, 'setup', scripts.setup);
      if (!this.isCurrent(id, state)) return;
      setupSucceeded = outcome === 'succeeded';
      state.activation.scripts.setup = setupSucceeded ? 'succeeded' : 'failed';
      this.publish(id, state);
    }

    if (!scripts.run) return;
    if (!setupSucceeded) {
      // Run waits on setup success; a failed setup means run never starts.
      state.activation.scripts.run = 'skipped';
      this.options.recordScriptStep(id, 'run', {
        status: 'skipped',
        message: 'Setup did not succeed',
      });
      this.publish(id, state);
      return;
    }
    state.activation.scripts.run = 'running';
    this.publish(id, state);
    const outcome = await this.runScript(id, state, 'run', scripts.run, { longRunning: true });
    if (!this.isCurrent(id, state)) return;
    state.activation.scripts.run = outcome === 'succeeded' ? 'exited' : 'failed';
    this.publish(id, state);
  }

  private async runScript(
    id: string,
    state: ActiveState,
    script: ScriptStepScript,
    command: string,
    options: { longRunning?: boolean } = {}
  ): Promise<'succeeded' | 'failed' | 'cancelled'> {
    // The run's durable step transitions come from observation, not from here: the
    // outcome below drives only sequencing (control flow) and notices.
    const outcome = await this.runner.run({
      id: script,
      command,
      shellSetup: state.shellSetup,
      cwd: state.workspacePath,
      signal: state.controller.signal,
      // Run scripts are dev-server-shaped: bounded only by deactivation, not a timeout.
      // 2^31-1 ms is Node's max timer value (~24 days), the closest thing to "never".
      ...(options.longRunning ? { timeoutMs: 2 ** 31 - 1 } : {}),
    });
    if (outcome.status === 'succeeded') {
      this.options.clearNotice(id, script);
      return 'succeeded';
    }
    if (outcome.status === 'cancelled') {
      // Deactivation stopped it on purpose; a notice would be noise.
      return 'cancelled';
    }
    this.options.setNotice(id, script, outcome.message);
    return 'failed';
  }

  private isCurrent(id: string, state: ActiveState): boolean {
    return this.active.get(id) === state;
  }

  private publish(id: string, state: ActiveState): void {
    if (!this.isCurrent(id, state)) return;
    this.options.publishActivation(id, {
      ...state.activation,
      scripts: { ...state.activation.scripts },
    });
  }
}

async function readWorkspaceScripts(
  _id: string,
  workspacePath: string
): Promise<EmdashScriptsConfig> {
  // Lenient by design: an unparseable .emdash.json must never block activation.
  return (await readWorkspaceConfig(workspacePath)).config.scripts ?? {};
}
