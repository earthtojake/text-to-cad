/**
 * `agents.list` on a cold launch: the handler waits for the first probe, up
 * to `COLD_LIST_WAIT_MS`, instead of answering an empty table the renderer
 * draws as "no agents" and redraws two seconds later. A probe that hangs
 * still gets an answer — empty, at the bound — and the broadcast follows.
 *
 * The handler is the real one; the detector it builds is given a fake
 * machine whose login shell answers when the test says so.
 */
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type * as Detect from "@main/agents/detect";
import type { DetectorProbes } from "@main/agents/detect";

const shell = vi.hoisted(() => ({
  release: (() => {}) as () => void,
  env: null as Promise<Record<string, string>> | null,
}));

vi.mock("@main/agents/detect", async (importOriginal) => {
  const actual = await importOriginal<typeof Detect>();
  const probes: DetectorProbes = {
    env: () => shell.env ?? Promise.resolve({ PATH: "/usr/local/bin" }),
    isExecutable: async (file) => file === "/usr/local/bin/claude",
    exists: async () => false,
    exec: async () => ({ stdout: "2.1.0 (Claude Code)", stderr: "", code: 0 }),
    homeDir: () => "/Users/me",
    platform: "darwin",
  };
  class FakeMachineDetector extends actual.AgentDetector {
    constructor() {
      super(undefined, probes);
    }
  }
  return { ...actual, AgentDetector: FakeMachineDetector };
});
vi.mock("@main/ipc/register", () => ({ broadcast: vi.fn(), IpcError: class extends Error {} }));
vi.mock("@main/acp/pty-backend", () => ({ spawnJobPty: vi.fn() }));

/** The login shell answers only when `release` is called. */
function slowShell() {
  shell.env = new Promise((resolve) => {
    shell.release = () => resolve({ PATH: "/usr/local/bin" });
  });
}

beforeEach(() => {
  vi.resetModules();
  shell.env = null;
});
afterEach(() => {
  vi.useRealTimers();
});

it("answers a cold list with the first probe's table, not an empty one", async () => {
  slowShell();
  const { agentsHandlers } = await import("@main/ipc/agents");
  const answer = agentsHandlers.agents.list();
  setTimeout(() => shell.release(), 20);
  const agents = await answer;
  expect(agents.length).toBeGreaterThan(0);
  expect(agents.find((agent) => agent.id === "claude-code")).toMatchObject({ installed: true, version: "2.1.0" });
});

it("answers empty at the bound when the probe hangs, and the cache after it lands", async () => {
  vi.useFakeTimers();
  slowShell();
  const { agentsHandlers, COLD_LIST_WAIT_MS } = await import("@main/ipc/agents");
  let answered: unknown[] | null = null;
  void agentsHandlers.agents.list().then((agents) => {
    answered = agents;
  });
  await vi.advanceTimersByTimeAsync(COLD_LIST_WAIT_MS - 1);
  expect(answered).toBeNull();
  await vi.advanceTimersByTimeAsync(1);
  expect(answered).toEqual([]);

  shell.release();
  await vi.runAllTimersAsync();
  const warm = await agentsHandlers.agents.list();
  expect(warm.length).toBeGreaterThan(0);
});
