/**
 * `agents.login` on a warm launch: the binary it signs in with is this
 * launch's probe's, not the last launch's row — the CLI may have moved (or
 * been installed) since, and a login started from a stale path fails.
 *
 * The handler is the real one on a fake machine whose login shell answers
 * when the test says so; only the pty job is replaced, to see its argument.
 */
import { beforeEach, expect, it, vi } from "vitest";

import type * as Detect from "@main/agents/detect";
import type { DetectorProbes } from "@main/agents/detect";
import { AGENT_PROVIDERS } from "@main/agents/registry";

const machine = vi.hoisted(() => ({
  release: (() => {}) as () => void,
  gate: Promise.resolve({ PATH: "/usr/local/bin" }),
  loggedInWith: [] as (string | null)[],
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
  class FakeMachineDetector extends actual.AgentDetector {
    constructor(providers?: undefined, _probes?: undefined, cache?: Detect.AgentsCache) {
      super(providers, probes, cache);
    }
  }
  return { ...actual, AgentDetector: FakeMachineDetector };
});
vi.mock("@main/agents/auth", () => ({
  startLogin: (_runner: unknown, _provider: unknown, binaryPath: string | null) => {
    machine.loggedInWith.push(binaryPath);
    return { id: "job-1" };
  },
}));
vi.mock("@main/db/repositories", () => ({
  settings: {
    agentsCache: () => ({
      version: "9.9.9",
      statuses: AGENT_PROVIDERS.map((provider) => ({
        ...provider,
        installed: true,
        binaryPath: "/old/claude",
        version: "1.0.0",
        auth: "unauthenticated",
        checkedAt: 1,
      })),
    }),
    setAgentsCache: () => {},
  },
}));
vi.mock("@main/app-paths", () => ({ appVersion: () => "9.9.9", appRoot: () => "", resourcesDir: () => "" }));
vi.mock("@main/ipc/register", () => ({ broadcast: vi.fn(), IpcError: class extends Error {} }));
vi.mock("@main/acp/pty-backend", () => ({ spawnJobPty: vi.fn() }));

beforeEach(() => {
  vi.resetModules();
  machine.loggedInWith = [];
  machine.gate = new Promise((resolve) => {
    machine.release = () => resolve({ PATH: "/usr/local/bin" });
  });
});

it("signs in with the binary this launch's probe found, not the last launch's path", async () => {
  const { agentsHandlers } = await import("@main/ipc/agents");
  const started = agentsHandlers.agents.login({ agentId: "claude-code" });
  machine.release();
  await started;
  expect(machine.loggedInWith).toEqual(["/usr/local/bin/claude"]);
});
