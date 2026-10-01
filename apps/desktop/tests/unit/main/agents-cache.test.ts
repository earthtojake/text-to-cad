/**
 * The detector's table survives a launch: a warm `agents.list` answers at once
 * with the last launch's rows marked `probing`, the probe's table replaces
 * them on the `agents.status` broadcast, and a table stored by another build
 * of the app is not trusted.
 *
 * The detector runs on a fake machine whose login shell answers when the test
 * says so; the cache is an in-memory stand-in for the settings table.
 */
import { beforeEach, expect, it, vi } from "vitest";

import { settingsAgentsCache } from "@main/agents/cache";
import { AgentDetector, type AgentsCache, type DetectorProbes } from "@main/agents/detect";
import { AGENT_PROVIDERS } from "@main/agents/registry";
import type { AgentStatus } from "@shared/agents";

const shell = vi.hoisted(() => ({ release: (() => {}) as () => void, env: null as Promise<Record<string, string>> | null }));

/** What the last launch found: Claude Code installed, and signed out. */
const lastLaunch: AgentStatus[] = AGENT_PROVIDERS.map((provider) => ({
  ...provider,
  installed: provider.id === "claude-code",
  binaryPath: provider.id === "claude-code" ? "/old/bin/claude" : null,
  version: provider.id === "claude-code" ? "1.0.0" : null,
  auth: provider.id === "claude-code" ? "unauthenticated" : "unknown",
  checkedAt: 1,
}));

/** This launch's machine: Claude Code is at a new path, and signed in. */
function probes(): DetectorProbes {
  return {
    env: () => shell.env ?? Promise.resolve({ PATH: "/usr/local/bin" }),
    isExecutable: async (file) => file === "/usr/local/bin/claude",
    exists: async () => false,
    exec: async (_file, args) => ({ stdout: args[0] === "--version" ? "2.1.0 (Claude Code)" : "", stderr: "", code: 0 }),
    homeDir: () => "/Users/me",
    platform: "darwin",
  };
}

/** The shell answers only when `release` is called. */
function slowShell() {
  shell.env = new Promise((resolve) => {
    shell.release = () => resolve({ PATH: "/usr/local/bin" });
  });
}

function memoryStore(initial?: unknown) {
  let value = initial;
  return {
    agentsCache: () => value,
    setAgentsCache: (next: unknown) => {
      value = next;
    },
    get value() {
      return value;
    },
  };
}

beforeEach(() => {
  shell.env = null;
});

it("answers from the last launch's table before the probe resolves, then broadcasts the fresh one", async () => {
  slowShell();
  const store = memoryStore({ version: "1.2.3", statuses: lastLaunch });
  const detector = new AgentDetector(undefined, probes(), settingsAgentsCache(store, () => "1.2.3"));
  const broadcasts: AgentStatus[][] = [];
  detector.onChange((statuses) => broadcasts.push(statuses));

  const started = performance.now();
  const answered = await detector.listWithin(3_000);
  const took = performance.now() - started;
  // The shell has not answered: this is the cache, every row provisional.
  expect(answered).toHaveLength(AGENT_PROVIDERS.length);
  expect(answered.every((row) => row.probing === true)).toBe(true);
  expect(answered.find((row) => row.id === "claude-code")).toMatchObject({ auth: "unauthenticated", version: "1.0.0" });
  expect(broadcasts).toHaveLength(0);
  expect(took).toBeLessThan(50);

  shell.release();
  const fresh = await detector.settled();
  expect(broadcasts).toEqual([fresh]);
  expect(fresh.some((row) => row.probing)).toBe(false);
  expect(fresh.find((row) => row.id === "claude-code")).toMatchObject({
    installed: true,
    binaryPath: "/usr/local/bin/claude",
    version: "2.1.0",
    auth: "authenticated",
  });
  // Later answers are the probe's, unmarked, and the store now holds them.
  expect((await detector.listWithin(3_000)).some((row) => row.probing)).toBe(false);
  expect((store.value as { version: string }).version).toBe("1.2.3");
  expect((store.value as { statuses: AgentStatus[] }).statuses.find((row) => row.id === "claude-code")?.auth).toBe("authenticated");
});

it("does not act on a cache from a different app version, and waits for the probe as a cold launch does", async () => {
  slowShell();
  const store = memoryStore({ version: "1.2.2", statuses: lastLaunch });
  expect(settingsAgentsCache(store, () => "1.2.3").read()).toBeNull();

  const detector = new AgentDetector(undefined, probes(), settingsAgentsCache(store, () => "1.2.3"));
  const answer = detector.listWithin(3_000);
  setTimeout(() => shell.release(), 20);
  const table = await answer;
  expect(table.length).toBeGreaterThan(0);
  expect(table.some((row) => row.probing)).toBe(false);
  expect(table.find((row) => row.id === "claude-code")).toMatchObject({ version: "2.1.0" });
});

it("ignores a table that is unreadable or missing a provider", () => {
  const read = (value: unknown) => settingsAgentsCache(memoryStore(value), () => "1.2.3").read();
  expect(read(undefined)).toBeNull();
  expect(read({ version: "1.2.3", statuses: "garbage" })).toBeNull();
  expect(read({ version: "1.2.3", statuses: lastLaunch.slice(1) })).toBeNull();
  expect(read({ version: "1.2.3", statuses: lastLaunch })).toHaveLength(lastLaunch.length);
});

it("keeps the rows, flagged, if the probe fails: none stays 'probing', and the table is not empty", async () => {
  shell.env = Promise.reject(new Error("no login shell"));
  shell.env.catch(() => undefined);
  const cache: AgentsCache = { read: () => lastLaunch, write: vi.fn() };
  const detector = new AgentDetector(undefined, probes(), cache);
  const broadcasts: AgentStatus[][] = [];
  detector.onChange((statuses) => broadcasts.push(statuses));
  expect((await detector.listWithin(3_000)).every((row) => row.probing)).toBe(true);
  await detector.settled().catch(() => undefined);
  // An empty table would be read as "no agent ready — sign in": the wrong cause.
  expect(broadcasts).toHaveLength(1);
  expect(broadcasts[0]).toHaveLength(AGENT_PROVIDERS.length);
  expect(broadcasts[0]!.every((row) => row.probeFailed === true && !row.probing)).toBe(true);
  expect(cache.write).not.toHaveBeenCalled();
});
