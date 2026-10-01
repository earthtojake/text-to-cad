/**
 * `agents.list` on a warm launch: the real handler, built on a detector with
 * a stored table, answers before the login shell has (the cold path waits for
 * it), and the order says so: no clock is read.
 */
import { beforeEach, expect, it, vi } from "vitest";

import type * as Detect from "@main/agents/detect";
import type { DetectorProbes } from "@main/agents/detect";
import { AGENT_PROVIDERS } from "@main/agents/registry";

const machine = vi.hoisted(() => ({
  stored: undefined as unknown,
  /** Whether the login shell has answered; it answers when `release` is called. */
  shellDone: false,
  release: (() => {}) as () => void,
  gate: Promise.resolve({ PATH: "/usr/local/bin" }),
}));

vi.mock("@main/agents/detect", async (importOriginal) => {
  const actual = await importOriginal<typeof Detect>();
  const probes: DetectorProbes = {
    env: () => machine.gate,
    isExecutable: async (file) => file === "/usr/local/bin/claude",
    exists: async () => false,
    exec: async () => ({ stdout: "2.1.0 (Claude Code)", stderr: "", code: 0 }),
    homeDir: () => "/Users/me",
    platform: "darwin",
  };
  // The handler's own cache argument is kept; only the machine is fake.
  class FakeMachineDetector extends actual.AgentDetector {
    constructor(providers?: undefined, _probes?: undefined, cache?: Detect.AgentsCache) {
      super(providers, probes, cache);
    }
  }
  return { ...actual, AgentDetector: FakeMachineDetector };
});
vi.mock("@main/db/repositories", () => ({
  settings: { agentsCache: () => machine.stored, setAgentsCache: (value: unknown) => void (machine.stored = value) },
}));
vi.mock("@main/app-paths", () => ({ appVersion: () => "9.9.9", appRoot: () => "", resourcesDir: () => "" }));
vi.mock("@main/ipc/register", () => ({ broadcast: vi.fn(), IpcError: class extends Error {} }));
vi.mock("@main/acp/pty-backend", () => ({ spawnJobPty: vi.fn() }));

beforeEach(() => {
  vi.resetModules();
  machine.shellDone = false;
  machine.gate = new Promise((resolve) => {
    machine.release = () => {
      machine.shellDone = true;
      resolve({ PATH: "/usr/local/bin" });
    };
  });
});

const stored = (version: string) => ({
  version,
  statuses: AGENT_PROVIDERS.map((provider) => ({
    ...provider,
    installed: true,
    binaryPath: "/old/claude",
    version: "1.0.0",
    auth: "unauthenticated",
    checkedAt: 1,
  })),
});

it("answers a warm list from the stored table before the shell has answered", async () => {
  machine.stored = stored("9.9.9");
  const { agentsHandlers } = await import("@main/ipc/agents");
  const agents = await agentsHandlers.agents.list();
  // The shell is still out: the answer came first, and it is the stored table.
  expect(machine.shellDone).toBe(false);
  expect(agents.length).toBe(AGENT_PROVIDERS.length);
  expect(agents.every((agent) => agent.probing === true)).toBe(true);
  machine.release();
});

it("waits for the shell when the stored table is another version's", async () => {
  machine.stored = stored("9.9.8");
  const { agentsHandlers } = await import("@main/ipc/agents");
  const answer = agentsHandlers.agents.list();
  // Nothing to answer with until the shell has: this list is its table.
  machine.release();
  const agents = await answer;
  expect(machine.shellDone).toBe(true);
  expect(agents.some((agent) => agent.probing)).toBe(false);
  expect(agents.find((agent) => agent.id === "claude-code")).toMatchObject({ version: "2.1.0" });
});
