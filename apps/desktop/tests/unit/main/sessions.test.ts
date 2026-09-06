import { mkdtemp, realpath } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

import { AgentDetector } from "@main/agents/detect";
import { spawnProcessTerminal } from "@main/acp/process-backend";
import { SessionManager, diffCounts, titleFromPrompt, type SessionRepository } from "@main/acp/sessions";
import type { AgentProvider } from "@shared/agents";
import type { IpcEventChannel } from "@shared/ipc";
import type { Session } from "@shared/types";

const FAKE_AGENT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "fake-agent", "index.mjs");

describe("titleFromPrompt", () => {
  it("takes the first non-empty line, collapsed, and truncates with an ellipsis", () => {
    expect(titleFromPrompt([{ type: "text", text: "\n\n  Model the   wrist\nmore" }])).toBe("Model the wrist");
    const long = "x".repeat(80);
    expect(titleFromPrompt([{ type: "text", text: long }])).toHaveLength(60);
    expect(titleFromPrompt([{ type: "text", text: long }]).endsWith("…")).toBe(true);
    expect(titleFromPrompt([{ type: "image", data: "", mimeType: "image/png", uri: null }])).toBe("Image");
    expect(titleFromPrompt([{ type: "text", text: "   " }])).toBe("New session");
  });
});

describe("diffCounts", () => {
  it("counts lines added and removed as a multiset difference", () => {
    expect(diffCounts("a\nb\nc", "a\nc\nd\nd")).toEqual({ insertions: 2, deletions: 1 });
    expect(diffCounts("", "new\nfile")).toEqual({ insertions: 2, deletions: 0 });
    expect(diffCounts("same", "same")).toEqual({ insertions: 0, deletions: 0 });
  });
});

/* -------------------------------------------------------------------------- */
/* SessionManager                                                              */
/* -------------------------------------------------------------------------- */

function memoryRepo(): SessionRepository & { rows: Map<string, Session> } {
  const rows = new Map<string, Session>();
  return {
    rows,
    list: (projectId) =>
      [...rows.values()]
        .filter((row) => !projectId || row.projectId === projectId)
        .sort((a, b) => b.updatedAt - a.updatedAt),
    get: (id) => rows.get(id) ?? null,
    upsert: (session) => {
      rows.set(session.id, session);
      return session;
    },
    remove: (id) => {
      rows.delete(id);
    },
  };
}

/** A registry with one provider that launches the fake agent. */
const fakeProvider: AgentProvider = {
  id: "claude-code", // must be a registry id: SessionManager looks launch data up there
  name: "Fake",
  description: "",
  websiteUrl: "",
  docsUrl: "",
  registryId: null,
  icon: null,
  binaryNames: ["fake"],
  versionArgs: [],
  launchWithoutBinary: true,
  install: { macos: [], linux: [], windows: [] },
  authMethods: [{ type: "none", label: "none" }],
  authProbe: { files: [], envVars: [], checkArgs: null },
  launch: { command: process.execPath, args: [FAKE_AGENT], env: {} },
  capabilities: { subagents: true, terminals: true, modes: true, configOptions: true, loadSession: true },
  skillsDir: null,
  pluginInstall: null,
};

const managers: SessionManager[] = [];
afterEach(() => {
  for (const manager of managers.splice(0)) {
    manager.closeAll();
  }
});

async function setup() {
  const repo = memoryRepo();
  const broadcasts: { channel: IpcEventChannel; payload: unknown }[] = [];
  const detector = new AgentDetector([fakeProvider], {
    env: async () => ({ PATH: process.env.PATH ?? "" }),
    isExecutable: async () => false,
    exists: async () => false,
    exec: async () => ({ stdout: "", stderr: "", code: 0 }),
    homeDir: () => os.homedir(),
    platform: process.platform,
  });
  await detector.refresh();
  let counter = 0;
  const manager = new SessionManager({
    repo,
    detector,
    spawnTerminal: spawnProcessTerminal,
    broadcast: (channel, payload) => {
      broadcasts.push({ channel, payload });
    },
    newId: () => `session-${++counter}`,
  });
  managers.push(manager);
  const cwd = await realpath(await mkdtemp(path.join(os.tmpdir(), "hardcore-mgr-")));
  return { repo, broadcasts, manager, cwd };
}

// The manager resolves the launch through the registry, which has the real
// Claude launch line. Point it at the fake agent for the tests.
import { AGENT_PROVIDERS } from "@main/agents/registry";
const claude = AGENT_PROVIDERS.find((provider) => provider.id === "claude-code")!;
const originalLaunch = claude.launch;
(claude as { launch: AgentProvider["launch"] }).launch = fakeProvider.launch;
afterEach(() => {
  (claude as { launch: AgentProvider["launch"] }).launch = fakeProvider.launch;
});
void originalLaunch;

describe("SessionManager", () => {
  it("creates a row, connects, titles the session from the first prompt, and tallies changes", async () => {
    const { repo, broadcasts, manager, cwd } = await setup();
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    expect(session).toMatchObject({ id: "session-1", status: "idle", acpSessionId: "fake-session-1", title: "New session" });
    expect(manager.state(session.id)?.status).toBe("idle");
    expect(broadcasts.some((b) => b.channel === "session.state")).toBe(true);

    const target = path.join(cwd, "made.txt");
    const { stopReason } = await manager.prompt(session.id, [{ type: "text", text: `please write ${target}` }]);
    expect(stopReason).toBe("end_turn");
    const row = repo.get(session.id)!;
    expect(row.title.startsWith("please write ")).toBe(true);
    expect(row.title.length).toBeLessThanOrEqual(60);
    expect(row.title.endsWith("…")).toBe(true);
    expect(row.status).toBe("idle");
    expect(row.changedFiles).toBe(1);
    expect(row.insertions).toBe(1);
    expect(broadcasts.filter((b) => b.channel === "files.changed")).toHaveLength(1);
    expect(broadcasts.filter((b) => b.channel === "session.update").length).toBeGreaterThan(3);
  });

  it("bridges permission requests and answers", async () => {
    const { broadcasts, manager, cwd } = await setup();
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    const turn = manager.prompt(session.id, [{ type: "text", text: "needs permission" }]);
    const request = await until(() => broadcasts.find((b) => b.channel === "session.permission"));
    const { requestId } = (request.payload as { request: { requestId: string } }).request;
    expect(manager.get(session.id)?.status).toBe("waiting");
    manager.respondPermission(session.id, requestId, "allow-once");
    await turn;
    expect(manager.get(session.id)?.status).toBe("idle");
  });

  it("approval mode set before connecting applies to the connection", async () => {
    const { manager, cwd } = await setup();
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    manager.setApprovalMode(session.id, "approve-for-me");
    const { stopReason } = await manager.prompt(session.id, [{ type: "text", text: "needs permission" }]);
    expect(stopReason).toBe("end_turn");
    expect(manager.state(session.id)?.approvalMode).toBe("approve-for-me");
  });

  it("close keeps the row, load reconnects through session/load, delete forgets it", async () => {
    const { repo, manager, cwd } = await setup();
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    manager.close(session.id);
    expect(manager.state(session.id)).toBeNull();
    expect(repo.get(session.id)?.status).toBe("closed");

    const state = await manager.load(session.id);
    expect(state.status).toBe("idle");
    expect(state.turns.map((turn) => turn.role)).toEqual(["user", "agent"]);

    // A prompt after a crash reconnects on its own.
    await expect(manager.prompt(session.id, [{ type: "text", text: "please crash" }])).rejects.toThrow();
    await until(() => (repo.get(session.id)?.status === "error" ? true : undefined));
    const { stopReason } = await manager.prompt(session.id, [{ type: "text", text: "ok again" }]);
    expect(stopReason).toBe("end_turn");
    expect(repo.get(session.id)?.status).toBe("idle");

    manager.delete(session.id);
    expect(repo.get(session.id)).toBeNull();
    expect(manager.state(session.id)).toBeNull();
  });

  it("refuses an unknown agent and lists by project", async () => {
    const { manager, cwd } = await setup();
    await expect(manager.create({ projectId: "p1", agentId: "nope", cwd, gitMode: "none" })).rejects.toThrow(/unknown agent/);
    await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    await manager.create({ projectId: "p2", agentId: "claude-code", cwd, gitMode: "checkout", branch: "main" });
    expect(manager.list("p1")).toHaveLength(1);
    expect(manager.list()).toHaveLength(2);
    expect(manager.list("p2")[0]?.branch).toBe("main");
  });
});

async function until<T>(probe: () => T | undefined, timeoutMs = 5_000): Promise<T> {
  const started = Date.now();
  for (;;) {
    const value = probe();
    if (value !== undefined) {
      return value;
    }
    if (Date.now() - started > timeoutMs) {
      throw new Error("timed out");
    }
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}
