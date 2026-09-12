import { describe, expect, it } from "vitest";

import { WarmAdapterPool, type WarmAdapter } from "@main/acp/warm";

/**
 * One idle adapter per agent, spawned and initialized before anyone asks
 * (README, "Opening a session": 0.7 s of a Codex session's load and 1.0 s of
 * a Claude one's). The rules that need holding are that it is handed out
 * once, that it is replaced afterwards, that a session in another directory
 * does not take it, and that quitting kills it.
 */

class FakeAdapter implements WarmAdapter {
  closed = 0;
  alive = true;

  constructor(readonly cwd: string) {}

  close(): void {
    this.closed += 1;
    this.alive = false;
  }
}

function pool(options: { fail?: boolean } = {}) {
  const spawned: FakeAdapter[] = [];
  const logs: string[] = [];
  const instance = new WarmAdapterPool<FakeAdapter>({
    spawn: async (_agentId, cwd) => {
      if (options.fail) {
        throw new Error("not signed in");
      }
      const adapter = new FakeAdapter(cwd);
      spawned.push(adapter);
      return adapter;
    },
    log: (line) => logs.push(line),
  });
  return { pool: instance, spawned, logs };
}

describe("WarmAdapterPool", () => {
  it("warms one adapter per agent and hands it out once", async () => {
    const { pool: warm, spawned } = pool();
    await warm.warm("codex", "/p");
    expect(spawned).toHaveLength(1);
    expect(warm.has("codex")).toBe(true);

    const taken = warm.take("codex", "/p");
    expect(taken).toBe(spawned[0]);
    // The same agent asked again gets a fresh spawn, not the one in use.
    expect(warm.take("codex", "/p")).toBeNull();
  });

  it("replaces the one it handed out", async () => {
    const { pool: warm, spawned } = pool();
    await warm.warm("codex", "/p");
    warm.take("codex", "/p");
    // The replacement is started by `take` and settles on the microtask queue.
    await Promise.resolve();
    await Promise.resolve();
    expect(spawned).toHaveLength(2);
    expect(warm.has("codex")).toBe(true);
  });

  it("does not warm a second adapter for an agent that has one", async () => {
    const { pool: warm, spawned } = pool();
    await warm.warm("codex", "/p");
    await warm.warm("codex", "/p");
    await warm.warm("codex", "/p");
    expect(spawned).toHaveLength(1);
    expect(warm.size).toBe(1);
  });

  it("coalesces concurrent warms of one agent into one spawn", async () => {
    const { pool: warm, spawned } = pool();
    await Promise.all([warm.warm("codex", "/p"), warm.warm("codex", "/p")]);
    expect(spawned).toHaveLength(1);
  });

  it("keeps one per agent, not one per app", async () => {
    const { pool: warm } = pool();
    await warm.warm("codex", "/p");
    await warm.warm("claude-code", "/p");
    expect(warm.size).toBe(2);
    expect(warm.has("codex")).toBe(true);
    expect(warm.has("claude-code")).toBe(true);
  });

  /**
   * An adapter is spawned in a directory and cannot be moved: `spawn`'s
   * `cwd`, the client's file confinement and the agent's own notion of where
   * it is all come from it. A worktree session therefore spawns its own, and
   * the pool keeps the adapter it has for the next session that matches.
   */
  it("refuses to hand an adapter to a session in another directory, and keeps it", async () => {
    const { pool: warm, spawned } = pool();
    await warm.warm("codex", "/project");
    expect(warm.take("codex", "/worktrees/thing")).toBeNull();
    expect(warm.has("codex")).toBe(true);
    expect(warm.take("codex", "/project")).toBe(spawned[0]);
  });

  it("throws away an adapter that died while it waited, and starts another", async () => {
    const { pool: warm, spawned } = pool();
    await warm.warm("codex", "/p");
    spawned[0]!.alive = false;
    expect(warm.take("codex", "/p")).toBeNull();
    expect(warm.has("codex")).toBe(false);
    await Promise.resolve();
    await Promise.resolve();
    expect(spawned).toHaveLength(2);
  });

  /** Nothing waited for it, so a failure is a log line and not an error. */
  it("logs a spawn that failed instead of rejecting", async () => {
    const { pool: warm, logs } = pool({ fail: true });
    await expect(warm.warm("codex", "/p")).resolves.toBeUndefined();
    expect(warm.has("codex")).toBe(false);
    expect(logs.join("\n")).toContain("could not be warmed");
  });

  it("closes every idle adapter on quit and refuses to warm another", async () => {
    const { pool: warm, spawned } = pool();
    await warm.warm("codex", "/p");
    await warm.warm("claude-code", "/p");
    warm.closeAll();
    expect(spawned.every((adapter) => adapter.closed === 1)).toBe(true);
    expect(warm.size).toBe(0);

    await warm.warm("codex", "/p");
    expect(spawned).toHaveLength(2);
    expect(warm.has("codex")).toBe(false);
  });

  it("closes an adapter that finished booting after the quit", async () => {
    const spawned: FakeAdapter[] = [];
    let release: (() => void) | null = null;
    const warm = new WarmAdapterPool<FakeAdapter>({
      spawn: async (_agentId, cwd) => {
        await new Promise<void>((resolve) => {
          release = resolve;
        });
        const adapter = new FakeAdapter(cwd);
        spawned.push(adapter);
        return adapter;
      },
    });
    const inflight = warm.warm("codex", "/p");
    warm.closeAll();
    release!();
    await inflight;
    expect(spawned[0]!.closed).toBe(1);
    expect(warm.size).toBe(0);
  });
});
