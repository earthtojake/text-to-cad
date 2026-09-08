import { mkdir, mkdtemp, readFile, realpath, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

import { AgentDetector } from "@main/agents/detect";
import { spawnProcessTerminal } from "@main/acp/process-backend";
import {
  SessionManager,
  diffCounts,
  titleFromPrompt,
  type SessionManagerDeps,
  type SessionRepository,
} from "@main/acp/sessions";
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
  skillRoots: "preamble",
};

const managers: SessionManager[] = [];
afterEach(() => {
  for (const manager of managers.splice(0)) {
    manager.closeAll();
  }
});

async function setup(extra: Partial<SessionManagerDeps> = {}) {
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
    ...extra,
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

  /* ------------------------------------------------------------------ */
  /* P7: the git mode decides the directory (plan §9)                    */
  /* ------------------------------------------------------------------ */

  it("resolves the working directory from the git mode, and records both review marks", async () => {
    const { repo, manager, cwd } = await setup({
      workspace: async ({ gitMode, name }) => {
        if (gitMode !== "worktree") {
          return { cwd, ...(gitMode === "checkout" ? { branch: "main" } : {}) };
        }
        // A real resolver makes the directory; the adapter is spawned in it.
        await mkdir(`${cwd}/wt`, { recursive: true });
        return {
          cwd: `${cwd}/wt`,
          branch: `hardcore/${name ?? "generated"}`,
          worktreePath: `${cwd}/wt`,
        };
      },
      head: async (directory: string) =>
        directory.endsWith("/wt") ? "worktree-head" : "checkout-head",
    });

    const plain = await manager.create({ projectId: "p1", agentId: "claude-code", gitMode: "none" });
    expect(plain.cwd).toBe(cwd);
    expect(plain.branch).toBeUndefined();
    expect(plain.worktreePath).toBeUndefined();
    // Both scopes start at the same revision, so a review taken before the
    // first prompt shows what the person changed by hand rather than nothing.
    expect(plain).toMatchObject({
      sessionHead: "checkout-head",
      turnHead: "checkout-head",
      turnStartedAt: null,
    });

    const checkout = await manager.create({
      projectId: "p1",
      agentId: "claude-code",
      gitMode: "checkout",
    });
    expect(checkout).toMatchObject({ cwd, branch: "main" });
    expect(checkout.worktreePath).toBeUndefined();

    const worktree = await manager.create({
      projectId: "p1",
      agentId: "claude-code",
      gitMode: "worktree",
      name: "Model the wrist",
    });
    expect(worktree).toMatchObject({
      cwd: `${cwd}/wt`,
      branch: "hardcore/Model the wrist",
      worktreePath: `${cwd}/wt`,
      sessionHead: "worktree-head",
    });
    expect(repo.get(worktree.id)?.cwd).toBe(`${cwd}/wt`);
  });

  it("marks where the working tree was when each turn began", async () => {
    let head = "before-the-turn";
    const { repo, manager, cwd } = await setup({ head: async () => head });
    const session = await manager.create({
      projectId: "p1",
      agentId: "claude-code",
      cwd,
      gitMode: "none",
    });
    expect(repo.get(session.id)?.turnHead).toBe("before-the-turn");

    head = "the-turn-starts-here";
    await manager.prompt(session.id, [{ type: "text", text: "hello" }]);

    const row = repo.get(session.id)!;
    // The turn's mark moved; the session's did not.
    expect(row.turnHead).toBe("the-turn-starts-here");
    expect(row.sessionHead).toBe("before-the-turn");
    expect(row.turnStartedAt).toBeGreaterThan(0);
  });

  it("refuses a mode its workspace cannot satisfy, and writes no row for it", async () => {
    const { repo, manager } = await setup({
      workspace: async () => {
        throw new Error("Project is not a git repository, worktree mode unavailable");
      },
    });
    await expect(
      manager.create({ projectId: "p1", agentId: "claude-code", gitMode: "worktree" }),
    ).rejects.toThrow("Project is not a git repository, worktree mode unavailable");
    // No half-made thread pointing at a directory that does not exist.
    expect(manager.list()).toHaveLength(0);
    expect(repo.rows.size).toBe(0);
  });

  it("hands the session to releaseWorkspace on delete", async () => {
    const released: (string | undefined)[] = [];
    const { manager, cwd } = await setup({
      workspace: async () => ({ cwd, worktreePath: `${cwd}/wt` }),
      releaseWorkspace: async (session) => {
        released.push(session.worktreePath);
      },
    });
    const session = await manager.create({
      projectId: "p1",
      agentId: "claude-code",
      gitMode: "worktree",
    });
    await manager.delete(session.id);
    expect(released).toEqual([`${cwd}/wt`]);
  });

  /* ------------------------------------------------------------------ */
  /* P2: the model, the effort and the mode                              */
  /* ------------------------------------------------------------------ */

  /**
   * A stand-in for the option store, recording what the manager asked it.
   *
   * `efforts` is a map from model value to level, the way the store keeps it
   * (migration 9): the manager asks for the effort of the model the session
   * ended up on, so a recorder with one level for the whole agent could not
   * show that it asked about the right one. `asked` is every model it asked
   * about, in order.
   */
  function optionRecorder(defaults: {
    model: string | null;
    efforts?: Record<string, string>;
    mode?: string | null;
  }) {
    const remembered: { agentId: string; ids: string[]; modes: string[] }[] = [];
    const choices: { agentId: string; configId: string; value: string | boolean }[] = [];
    const modes: { agentId: string; modeId: string }[] = [];
    const asked: (string | null)[] = [];
    return {
      remembered,
      choices,
      modes,
      asked,
      deps: {
        defaults: () => ({ model: defaults.model, mode: defaults.mode ?? null }),
        effortFor: (_agentId: string, model: string | null) => {
          asked.push(model);
          return defaults.efforts?.[model ?? ""] ?? null;
        },
        remember: (agentId: string, options: { id: string }[], sessionModes: { id: string }[]) => {
          remembered.push({
            agentId,
            ids: options.map((option) => option.id),
            modes: sessionModes.map((mode) => mode.id),
          });
        },
        rememberChoice: (agentId: string, configId: string, value: string | boolean) => {
          choices.push({ agentId, configId, value });
        },
        rememberMode: (agentId: string, modeId: string) => {
          modes.push({ agentId, modeId });
        },
      },
    };
  }

  /** What the fake agent says it was configured with, in order (tests/fake-agent). */
  async function appliedIn(manager: SessionManager, sessionId: string): Promise<string> {
    await manager.prompt(sessionId, [{ type: "text", text: "applied" }]);
    const parts = manager.state(sessionId)!.turns.at(-1)!.parts;
    const text = parts.find((part) => part.type === "text");
    return text?.type === "text" ? text.text : "";
  }

  it("applies the stored model before the effort, then the agent's own auto mode", async () => {
    const recorder = optionRecorder({ model: "smart", efforts: { smart: "high" } });
    const { manager, cwd } = await setup({ agentOptions: recorder.deps });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });

    // The order is the assertion: the model decides which effort levels the
    // agent has *and* which effort was remembered, so an effort read or set
    // first would be the outgoing model's. The mode is last, and is the
    // fake's `auto_review` preset — not the `default` it starts in.
    expect(await appliedIn(manager, session.id)).toBe("applied: model,reasoning_effort,mode:auto in auto");
    // Asked about `smart`, after it landed — not about `fast`, where the
    // session started.
    expect(recorder.asked).toEqual(["smart"]);
    const state = manager.state(session.id)!;
    expect(state.configOptions.find((option) => option.id === "model")?.currentValue).toBe("smart");
    expect(state.currentModeId).toBe("auto");
    // And the session's own snapshot went to the cache — the modes with the
    // options, because the new-session screen's mode chip is drawn from them.
    expect(recorder.remembered.at(-1)?.ids).toContain("model");
    expect(recorder.remembered.at(-1)?.modes).toEqual(["default", "plan", "auto", "full"]);
  });

  /**
   * The mode the person left this agent in wins over the auto preset: the
   * new-session screen's chip is a default like the model and the effort,
   * and `create` is where it is applied.
   */
  it("creates the session in the stored mode rather than the auto one", async () => {
    const recorder = optionRecorder({ model: null, mode: "plan" });
    const { manager, cwd } = await setup({ agentOptions: recorder.deps });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    expect(await appliedIn(manager, session.id)).toBe("applied: mode:plan in plan");
  });

  /**
   * The fake starts in `default`, which is what "Manual" is: a stored
   * default of it means the session is created with no `set_mode` at all,
   * rather than being moved to the auto preset.
   */
  it("leaves the agent where it starts when that is the stored mode", async () => {
    const recorder = optionRecorder({ model: null, mode: "default" });
    const { manager, cwd } = await setup({ agentOptions: recorder.deps });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    expect(await appliedIn(manager, session.id)).toBe("applied:  in default");
  });

  /** A mode the agent dropped is not a mode; the auto preset is the fallback. */
  it("ignores a stored mode the agent no longer offers", async () => {
    const recorder = optionRecorder({ model: null, mode: "yolo" });
    const { manager, cwd } = await setup({ agentOptions: recorder.deps });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    expect(await appliedIn(manager, session.id)).toBe("applied: mode:auto in auto");
  });

  it("sets nothing it does not have to: no defaults, and a mode already auto", async () => {
    const recorder = optionRecorder({ model: null });
    const { manager, cwd } = await setup({ agentOptions: recorder.deps });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    expect(await appliedIn(manager, session.id)).toBe("applied: mode:auto in auto");
  });

  it("ignores a stored model the agent no longer offers", async () => {
    const recorder = optionRecorder({ model: "gpt-9" });
    const { manager, cwd } = await setup({ agentOptions: recorder.deps });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    expect(await appliedIn(manager, session.id)).toBe("applied: mode:auto in auto");
  });

  it("creates the session anyway when the agent refuses the model", async () => {
    // The fake refuses `model` outright, the way an adapter refuses a model
    // an account cannot use.
    const refusing = { ...fakeProvider.launch, env: { FAKE_AGENT_REFUSE: "model" } };
    (claude as { launch: AgentProvider["launch"] }).launch = refusing;
    const recorder = optionRecorder({ model: "smart", efforts: { smart: "high", fast: "low" } });
    const { manager, cwd } = await setup({ agentOptions: recorder.deps });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    expect(session.status).toBe("idle");
    // The effort and the mode still landed; only the model did not — and the
    // effort is `fast`'s, because that is the model the session is on. A
    // refused model must not drag the wanted model's level in behind it.
    expect(await appliedIn(manager, session.id)).toBe("applied: reasoning_effort,mode:auto in auto");
    expect(recorder.asked).toEqual(["fast"]);
    expect(manager.state(session.id)!.configOptions.find((option) => option.id === "reasoning_effort")?.currentValue).toBe(
      "low",
    );
  });

  it("remembers the model, effort and mode a live session was switched to", async () => {
    const recorder = optionRecorder({ model: null });
    const { manager, cwd } = await setup({ agentOptions: recorder.deps });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    await manager.setConfigOption(session.id, "model", "smart");
    await manager.setConfigOption(session.id, "reasoning_effort", "low");
    expect(recorder.choices).toEqual([
      { agentId: "claude-code", configId: "model", value: "smart" },
      { agentId: "claude-code", configId: "reasoning_effort", value: "low" },
    ]);
    // Switching the mode mid-thread is the same decision as making it on the
    // new-session screen, so it becomes this agent's default too.
    await manager.setMode(session.id, "plan");
    expect(recorder.modes).toEqual([{ agentId: "claude-code", modeId: "plan" }]);
  });

  it("probes an agent for its config options without leaving a session behind", async () => {
    // The detector in this file finds nothing on PATH, so the probe needs the
    // launch override — which is also the rule: a probe never `npx`-fetches an
    // adapter for an agent whose CLI is not on the machine.
    const { manager, repo, cwd } = await setup({ launchOverride: () => fakeProvider.launch });
    const snapshot = await manager.probeOptions({ agentId: "claude-code", cwd, projectId: "p1" });
    expect(snapshot.configOptions.map((option) => option.id)).toEqual(["model", "reasoning_effort"]);
    // The modes come back too: they are the other half of what a session
    // with no `mode` config option would draw its one mode chip from.
    expect(snapshot.modes.map((mode) => mode.id)).toEqual(["default", "plan", "auto", "full"]);
    expect(repo.list()).toHaveLength(0);
    expect(manager.list()).toHaveLength(0);
  });

  it("refuses to probe an agent whose CLI is not on the machine", async () => {
    const { manager, cwd } = await setup();
    await expect(manager.probeOptions({ agentId: "claude-code", cwd, projectId: "p1" })).rejects.toThrow(
      /not installed/,
    );
  });

  it("says what happened when a session's directory has gone", async () => {
    const { manager, cwd, broadcasts } = await setup();
    const session = await manager.create({
      projectId: "p1",
      agentId: "claude-code",
      cwd,
      gitMode: "none",
    });
    manager.close(session.id);
    await rm(cwd, { recursive: true, force: true });

    await expect(manager.load(session.id)).rejects.toThrow(/directory no longer exists/);
    expect(
      broadcasts.some(
        (entry) =>
          entry.channel === "session.status" &&
          (entry.payload as { error: string | null }).error?.includes("no longer exists"),
      ),
    ).toBe(true);
  });
});

/**
 * What the app gives a session: the skills root in `session/new`, the preamble
 * only to an agent that will not read one, and the runtime's `cadgen` in front
 * of the adapter's PATH. Read back out of the fake agent's record file
 * (`FAKE_AGENT_RECORD`), which is the wire as the agent received it.
 */
describe("what a session is given", () => {
  async function recorded(agentId: string, deps: Partial<SessionManagerDeps> = {}) {
    const file = path.join(await mkdtemp(path.join(os.tmpdir(), "hardcore-record-")), "frames.jsonl");
    const { manager, cwd } = await setup({
      launchOverride: () => ({ ...fakeProvider.launch, env: { FAKE_AGENT_RECORD: file } }),
      skills: { root: () => "/data/skills/1.2.3", preamble: () => "SKILLS: /data/skills/1.2.3" },
      runtimePath: () => ["/app/bin", "/app/runtime/python/bin"],
      ...deps,
    });
    const session = await manager.create({ projectId: "p1", agentId, cwd, gitMode: "none" });
    await manager.prompt(session.id, [{ type: "text", text: "first" }]);
    await manager.prompt(session.id, [{ type: "text", text: "second" }]);
    const lines = (await readFile(file, "utf8")).trim().split("\n").map((line) => JSON.parse(line) as { kind: string; params: Record<string, unknown> });
    return { manager, session, lines };
  }

  it("names the skills root in session/new and puts the runtime in front of PATH", async () => {
    const { lines } = await recorded("claude-code");
    const params = lines.find((line) => line.kind === "session/new")!.params;
    expect(params.additionalDirectories).toEqual(["/data/skills/1.2.3"]);
    expect(params._meta).toMatchObject({ additionalRoots: ["/data/skills/1.2.3"] });
    // The adapter's own environment: what every command in the session inherits.
    expect(String(params.PATH).split(path.delimiter).slice(0, 2)).toEqual(["/app/bin", "/app/runtime/python/bin"]);
  });

  it("leaves PATH alone when there is no runtime", async () => {
    const { lines } = await recorded("claude-code", { runtimePath: () => [] });
    const params = lines.find((line) => line.kind === "session/new")!.params;
    expect(String(params.PATH)).toBe(process.env.PATH ?? "");
  });

  it("sends no preamble to an agent that loads the root itself", async () => {
    // claude-code is `skillRoots: "native"` in the registry.
    const { lines } = await recorded("claude-code");
    const prompts = lines.filter((line) => line.kind === "prompt");
    expect(prompts).toHaveLength(2);
    expect(JSON.stringify(prompts[0]!.params.prompt)).not.toContain("SKILLS:");
  });

  it("sends it once to an agent that does not, and not on the turn after", async () => {
    // gemini-cli is `skillRoots: "preamble"`.
    const { lines } = await recorded("gemini-cli");
    const prompts = lines.filter((line) => line.kind === "prompt");
    expect(prompts[0]!.params.prompt).toEqual([
      { type: "text", text: "SKILLS: /data/skills/1.2.3" },
      { type: "text", text: "first" },
    ]);
    expect(prompts[1]!.params.prompt).toEqual([{ type: "text", text: "second" }]);
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
