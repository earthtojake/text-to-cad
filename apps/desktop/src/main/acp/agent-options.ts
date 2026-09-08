/**
 * What each agent's sessions can be configured with, remembered between them.
 *
 * The composer's model, effort and mode chips are drawn from a live session's
 * `configOptions` and `modes`, which is the only place an agent says which
 * models and which modes it has. The new-session screen has no session, so it
 * reads this instead: every connected session's options and modes are written
 * here against its agent, an agent that has never run in this app is
 * **probed** once — spawn the adapter, `initialize`, `session/new`, keep what
 * it answered, close without prompting — and the model, effort and mode
 * chosen anywhere are stored as that agent's defaults, which
 * `SessionManager.create` applies to the next one.
 *
 * **The effort belongs to the model, not to the agent.** Claude reports its
 * `effort` option for whichever model the session is on, with the levels that
 * model has — `Xhigh` for one, not for the next — so the memory is a map from
 * model value to level (`setEffort`, `effortFor`), and so is the cache of the
 * levels themselves (`AgentOptions.effortOptions`, filled by `remember`).
 * Switching model and switching back comes back to the level that was chosen
 * there; the model and the mode stay per provider.
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
import type { ConfigOption, SessionMode } from "../../shared/acp/types";
import { NO_MODEL, effortModelKey, effortOption, modeOption, modelOption } from "../../shared/acp/options";
import type { AgentOptions } from "../../shared/ipc/agent-options";

/** What an agent last said a session of its own can be configured with. */
export type AgentSnapshot = { configOptions: ConfigOption[]; modes: SessionMode[] };

export type AgentOptionsDeps = {
  read(): AgentOptions[];
  get(agentId: string): AgentOptions | null;
  writeOptions(agentId: string, options: ConfigOption[], modes: SessionMode[]): void;
  writeDefaults(agentId: string, defaults: { model?: string | null; mode?: string | null }): void;
  /** The effort picked for one of this agent's models; `null` forgets it. */
  writeEffort(agentId: string, model: string, effort: string | null): void;
  /** Spawn the agent far enough to read its `session/new` reply. */
  probe(agentId: string, projectId: string | null): Promise<AgentSnapshot>;
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

  /**
   * The per-provider values a new session with this agent should start at.
   * The effort is not among them: it is remembered per model and read with
   * `effortFor`, once the model the session is actually on is known.
   */
  defaults(agentId: string): { model: string | null; mode: string | null } {
    const row = this.deps.get(agentId);
    return { model: row?.defaultModel ?? null, mode: row?.defaultMode ?? null };
  }

  /**
   * The effort level the person last picked for one of this agent's models,
   * and nothing else — no fallback to another model's level, and none to the
   * agent's own current, which is where a session already is. `null` means
   * "leave it alone".
   */
  effortFor(agentId: string, model: string | null): string | null {
    return this.deps.get(agentId)?.defaultEfforts[model ?? NO_MODEL] ?? null;
  }

  /**
   * A live session's options and modes, against its agent. Called on
   * `session/new`, `session/load` and every `config_option_update`, so the
   * cache is a snapshot of the last session anyone actually ran.
   */
  remember(agentId: string, options: ConfigOption[], modes: SessionMode[] = []): void {
    if (options.length === 0 && modes.length === 0) {
      return;
    }
    const before = this.deps.get(agentId);
    this.deps.writeOptions(agentId, options, modes);
    this.failed.delete(agentId);
    if (!same(before?.options ?? [], options) || !same(before?.modes ?? [], modes)) {
      this.deps.onChange(this.list());
    }
  }

  /**
   * The model, effort or mode a session was just switched to, so the next
   * session starts where the last one ended. Anything else the agent exposes
   * is session-scoped and is not remembered.
   *
   * `options` is the set as it was *before* the call, which is what makes the
   * effort keyable: the model in it is the model the level was picked under,
   * and a model switch would have rewritten it.
   *
   * The mode is here as well as in `rememberMode` because an agent that
   * sends its modes as a `mode` config option (Codex) switches them through
   * `set_config_option`, and one that sends `modes` (Claude) through
   * `set_mode`; the chip is the same chip either way.
   */
  rememberChoice(agentId: string, configId: string, value: string | boolean, options: ConfigOption[]): void {
    if (typeof value !== "string") {
      return;
    }
    const model = modelOption(options);
    const effort = effortOption(options);
    const mode = modeOption(options);
    if (model && configId === model.id) {
      // Deliberately nothing about the effort: the levels of the model being
      // left are still that model's, and the one being arrived at keeps
      // whatever was chosen there last.
      this.setDefaults(agentId, { model: value });
    } else if (effort && configId === effort.id) {
      this.setEffort(agentId, effortModelKey(options), value);
    } else if (mode && configId === mode.id) {
      this.setDefaults(agentId, { mode: value });
    }
  }

  /** The mode a live session was switched into, through `session/set_mode`. */
  rememberMode(agentId: string, modeId: string): void {
    this.setDefaults(agentId, { mode: modeId });
  }

  setDefaults(agentId: string, defaults: { model?: string | null; mode?: string | null }): AgentOptions[] {
    this.deps.writeDefaults(agentId, defaults);
    const all = this.list();
    this.deps.onChange(all);
    return all;
  }

  /** The effort for one model, remembered against that model alone. */
  setEffort(agentId: string, model: string, effort: string | null): AgentOptions[] {
    this.deps.writeEffort(agentId, model, effort);
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
      .then((snapshot) => {
        if (snapshot.configOptions.length > 0 || snapshot.modes.length > 0) {
          this.remember(agentId, snapshot.configOptions, snapshot.modes);
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

function same(before: unknown, after: unknown): boolean {
  return JSON.stringify(before) === JSON.stringify(after);
}
