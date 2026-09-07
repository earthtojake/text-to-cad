/**
 * What each agent's sessions can be configured with, remembered between them.
 *
 * The composer's model and effort chips are drawn from a live session's
 * `configOptions`, which is the only place an agent says which models it has.
 * The new-session screen has no session, so it reads this instead: every
 * connected session's options are written here against its agent, an agent
 * that has never run in this app is **probed** once — spawn the adapter,
 * `initialize`, `session/new`, keep the config options, close without
 * prompting — and the model and effort chosen anywhere are stored as that
 * agent's defaults, which `SessionManager.create` applies to the next one.
 *
 * A probe that fails is silence, not an error: an agent that is not installed
 * or not signed in contributes no models to the new-session menu, which is
 * exactly what "do not show uninstalled models" means. One probe per agent is
 * in flight at a time, and a failed one is not retried until the app is
 * restarted or the agent's status changes.
 *
 * Dependencies are injected — storage, the probe, the broadcast — so this file
 * has no Electron, no sqlite and no adapter of its own.
 */
import type { ConfigOption } from "../../shared/acp/types";
import { effortOption, modelOption } from "../../shared/acp/options";
import type { AgentOptions } from "../../shared/ipc/agent-options";

export type AgentOptionsDeps = {
  read(): AgentOptions[];
  get(agentId: string): AgentOptions | null;
  writeOptions(agentId: string, options: ConfigOption[]): void;
  writeDefaults(agentId: string, defaults: { model?: string | null; effort?: string | null }): void;
  /** Spawn the agent far enough to read its `session/new` reply. */
  probe(agentId: string, projectId: string | null): Promise<ConfigOption[]>;
  onChange(all: AgentOptions[]): void;
  /** Failures land here rather than anywhere a person can see them. */
  onProbeFailed?: (agentId: string, error: unknown) => void;
};

export class AgentOptionStore {
  /** One probe per agent at a time; the entry is kept after it settles. */
  private readonly probes = new Map<string, Promise<void>>();
  private readonly failed = new Set<string>();

  constructor(private readonly deps: AgentOptionsDeps) {}

  list(): AgentOptions[] {
    return this.deps.read();
  }

  get(agentId: string): AgentOptions | null {
    return this.deps.get(agentId);
  }

  /** The values a new session with this agent should start at. */
  defaults(agentId: string): { model: string | null; effort: string | null } {
    const row = this.deps.get(agentId);
    return { model: row?.defaultModel ?? null, effort: row?.defaultEffort ?? null };
  }

  /**
   * A live session's options, against its agent. Called on `session/new`,
   * `session/load` and every `config_option_update`, so the cache is a
   * snapshot of the last session anyone actually ran.
   */
  remember(agentId: string, options: ConfigOption[]): void {
    if (options.length === 0) {
      return;
    }
    const before = this.deps.get(agentId);
    this.deps.writeOptions(agentId, options);
    this.failed.delete(agentId);
    if (!sameOptions(before?.options ?? [], options)) {
      this.deps.onChange(this.list());
    }
  }

  /**
   * The model or effort a session was just switched to, so the next session
   * starts where the last one ended. Anything else the agent exposes is
   * session-scoped and is not remembered.
   */
  rememberChoice(agentId: string, configId: string, value: string | boolean, options: ConfigOption[]): void {
    if (typeof value !== "string") {
      return;
    }
    const model = modelOption(options);
    const effort = effortOption(options);
    if (model && configId === model.id) {
      this.setDefaults(agentId, { model: value });
    } else if (effort && configId === effort.id) {
      this.setDefaults(agentId, { effort: value });
    }
  }

  setDefaults(agentId: string, defaults: { model?: string | null; effort?: string | null }): AgentOptions[] {
    this.deps.writeDefaults(agentId, defaults);
    const all = this.list();
    this.deps.onChange(all);
    return all;
  }

  /**
   * Take a snapshot if there is none. Resolves when the probe is done (or at
   * once when one is not needed); the caller does not wait on it, and neither
   * does the UI — a provider with no snapshot simply has no group in the
   * model menu until it answers.
   */
  async ensure(agentId: string, projectId: string | null): Promise<void> {
    if (this.deps.get(agentId)?.options.length || this.failed.has(agentId)) {
      return;
    }
    const running = this.probes.get(agentId);
    if (running) {
      return running;
    }
    const probe = this.deps
      .probe(agentId, projectId)
      .then((options) => {
        if (options.length > 0) {
          this.remember(agentId, options);
        } else {
          this.failed.add(agentId);
        }
      })
      .catch((error: unknown) => {
        this.failed.add(agentId);
        this.deps.onProbeFailed?.(agentId, error);
      })
      .finally(() => {
        this.probes.delete(agentId);
      });
    this.probes.set(agentId, probe);
    return probe;
  }

  /** A re-probe is worth a try again once the agent's install or login changed. */
  forgetFailures(): void {
    this.failed.clear();
  }
}

function sameOptions(before: ConfigOption[], after: ConfigOption[]): boolean {
  return JSON.stringify(before) === JSON.stringify(after);
}
