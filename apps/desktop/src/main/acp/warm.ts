/**
 * One idle adapter per agent, spawned and `initialize`d before anyone asks.
 *
 * Measured on this machine (README, "Opening a session"): getting an adapter
 * to the point where it will answer a request is 0.7 s for Codex and 1.0 s
 * for Claude Code — most of a Codex session's whole load, and 40% of a
 * Claude one's. The `spawn()` call itself is a millisecond; what costs is
 * the adapter's own boot, and it shows up inside the `initialize` round
 * trip. That is the part that can be paid in advance, so it is.
 *
 * The rules are small on purpose:
 *
 *   - **At most one per agent.** An idle adapter is a whole Node process; a
 *     pool of them for eight providers is a pool nobody asked for.
 *   - **Handed out once.** `take` removes it and starts its replacement, so
 *     the second session of a burst spawns its own rather than waiting for
 *     one that is already busy.
 *   - **Matched by directory.** An adapter is spawned in a directory and
 *     cannot be moved: `spawn`'s `cwd`, the client's file confinement and
 *     the agent's own notion of where it is all come from it. A session in a
 *     worktree therefore does not take the project's warm adapter — it
 *     spawns its own, and the pool keeps the one it has for the next session
 *     that does match.
 *   - **Killed on quit**, with the adapters of live sessions
 *     (`SessionManager.closeAll`); each is registered in the children
 *     registry by `SessionConnection` itself.
 */

/** What the pool needs of an adapter: where it runs, whether it lives, how to end it. */
export interface WarmAdapter {
  readonly cwd: string;
  readonly alive: boolean;
  close(): void;
}

export type WarmPoolDeps<A extends WarmAdapter> = {
  /** Spawn one adapter for this agent in this directory and `initialize` it. */
  spawn: (agentId: string, cwd: string) => Promise<A>;
  log?: (line: string) => void;
};

export class WarmAdapterPool<A extends WarmAdapter> {
  private readonly idle = new Map<string, A>();
  private readonly warming = new Map<string, Promise<void>>();
  private stopped = false;

  constructor(private readonly deps: WarmPoolDeps<A>) {}

  /**
   * Have an idle adapter ready for this agent in this directory. A no-op
   * when one is already there or already on its way — and a failure is a
   * log line, never an error: nothing waited for it.
   */
  warm(agentId: string, cwd: string): Promise<void> {
    if (this.stopped) {
      return Promise.resolve();
    }
    const existing = this.idle.get(agentId);
    if (existing?.alive && existing.cwd === cwd) {
      return Promise.resolve();
    }
    const inflight = this.warming.get(agentId);
    if (inflight) {
      return inflight;
    }
    const work = this.deps
      .spawn(agentId, cwd)
      .then((adapter) => {
        // Quit, or a real session took the slot while this one was booting.
        if (this.stopped || this.idle.has(agentId)) {
          adapter.close();
          return;
        }
        this.idle.set(agentId, adapter);
        this.deps.log?.(`[acp] ${agentId} warmed in ${cwd}`);
      })
      .catch((error: unknown) => {
        this.deps.log?.(`[acp] ${agentId} could not be warmed: ${String(error)}`);
      })
      .finally(() => {
        this.warming.delete(agentId);
      });
    this.warming.set(agentId, work);
    return work;
  }

  /**
   * The idle adapter for this agent, if it is alive and was spawned in this
   * directory. Removed from the pool and replaced; null means the caller
   * spawns its own.
   */
  take(agentId: string, cwd: string): A | null {
    const adapter = this.idle.get(agentId);
    if (!adapter) {
      return null;
    }
    if (!adapter.alive) {
      this.idle.delete(agentId);
      void this.warm(agentId, cwd);
      return null;
    }
    if (adapter.cwd !== cwd) {
      return null;
    }
    this.idle.delete(agentId);
    void this.warm(agentId, cwd);
    return adapter;
  }

  /** Whether an idle adapter is waiting for this agent (the tests, and the log line). */
  has(agentId: string): boolean {
    return this.idle.get(agentId)?.alive === true;
  }

  get size(): number {
    return this.idle.size;
  }

  /** On quit: kill every idle adapter, and refuse to warm another. */
  closeAll(): void {
    this.stopped = true;
    for (const [agentId, adapter] of [...this.idle]) {
      this.idle.delete(agentId);
      adapter.close();
    }
  }
}
