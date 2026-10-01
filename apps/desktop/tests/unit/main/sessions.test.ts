import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentDetector } from "@main/agents/detect";
import { spawnProcessTerminal } from "@main/acp/process-backend";
import {
  SessionManager,
  diffCounts,
  titleFromPrompt,
  type SessionManagerDeps,
  type SessionRepository,
} from "@main/acp/sessions";
import type { SnapshotStore } from "@main/acp/snapshots";
import type { SessionEvent } from "@shared/acp/types";
import type { AgentProvider } from "@shared/agents";
import type { IpcEventChannel } from "@shared/ipc";
import { DELETED_WHILE_STARTING } from "@shared/ipc/errors";
import type { Session } from "@shared/types";

import { cleanTempDirs, tempDir } from "./temp-dirs";

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

/** The snapshot store, in a Map (sqlite's `session_state` in the app). */
function memorySnapshots(): SnapshotStore & { rows: Map<string, string> } {
  const rows = new Map<string, string>();
  return {
    rows,
    read: (id) => {
      const json = rows.get(id);
      return json === undefined ? null : JSON.parse(json);
    },
    write: (id, json) => {
      rows.set(id, json);
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
  adapter: null,
  capabilities: { subagents: true, terminals: true, modes: true, configOptions: true, loadSession: true },
  skillRoots: "preamble",
};

const managers: SessionManager[] = [];
afterEach(() => {
  // A test that faked timers and hung must not leave them faked for the next.
  vi.useRealTimers();
  for (const manager of managers.splice(0)) {
    manager.closeAll();
  }
  cleanTempDirs();
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
    newId: () => `s${++counter}-xxxxxxxx`,
    ...extra,
  });
  managers.push(manager);
  const cwd = await tempDir("text-to-cad-mgr-");
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
    expect(session).toMatchObject({ id: "s1-xxxxxxxx", status: "idle", acpSessionId: "fake-session-1", title: "New session" });
    expect(manager.state(session.id)?.state.status).toBe("idle");
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

  it("writes the counts of an edit that arrives after the turn has settled", async () => {
    const { repo, manager, cwd } = await setup();
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    await manager.prompt(session.id, [{ type: "text", text: "nothing to edit" }]);
    expect(repo.get(session.id)?.insertions).toBe(0);
    // A background task finishing: a tool call with a diff, long after `prompt` resolved.
    const late = { sessionUpdate: "tool_call", toolCallId: "late-1", status: "completed", kind: "edit", title: "Edit late.md", content: [{ type: "diff", path: "late.md", oldText: "", newText: "a\nb\n" }] };
    (manager as unknown as { onEvent(id: string, event: unknown): void }).onEvent(session.id, { type: "session/update", acpSessionId: "fake-session-1", update: late });
    expect(repo.get(session.id)).toMatchObject({ changedFiles: 1, insertions: 2, deletions: 0 });
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

  it("returns the row to idle when a permission asked after the turn closed is answered", async () => {
    const { manager, cwd } = await setup();
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    const connection = (manager as unknown as { live: Map<string, { dispatch: (event: SessionEvent) => void }> }).live.get(session.id)!;
    const request = { requestId: "late-1", acpSessionId: "fake-session-1", toolCallId: "c1", title: null, description: null, kind: null, input: null, options: [] };
    connection.dispatch({ type: "permission/request", request, at: Date.now() });
    expect(manager.get(session.id)?.status).toBe("waiting");
    connection.dispatch({ type: "permission/resolve", requestId: "late-1", outcome: { state: "cancelled" }, at: Date.now() });
    expect(manager.get(session.id)?.status).toBe("idle");
  });

  it("persists and broadcasts agent titles, including notifications before session/new answers", async () => {
    const { repo, broadcasts, manager, cwd } = await setup({
      launchOverride: () => ({ ...fakeProvider.launch, args: [FAKE_AGENT, "--new-title", "Initial agent title"] }),
    });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    expect(session).toMatchObject({ title: "Initial agent title", titleSource: "agent" });

    broadcasts.length = 0;
    await manager.prompt(session.id, [{ type: "text", text: 'session-title {"title":"  Design a gripper  "}' }]);
    expect(repo.get(session.id)).toMatchObject({ title: "Design a gripper", titleSource: "agent" });
    expect(broadcasts).toContainEqual({
      channel: "sessions.changed",
      payload: expect.arrayContaining([expect.objectContaining({ id: session.id, title: "Design a gripper" })]),
    });

    for (const info of [{ title: null }, { title: "   " }, { title: "Child agent title", sessionId: "child-session" }]) {
      await manager.prompt(session.id, [{ type: "text", text: `session-title ${JSON.stringify(info)}` }]);
      expect(repo.get(session.id)?.title).toBe("Design a gripper");
    }
  });

  it("uses the agent title from replay even when a prompt initiated the reconnect", async () => {
    const { manager, repo, cwd } = await setup({
      launchOverride: () => ({ ...fakeProvider.launch, args: [FAKE_AGENT, "--load-title", "Resumed agent title"] }),
    });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    manager.close(session.id);
    await manager.prompt(session.id, [{ type: "text", text: "Continue this work" }]);
    expect(repo.get(session.id)).toMatchObject({ title: "Resumed agent title", titleSource: "agent" });
  });

  it("keeps the agent's title in the state across a session/load, and settles the replayed turn", async () => {
    // The replay carries no `session_info_update`: without the row's title
    // the reloaded state's `title` was null, and its agent turn had no stop
    // reason where the live one had `end_turn`.
    const { manager, cwd } = await setup({
      launchOverride: () => ({ ...fakeProvider.launch, args: [FAKE_AGENT, "--new-title", "Initial agent title"] }),
    });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    await manager.prompt(session.id, [{ type: "text", text: "hello there" }]);
    expect(manager.state(session.id)?.state.title).toBe("Initial agent title");
    manager.close(session.id);

    const state = await manager.load(session.id);
    expect(state.title).toBe("Initial agent title");
    expect(state.turns.map((turn) => `${turn.role}:${turn.stopReason}`)).toEqual(["user:null", "agent:end_turn"]);
  });

  it("preserves a user's explicit title through later agent updates and a manager restart", async () => {
    const first = await setup({
      launchOverride: () => ({ ...fakeProvider.launch, args: [FAKE_AGENT, "--load-title", "Agent replay title"] }),
    });
    const session = await first.manager.create({ projectId: "p1", agentId: "claude-code", cwd: first.cwd, gitMode: "none" });
    first.manager.rename(session.id, " My chosen title ");
    await first.manager.prompt(session.id, [{ type: "text", text: 'session-title {"title":"Agent replacement"}' }]);
    expect(first.repo.get(session.id)).toMatchObject({ title: "My chosen title", titleSource: "user" });
    first.manager.closeAll();

    const second = await setup({
      repo: first.repo,
      launchOverride: () => ({ ...fakeProvider.launch, args: [FAKE_AGENT, "--load-title", "Agent replay title"] }),
    });
    await second.manager.load(session.id);
    expect(second.manager.get(session.id)).toMatchObject({ title: "My chosen title", titleSource: "user" });
  });

  it("counts a reloaded session's replayed edits once, however many times it is loaded", async () => {
    // Recordings in the fake agent's fixture shape. The first adapter has one
    // turn that edits a file; every later one (a reload) replays that edit as
    // history during session/load — which is what a real adapter does — and
    // has an empty turn. (The checked-in fixtures replay no diffs.)
    const diff = { type: "diff", path: "notes.md", oldText: "a\n", newText: "a\nb\nc\n" };
    const edit = (sessionUpdate: string) => ({
      dir: "in",
      msg: { jsonrpc: "2.0", method: "session/update", params: { sessionId: "recorded", update: { sessionUpdate, toolCallId: "edit-1", status: "completed", kind: "edit", title: "Edit notes.md", content: [diff] } } },
    });
    const request = (id: number, method: string) => ({ dir: "out", msg: { jsonrpc: "2.0", id, method, params: { sessionId: "recorded" } } });
    const response = (id: number, result: object) => ({ dir: "in", msg: { jsonrpc: "2.0", id, result } });
    const dir = await tempDir("text-to-cad-tally-");
    const write = async (name: string, frames: object[]) => {
      const file = path.join(dir, name);
      await writeFile(file, frames.map((frame) => JSON.stringify(frame)).join("\n"));
      return file;
    };
    const first = await write("first.jsonl", [request(1, "session/prompt"), edit("tool_call_update"), response(1, { stopReason: "end_turn" })]);
    const reload = await write("reload.jsonl", [request(1, "session/load"), edit("tool_call"), response(1, {})]);
    let fixture = first;
    const { repo, manager, cwd } = await setup({
      launchOverride: () => ({ ...fakeProvider.launch, args: [FAKE_AGENT, "--fixture", fixture] }),
    });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    await manager.prompt(session.id, [{ type: "text", text: "edit the notes" }]);
    const tally = (row: Session | null) => ({ changedFiles: row?.changedFiles, insertions: row?.insertions, deletions: row?.deletions });
    expect(tally(repo.get(session.id))).toEqual({ changedFiles: 1, insertions: 2, deletions: 0 });
    fixture = reload;

    for (let round = 0; round < 2; round += 1) {
      manager.close(session.id);
      await manager.load(session.id);
      // An empty turn: this prompt only persists the tally.
      await manager.prompt(session.id, [{ type: "text", text: "anything else?" }]);
      expect(tally(repo.get(session.id))).toEqual({ changedFiles: 1, insertions: 2, deletions: 0 });
    }

    // An adapter that replays no diffs during session/load: the persisted
    // counts are the history, and the next edit adds to them rather than
    // replacing them with just its own turn.
    const other = { type: "diff", path: "other.md", oldText: "", newText: "x\ny\n" };
    fixture = await write("reload-quiet.jsonl", [
      request(1, "session/load"),
      response(1, {}),
      request(2, "session/prompt"),
      { dir: "in", msg: { jsonrpc: "2.0", method: "session/update", params: { sessionId: "recorded", update: { sessionUpdate: "tool_call", toolCallId: "edit-2", status: "completed", kind: "edit", title: "Edit other.md", content: [other] } } } },
      response(2, { stopReason: "end_turn" }),
    ]);
    manager.close(session.id);
    await manager.load(session.id);
    await manager.prompt(session.id, [{ type: "text", text: "edit the other file" }]);
    expect(tally(repo.get(session.id))).toEqual({ changedFiles: 2, insertions: 4, deletions: 0 });
  });

  it("marks a repository with no commits at the empty tree, so a first commit mid-session is in This session and Last turn", async () => {
    const { head, emptyTreeIfUnborn, status } = await import("@main/projects/git");
    const { resolveDiffScope } = await import("@shared/types");
    const { execFileSync } = await import("node:child_process");
    const { repo, manager, cwd } = await setup({ head, emptyTree: emptyTreeIfUnborn });
    const run = (...args: string[]) =>
      execFileSync("git", ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", ...args], { cwd, encoding: "utf8" }).trim();
    run("init", "-q");
    const emptyTree = execFileSync("git", ["hash-object", "-t", "tree", "--stdin"], { cwd, input: "", encoding: "utf8" }).trim();

    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    expect(repo.get(session.id)).toMatchObject({ sessionHead: emptyTree, turnHead: emptyTree });

    // The first commit lands between the session's start and its next turn.
    await writeFile(path.join(cwd, "first.txt"), "one\n");
    run("add", "first.txt");
    run("commit", "-q", "-m", "first");
    const firstCommit = run("rev-parse", "HEAD");
    await manager.prompt(session.id, [{ type: "text", text: "hello" }]);

    const row = repo.get(session.id);
    expect(row?.sessionHead).toBe(emptyTree);
    expect(row?.turnHead).toBe(firstCommit);
    const since = resolveDiffScope({ kind: "session" }, row);
    expect(since).toEqual({ kind: "range", from: emptyTree });
    const listed = await status(cwd, since);
    expect(listed.files.map((file) => file.path)).toContain("first.txt");
  });

  it("records no mark when head() fails in a repository that has commits, never the empty tree", async () => {
    // head() answers null on any failure — a timeout, a spawn error, a ref
    // mid-update. In a repository with commits that is not "unborn", and the
    // empty tree would make Last turn show the whole repository.
    const { emptyTreeIfUnborn } = await import("@main/projects/git");
    const { execFileSync } = await import("node:child_process");
    const { repo, manager, cwd } = await setup({ head: async () => null, emptyTree: emptyTreeIfUnborn });
    const run = (...args: string[]) =>
      execFileSync("git", ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", ...args], { cwd, encoding: "utf8" }).trim();
    run("init", "-q");
    await writeFile(path.join(cwd, "first.txt"), "one\n");
    run("add", "first.txt");
    run("commit", "-q", "-m", "first");

    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    expect(repo.get(session.id)).toMatchObject({ sessionHead: null, turnHead: null });
  });

  it("asks for the empty tree only when head() had nothing", async () => {
    const asked: string[] = [];
    const { repo, manager, cwd } = await setup({
      head: async () => "a".repeat(40),
      emptyTree: async (directory) => {
        asked.push(directory);
        return null;
      },
    });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    expect(repo.get(session.id)).toMatchObject({ sessionHead: "a".repeat(40) });
    expect(asked).toEqual([]);
  });

  it("records no mark outside a repository", async () => {
    const { head, emptyTreeIfUnborn } = await import("@main/projects/git");
    const { repo, manager, cwd } = await setup({ head, emptyTree: emptyTreeIfUnborn });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    expect(repo.get(session.id)).toMatchObject({ sessionHead: null, turnHead: null });
  });

  it("at boot, closes rows a crash left running, waiting or connecting, without reordering them", async () => {
    const repo = memoryRepo();
    const row = (id: string, status: Session["status"]): Session => ({
      id,
      projectId: "p1",
      agentId: "claude-code",
      cwd: "/tmp",
      gitMode: "none",
      title: id,
      titleSource: "prompt",
      createdAt: 1,
      updatedAt: 100,
      status,
      acpSessionId: `acp-${id}`,
      changedFiles: 0,
      insertions: 0,
      deletions: 0,
      archived: false,
      pinned: false,
    } as Session);
    for (const [id, status] of [
      ["running", "running"],
      ["waiting", "waiting"],
      ["connecting", "connecting"],
      ["idle", "idle"],
      ["error", "error"],
      ["closed", "closed"],
    ] as const) {
      repo.upsert(row(id, status));
    }
    const { manager } = await setup({ repo });
    const statuses = Object.fromEntries(manager.list().map((session) => [session.id, session.status]));
    expect(statuses).toEqual({
      running: "closed",
      waiting: "closed",
      connecting: "closed",
      idle: "idle",
      error: "error",
      closed: "closed",
    });
    expect(manager.list().every((session) => session.updatedAt === 100)).toBe(true);
  });

  it("drops the row of a create that never reached session/new's answer when the app next starts", async () => {
    // `closeAll` in the middle of a create closes the database under it, and
    // the create's own cleanup then throws: the row is what is left.
    const repo = memoryRepo();
    const base = { projectId: "p1", agentId: "claude-code", cwd: "/x", gitMode: "none", title: "New session", titleSource: "prompt", createdAt: 1, updatedAt: 100, changedFiles: 0, insertions: 0, deletions: 0, archived: false, pinned: false } as const;
    repo.upsert({ ...base, id: "phantom", status: "connecting", acpSessionId: null } as Session);
    repo.upsert({ ...base, id: "real", status: "closed", acpSessionId: "acp-real" } as Session);
    const { manager } = await setup({ repo });
    expect(manager.list().map((session) => session.id)).toEqual(["real"]);
  });

  it("releases the worktree of a dead create at boot only when that create cut it", async () => {
    const repo = memoryRepo();
    const base = { projectId: "p1", agentId: "claude-code", cwd: "/x", gitMode: "worktree", title: "New session", titleSource: "prompt", createdAt: 1, updatedAt: 100, changedFiles: 0, insertions: 0, deletions: 0, archived: false, pinned: false, status: "connecting", acpSessionId: null } as const;
    repo.upsert({ ...base, id: "cut", worktreePath: "/wt/cut", worktreeOwned: true } as Session);
    repo.upsert({ ...base, id: "given", worktreePath: "/wt/given" } as Session);
    const released: { path: string | undefined; abandoned: boolean | undefined }[] = [];
    const { manager } = await setup({
      repo,
      releaseWorkspace: async (session, options) => {
        released.push({ path: session.worktreePath, abandoned: options?.abandoned });
      },
    });
    expect(manager.list()).toEqual([]);
    expect(released).toEqual([{ path: "/wt/cut", abandoned: true }]);
  });

  it("records that a create cut its worktree, and that one it was handed is not its own", async () => {
    const { manager, cwd } = await setup({
      workspace: async (input) => (input.cwd ? { cwd: input.cwd, worktreePath: input.cwd } : { cwd, worktreePath: `${cwd}/wt` }),
    });
    const cut = await manager.create({ projectId: "p1", agentId: "claude-code", gitMode: "worktree" });
    const given = await manager.create({ projectId: "p1", agentId: "claude-code", gitMode: "worktree", cwd });
    expect(cut.worktreeOwned).toBe(true);
    expect(given.worktreeOwned).toBeUndefined();
  });

  it("refuses an answer to a permission request the agent is no longer waiting on", async () => {
    const { manager, cwd } = await setup();
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    expect(() => manager.respondPermission(session.id, "no-such-request", "allow-once")).toThrow(/expired/);
    manager.close(session.id);
    expect(() => manager.respondPermission(session.id, "no-such-request", "allow-once")).toThrow();
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

  it("leaves updatedAt alone across closed, connecting and idle, and stamps it on a turn", async () => {
    const { repo, manager, cwd } = await setup();
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    repo.upsert({ ...repo.get(session.id)!, updatedAt: 100 });
    manager.close(session.id);
    expect(repo.get(session.id)?.status).toBe("closed");
    await manager.load(session.id);
    expect(repo.get(session.id)?.status).toBe("idle");
    expect(repo.get(session.id)?.updatedAt).toBe(100);
    await manager.prompt(session.id, [{ type: "text", text: "ok again" }]);
    expect(repo.get(session.id)!.updatedAt).toBeGreaterThan(100);
  });

  /**
   * `connect` waits on the shell environment before the connection is in the live set, so a
   * Disconnect that lands then has nothing to retire: the load is what has to notice it.
   */
  describe("a Disconnect that lands while a load is still connecting", () => {
    async function held() {
      const { repo, broadcasts, manager, cwd } = await setup();
      const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
      manager.close(session.id);
      broadcasts.length = 0;
      const detector = (manager as unknown as { deps: { detector: { environment: () => Promise<Record<string, string>> } } }).deps.detector;
      let release!: { resolve: () => void; reject: (error: Error) => void };
      const gate = new Promise<void>((resolve, reject) => (release = { resolve, reject }));
      detector.environment = async () => {
        await gate;
        return { PATH: process.env.PATH ?? "" };
      };
      const loading = manager.load(session.id);
      const settled = loading.then(() => "loaded", () => "refused");
      manager.close(session.id);
      return { repo, broadcasts, manager, session, release, settled };
    }

    it("does not leave the row error when the connect fails", async () => {
      const { repo, session, release, settled } = await held();
      release.reject(new Error("the login shell went away"));
      expect(await settled).toBe("refused");
      expect(repo.get(session.id)?.status).toBe("closed");
    });

    it("does not make the row idle, or broadcast a state, when the connect goes on to succeed", async () => {
      const { repo, broadcasts, session, release, settled } = await held();
      release.resolve();
      expect(await settled).toBe("refused");
      expect(repo.get(session.id)?.status).toBe("closed");
      expect(broadcasts.filter((sent) => sent.channel === "session.state")).toEqual([]);
    });

    it("lets a Reconnect start a load of its own rather than join the abandoned one", async () => {
      const { session, release, settled, manager } = await held();
      const reconnecting = manager.load(session.id);
      release.resolve();
      expect(await settled).toBe("refused");
      expect((await reconnecting).status).toBe("idle");
    });

    it("does not make the row connecting when the close lands during the wait for the probe", async () => {
      const { repo, manager, cwd } = await setup();
      const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
      manager.close(session.id);
      // An agent that needs its binary, whose last-launch row says "not installed" while this
      // launch's probe has not landed.
      const gemini = AGENT_PROVIDERS.find((provider) => provider.id === "gemini-cli")!;
      repo.upsert({ ...repo.get(session.id)!, agentId: "gemini-cli" });
      const detector = (manager as unknown as { deps: { detector: AgentDetector } }).deps.detector;
      const fresh = [{ ...gemini, installed: true, binaryPath: "/usr/local/bin/gemini", version: "1.0.0", auth: "unknown" as const, checkedAt: 2 }];
      const stale = [{ ...fresh[0]!, installed: false, binaryPath: null, version: null, checkedAt: 1 }];
      let probeLands!: () => void;
      const probe = new Promise<void>((resolve) => (probeLands = resolve));
      detector.list = () => stale;
      // Nothing past the wait may spawn the agent: what is under test is what `connect` writes.
      (manager as unknown as { adapterOptions: () => Promise<never> }).adapterOptions = async () => {
        throw new Error("no adapter in this test");
      };
      detector.freshWithin = async () => {
        await probe;
        return fresh;
      };
      const loading = manager.load(session.id).then(() => "loaded", () => "refused");
      manager.close(session.id);
      probeLands();
      expect(await loading).toBe("refused");
      expect(repo.get(session.id)?.status).toBe("closed");
    });

    it("keeps the connection of the load that replaced an overtaken one", async () => {
      const { repo, manager, cwd } = await setup();
      const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
      manager.close(session.id);
      const detector = (manager as unknown as { deps: { detector: { environment: () => Promise<Record<string, string>> } } }).deps.detector;
      let release!: () => void;
      const gate = new Promise<void>((resolve) => (release = resolve));
      let calls = 0;
      detector.environment = async () => {
        if (++calls === 1) await gate;
        return { PATH: process.env.PATH ?? "" };
      };
      const first = manager.load(session.id).then(() => "loaded", () => "refused");
      await until(() => (calls === 1 ? true : undefined));
      manager.close(session.id);
      // The abandoned load is not there to be joined: a `load` is `async`, so the promises it hands out
      // are never identical and the map is where joining shows.
      expect((manager as unknown as { loads: Map<string, unknown> }).loads.has(session.id)).toBe(false);
      await manager.load(session.id);
      const second = (manager as unknown as { live: { get: (id: string) => unknown } }).live.get(session.id);
      expect(second).toBeDefined();
      release();
      expect(await first).toBe("refused");
      expect((manager as unknown as { live: { get: (id: string) => unknown } }).live.get(session.id)).toBe(second);
      expect(repo.get(session.id)?.status).toBe("idle");
    });
  });

  /* ------------------------------------------------------------------ */
  /* Opening a session: the snapshot, the keep-alive, the warm adapter   */
  /* ------------------------------------------------------------------ */

  /**
   * The snapshot is what a session paints from while its agent reconnects
   * (README, "Opening a session"). `close` files it at once, because the
   * adapter is gone and the next click has nothing else to draw.
   */
  it("files a snapshot of the transcript, and state() answers from it once the adapter is gone", async () => {
    const store = memorySnapshots();
    const { manager, cwd } = await setup({ snapshots: store });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    await manager.prompt(session.id, [{ type: "text", text: "hello there" }]);

    // Live: the connection's own state, and nothing about a snapshot.
    expect(manager.state(session.id)).toMatchObject({ live: true });

    manager.close(session.id);
    const painted = manager.state(session.id);
    expect(painted?.live).toBe(false);
    expect(painted?.state.turns.map((turn) => turn.role)).toEqual(["user", "agent"]);
    // The stored status is never `closed`: the composer of a session that is
    // about to be live must not be greyed out (src/main/acp/snapshots.ts).
    expect(painted?.state.status).toBe("idle");

    // Deleting the session takes its picture with it.
    await manager.delete(session.id);
    expect(store.rows.has(session.id)).toBe(false);
  });

  /**
   * The renderer starts a load behind the painted snapshot, and a prompt
   * typed into that snapshot's composer arrives while it is still running.
   * Two spawns for one session, and a `session/prompt` in the middle of a
   * `session/load`, is what the in-flight map prevents.
   */
  it("joins a load already in flight rather than spawning a second adapter", async () => {
    const { manager, cwd } = await setup({ snapshots: memorySnapshots() });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    manager.close(session.id);

    const [first, second] = await Promise.all([manager.load(session.id), manager.load(session.id)]);
    expect(first).toBe(second);
    expect(first.status).toBe("idle");

    // A prompt sent while a load runs waits for it and lands on the same
    // connection, rather than being sent into the middle of the replay.
    manager.close(session.id);
    const loading = manager.load(session.id);
    const { stopReason } = await manager.prompt(session.id, [{ type: "text", text: "hello again" }]);
    await loading;
    expect(stopReason).toBe("end_turn");
  });

  /**
   * A reconnect's state is the beginning of its own replay: turns empty until
   * `session/load` has streamed them. Filed over the stored transcript — by a
   * failed load's debounce, or by a quit in the first second — it destroys the
   * only copy of the history.
   */
  it("keeps a stored turn's stop reason and late label across a session/load", async () => {
    // The replay carries no `prompt/end` and no stop reason: every replayed
    // agent turn ends `end_turn`, and late text merges into the answer.
    const store = memorySnapshots();
    const { manager, cwd } = await setup({ snapshots: store });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    await manager.prompt(session.id, [{ type: "text", text: "hello there" }]);
    manager.close(session.id);

    const saved = JSON.parse(store.rows.get(session.id)!);
    const last = saved.turns.at(-1);
    expect(last.role).toBe("agent");
    // What the fake agent replays for any session: the stored transcript is of the same text.
    saved.turns[0].parts = [{ type: "text", text: "earlier prompt" }];
    last.parts = [{ type: "text", text: "earlier reply" }];
    last.stopReason = "cancelled";
    last.lateFrom = last.parts.length - 1;
    store.rows.set(session.id, JSON.stringify(saved));

    const state = await manager.load(session.id);
    expect(state.turns.at(-1)).toMatchObject({ role: "agent", stopReason: "cancelled", lateFrom: last.lateFrom });
    manager.closeAll();
    expect(JSON.parse(store.rows.get(session.id)!).turns.at(-1)).toMatchObject({ stopReason: "cancelled", lateFrom: last.lateFrom });
  });

  it("splits the late text a session/load merged into the answer, restoring the stop and the label", async () => {
    const store = memorySnapshots();
    const { manager, cwd } = await setup({ snapshots: store });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    await manager.prompt(session.id, [{ type: "text", text: "hello there" }]);
    manager.close(session.id);

    const saved = JSON.parse(store.rows.get(session.id)!);
    const last = saved.turns.at(-1);
    saved.turns[0].parts = [{ type: "text", text: "earlier prompt" }];
    // Live: "earlier " then, after the stop, "reply". The replay joins them into "earlier reply".
    last.parts = [{ type: "text", text: "earlier " }, { type: "text", text: "reply" }];
    last.stopReason = "cancelled";
    last.lateFrom = 1;
    store.rows.set(session.id, JSON.stringify(saved));

    const state = await manager.load(session.id);
    expect(state.turns.at(-1)).toMatchObject({
      stopReason: "cancelled",
      lateFrom: 1,
      parts: [{ text: "earlier " }, { text: "reply" }],
    });
  });

  it("keeps the stored transcript when a reconnect's session/load is refused", async () => {
    let launchArgs = [FAKE_AGENT];
    const store = memorySnapshots();
    const { manager, cwd } = await setup({
      snapshots: store,
      launchOverride: () => ({ ...fakeProvider.launch, args: launchArgs }),
    });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    await manager.prompt(session.id, [{ type: "text", text: "hello there" }]);
    manager.close(session.id);
    expect(JSON.parse(store.rows.get(session.id)!).turns).toHaveLength(2);

    launchArgs = [FAKE_AGENT, "--load-error"];
    await expect(manager.load(session.id)).rejects.toThrow();
    manager.closeAll(); // flushAll: whatever was still pending is written now
    expect(JSON.parse(store.rows.get(session.id)!).turns).toHaveLength(2);
  });

  /**
   * The crashed turn's `prompt/error` queues a save, 750 ms out; a reconnect
   * that fails inside that window used to `discard` it, and with it the only
   * copy of the turns since the last write.
   */
  it("writes the crashed connection's final snapshot when the reconnect fails at once", async () => {
    let launchArgs = [FAKE_AGENT];
    const store = memorySnapshots();
    const { manager, cwd } = await setup({
      snapshots: store,
      launchOverride: () => ({ ...fakeProvider.launch, args: launchArgs }),
    });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    await manager.prompt(session.id, [{ type: "text", text: "hello there" }]);
    await expect(manager.prompt(session.id, [{ type: "text", text: "please crash" }])).rejects.toThrow();

    launchArgs = [FAKE_AGENT, "--load-error"];
    await expect(manager.load(session.id)).rejects.toThrow();
    manager.closeAll();
    const stored = store.rows.get(session.id);
    expect(stored).toContain("hello there");
    expect(stored).toContain("please crash");
  });

  it("keeps the stored transcript when the app quits in the middle of a reconnect's replay", async () => {
    let launchArgs = [FAKE_AGENT];
    const store = memorySnapshots();
    const { broadcasts, manager, cwd } = await setup({
      snapshots: store,
      launchOverride: () => ({ ...fakeProvider.launch, args: launchArgs }),
    });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    await manager.prompt(session.id, [{ type: "text", text: "hello there" }]);
    manager.close(session.id);

    launchArgs = [FAKE_AGENT, "--load-delay", "60000"];
    broadcasts.length = 0;
    const loading = manager.load(session.id);
    loading.catch(() => undefined);
    // `session/load` is on the wire, and the state is the empty beginning of it.
    await until(() =>
      broadcasts.some(
        (b) => b.channel === "session.update" && (b.payload as { event: { type: string } }).event.type === "session/connected",
      )
        ? true
        : undefined,
    );
    manager.closeAll();
    await expect(loading).rejects.toThrow();
    expect(JSON.parse(store.rows.get(session.id)!).turns).toHaveLength(2);
  });

  /**
   * The row is in the sidebar from before `session/new` answers, and the
   * spawn takes one to three seconds: a click in that window is a `load` of a
   * session with no agent session id yet.
   */
  it("joins a create still in session/new when the row is loaded", async () => {
    const { repo, manager, cwd } = await setup({
      launchOverride: () => ({ ...fakeProvider.launch, args: [FAKE_AGENT, "--new-delay", "150"] }),
    });
    const creating = manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    const row = await until(() => repo.list()[0]);
    expect(row.acpSessionId).toBeNull();
    const state = await manager.load(row.id);
    expect(state.status).toBe("idle");
    expect((await creating).acpSessionId).toBe("fake-session-1");
    expect(manager.state(row.id)?.live).toBe(true);
  });

  /**
   * `archive` used to `close` the connection under `session/new`: `newSession`
   * rejected, `create` removed the row and the worktree, and the person had
   * archived a thread that no longer existed and been shown a create error.
   */
  it("archives a row that is still in session/new once its create has settled", async () => {
    const { repo, manager, cwd } = await setup({
      launchOverride: () => ({ ...fakeProvider.launch, args: [FAKE_AGENT, "--new-delay", "150"] }),
    });
    const creating = manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    const row = await until(() => repo.list()[0]);
    expect(row.acpSessionId).toBeNull();
    const archived = await manager.archive(row.id, true);
    expect((await creating).id).toBe(row.id);
    expect(archived).toMatchObject({ id: row.id, archived: true, status: "closed" });
    expect(repo.get(row.id)).toMatchObject({ archived: true, acpSessionId: "fake-session-1" });
  });

  /**
   * `initialize` and `session/new` have no timeout, and `archive` waits for
   * the create: a hung agent left the sidebar's archive click dead.
   */
  it("archives a hung create after the wait, by abandoning it: the row is removed", async () => {
    const timers: (() => void)[] = [];
    const { repo, manager, cwd } = await setup({
      launchOverride: () => ({ ...fakeProvider.launch, args: [FAKE_AGENT, "--new-delay", "600000"] }),
      startTimer: (_ms, fire) => (timers.push(fire), () => undefined),
    });
    const creating = manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    const settled = creating.then(() => "resolved", (error: Error) => error.message);
    const row = await until(() => repo.list()[0]);
    const archiving = manager.archive(row.id, true);
    expect(timers).toHaveLength(1);
    timers[0]!();
    await expect(archiving).resolves.toMatchObject({ id: row.id, archived: true, status: "closed" });
    expect(await settled).not.toBe("resolved");
    await until(() => (repo.get(row.id) ? undefined : true));
  });

  /**
   * `NewSession` sends the first prompt as the create returns; with an archive
   * in between, `prompt -> ensureLive -> load` reconnected the archived row
   * and ran a turn in it.
   */
  it("refuses a prompt to a row archived during its create, and reconnects nothing", async () => {
    const { repo, manager, cwd } = await setup({
      launchOverride: () => ({ ...fakeProvider.launch, args: [FAKE_AGENT, "--new-delay", "150"] }),
    });
    const creating = manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    const row = await until(() => repo.list()[0]);
    await manager.archive(row.id, true);
    await creating;
    await expect(manager.prompt(row.id, [{ type: "text", text: "hello" }])).rejects.toThrow(/archived; unarchive it first/);
    expect(manager.state(row.id)?.live).toBeFalsy();
    expect(repo.get(row.id)).toMatchObject({ archived: true, status: "closed" });
  });

  /**
   * A `close` while the preferences and the marks are pending set `closed`,
   * and `create` wrote `idle` over it and announced a live state for a
   * connection that was gone.
   */
  it("leaves a row closed during the marks closed, and announces no live state for it", async () => {
    let release!: (tree: string) => void;
    const { repo, manager, broadcasts, cwd } = await setup({
      snapshot: () => new Promise<string>((resolve) => (release = resolve)),
    });
    const creating = manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    const id = (await until(() => (repo.list()[0]?.acpSessionId ? repo.list()[0] : undefined))).id;
    manager.close(id);
    release("tree");
    await creating;
    expect(repo.get(id)?.status).toBe("closed");
    expect(broadcasts.some((b) => b.channel === "session.state" && (b.payload as { sessionId: string }).sessionId === id)).toBe(false);
  });

  /**
   * The turn mark waits on git while the connection is idle; a second session
   * opened in that window is what the keep-alive limit evicts the oldest for.
   */
  it("does not evict a session whose prompt is waiting on the turn mark", async () => {
    let release: ((tree: string) => void) | undefined;
    const { manager, cwd } = await setup({
      keepAlive: 1,
      // Only a turn's mark waits; a `none`-mode create marks `<id>/session`.
      snapshot: async (_cwd, mark) =>
        mark.endsWith("/turn") ? new Promise<string>((resolve) => (release = resolve)) : "tree",
    });
    const a = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    const turn = manager.prompt(a.id, [{ type: "text", text: "hello" }]);
    await until(() => release);
    // Opening B during the snapshot takes the limit past one; A is the oldest.
    await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    release!("tree");
    await expect(turn).resolves.toMatchObject({ stopReason: "end_turn" });
  });

  /**
   * `create` waits on its marks (up to five seconds) after `session/new`, with
   * the connection idle: a second create past the limit closed it, and the
   * first then wrote `idle` over the eviction's `closed` and returned a dead
   * session.
   */
  it("does not evict a new session while its create waits on the marks", async () => {
    let release!: (tree: string) => void;
    let gated = false;
    const { manager, broadcasts, cwd } = await setup({
      keepAlive: 1,
      snapshot: (_cwd, _mark) => {
        if (gated) return Promise.resolve("tree");
        gated = true;
        return new Promise<string>((resolve) => (release = resolve));
      },
    });
    const a = manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    await until(() => (connectedCount(broadcasts) > 0 ? true : undefined));
    await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    release("tree");
    const created = await a;
    expect(manager.state(created.id)?.live).toBe(true);
  });

  /**
   * The sidebar's "New session" row is promptable from `session/connected`, and
   * `ensureLive` used to hand the connection over then: the turn ran inside
   * `create`'s window and `create` wrote its session mark over the turn's.
   */
  it("holds a prompt until the create that made the session has returned", async () => {
    let release!: (tree: string) => void;
    let turnMarked = false;
    const { repo, manager, broadcasts, cwd } = await setup({
      snapshot: (_cwd, mark) => {
        if (mark.endsWith("/turn")) {
          turnMarked = true;
          return Promise.resolve("turn-tree");
        }
        return new Promise<string>((resolve) => (release = () => resolve("session-tree")));
      },
    });
    const order: string[] = [];
    const creating = manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    void creating.then(() => order.push("created"));
    await until(() => (connectedCount(broadcasts) > 0 ? true : undefined));
    const id = repo.list()[0]!.id;
    const turn = manager.prompt(id, [{ type: "text", text: "hello" }]);
    void turn.then(() => order.push("prompted"));
    // A prompt that is going to run has taken its mark within a few ticks.
    for (let tick = 0; tick < 50 && !turnMarked; tick++) {
      await new Promise((resolve) => setImmediate(resolve));
    }
    release("session-tree");
    await Promise.all([creating, turn]);
    expect(order).toEqual(["created", "prompted"]);
    expect(repo.get(id)?.turnHead).toBe("turn-tree");
  });

  it("reports a session still being created as connecting, live, until create returns", async () => {
    const { repo, manager, broadcasts, cwd } = await setup({
      snapshot: () => new Promise<string>(() => undefined),
    });
    const creating = manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    creating.catch(() => undefined);
    await until(() => (connectedCount(broadcasts) > 0 ? true : undefined));
    const id = repo.list()[0]!.id;
    expect(manager.state(id)).toMatchObject({ live: true, state: { status: "connecting" } });
  });

  it("writes the agent session id as soon as session/new answers, before the marks land", async () => {
    const { repo, manager, broadcasts, cwd } = await setup({
      snapshot: () => new Promise<string>(() => undefined),
    });
    const creating = manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    creating.catch(() => undefined);
    await until(() => (connectedCount(broadcasts) > 0 ? true : undefined));
    const row = await until(() => {
      const found = repo.list()[0];
      return found?.acpSessionId ? found : undefined;
    }, 500);
    expect(row.acpSessionId).toBe("fake-session-1");
  });

  /**
   * A snapshot of a huge or locked tree can take a minute. The mark is never
   * a reason to fail a turn, nor to hold one back for long: past five seconds
   * the commit stands in for the tree.
   */
  it("keeps the previous mark when a turn's snapshot takes longer than five seconds", async () => {
    const { repo, manager, cwd } = await setup({
      head: async () => "the-commit",
      snapshot: (_cwd, mark) => (mark.endsWith("/turn") ? new Promise<string>(() => undefined) : Promise.resolve("tree")),
    });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    // A none-mode create marks the session, and that is the turn's mark until a turn moves it.
    expect(repo.get(session.id)?.turnHead).toBe("tree");
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      const turn = manager.prompt(session.id, [{ type: "text", text: "hello" }]);
      await vi.advanceTimersByTimeAsync(5_000);
      await expect(turn).resolves.toMatchObject({ stopReason: "end_turn" });
    } finally {
      vi.useRealTimers();
    }
    expect(repo.get(session.id)?.turnHead).toBe("tree");
  });

  it("falls back to HEAD when a turn's snapshot takes longer than five seconds and there is no previous mark", async () => {
    const { repo, manager, cwd } = await setup({
      head: async () => "the-commit",
      snapshot: (_cwd, mark) => (mark.endsWith("/turn") ? new Promise<string>(() => undefined) : Promise.resolve("tree")),
    });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    repo.upsert({ ...repo.get(session.id)!, turnHead: null });
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      const turn = manager.prompt(session.id, [{ type: "text", text: "hello" }]);
      await vi.advanceTimersByTimeAsync(5_000);
      await expect(turn).resolves.toMatchObject({ stopReason: "end_turn" });
    } finally {
      vi.useRealTimers();
    }
    expect(repo.get(session.id)?.turnHead).toBe("the-commit");
  });

  it("keeps the previous mark, not HEAD, when a turn's snapshot fails outright", async () => {
    const { repo, manager, cwd } = await setup({
      head: async () => "the-commit",
      snapshot: async (_cwd, mark) => (mark.endsWith("/turn") ? null : "tree"),
    });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    expect(repo.get(session.id)?.turnHead).toBe("tree");
    await manager.prompt(session.id, [{ type: "text", text: "hello" }]);
    expect(repo.get(session.id)?.turnHead).toBe("tree");
  });

  it("takes one snapshot at a time per mark, so turns behind a slow one do not stack another", async () => {
    const releases: ((tree: string) => void)[] = [];
    let started = 0;
    const { manager, cwd } = await setup({
      snapshot: (_cwd, mark) => {
        if (!mark.endsWith("/turn")) return Promise.resolve("tree");
        started++;
        return new Promise<string>((resolve) => releases.push(resolve));
      },
    });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      for (let turn = 0; turn < 2; turn++) {
        const running = manager.prompt(session.id, [{ type: "text", text: `turn ${turn}` }]);
        await vi.advanceTimersByTimeAsync(5_000);
        await running;
      }
    } finally {
      vi.useRealTimers();
    }
    expect(started).toBe(1);
    releases[0]!("late-tree");
  });

  /**
   * The snapshot goes on after the wait, and pins `<id>/turn` when it lands:
   * after a delete has unpinned the marks that ref would be nobody's.
   */
  it("drops the ref a late turn snapshot pins after the session was deleted", async () => {
    const { head, snapshotTree, dropMarks } = await import("@main/projects/git");
    const { execFileSync } = await import("node:child_process");
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    let reached = false;
    let landed!: () => void;
    const snapshotted = new Promise<void>((resolve) => (landed = resolve));
    const { manager, cwd } = await setup({
      head,
      dropMarks,
      snapshot: async (dir, mark) => {
        if (mark.endsWith("/turn")) {
          reached = true;
          await gate;
        }
        const tree = await snapshotTree(dir, mark);
        if (mark.endsWith("/turn")) landed();
        return tree;
      },
    });
    const run = (...args: string[]) =>
      execFileSync("git", ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", ...args], { cwd, encoding: "utf8" }).trim();
    run("init", "-q");
    await writeFile(path.join(cwd, "base.txt"), "base\n");
    run("add", "-A");
    run("commit", "-q", "-m", "base");

    const session = await manager.create({ projectId: cwd, agentId: "claude-code", cwd, gitMode: "none" });
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    try {
      const turn = manager.prompt(session.id, [{ type: "text", text: "one" }]);
      turn.catch(() => undefined);
      while (!reached) await Promise.resolve();
      await manager.delete(session.id);
      await vi.advanceTimersByTimeAsync(5_000);
      await expect(turn).rejects.toThrow(/no such session/);
    } finally {
      vi.useRealTimers();
    }
    release();
    await snapshotted;
    // The ref exists now; the drop is a git call away. Give it ticks, bounded,
    // and let the assertion say which side it is on.
    for (let tick = 0; tick < 300 && run("for-each-ref", "refs/text-to-cad/") !== ""; tick++) {
      await new Promise((resolve) => setImmediate(resolve));
    }
    expect(run("for-each-ref", "refs/text-to-cad/")).toBe("");
  });

  it("spawns the adapter without waiting for the creating session's snapshot", async () => {
    const { broadcasts, manager, cwd } = await setup({
      head: async () => "the-commit",
      snapshot: () => new Promise<string>(() => undefined),
    });
    const creating = manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    creating.catch(() => undefined);
    // `session/new` answered: the adapter was spawned while the snapshot hangs.
    await until(() =>
      broadcasts.some(
        (b) => b.channel === "session.update" && (b.payload as { event: { type: string } }).event.type === "session/connected",
      )
        ? true
        : undefined,
    );
  });

  it("has no snapshot for a session that never connected, so the spinner stays", async () => {
    const { manager } = await setup({ snapshots: memorySnapshots() });
    expect(manager.state("session-does-not-exist")).toBeNull();
  });

  /**
   * Selecting another session does not close the one before it: switching
   * back is a paint with no spawn, no `initialize` and no replay
   * (src/main/acp/live.ts).
   */
  it("keeps the previous session's adapter alive when another is loaded", async () => {
    const { repo, manager, cwd } = await setup();
    const first = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    const second = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    await manager.load(first.id);
    expect(manager.state(first.id)?.live).toBe(true);
    expect(manager.state(second.id)?.live).toBe(true);
    expect(repo.get(second.id)?.status).not.toBe("closed");
  });

  /** The oldest beyond the limit goes, and its row goes to `closed` so the next click reconnects it. */
  it("closes the oldest adapter beyond the keep-alive limit and marks its row", async () => {
    const { repo, manager, cwd } = await setup({ keepAlive: 1, snapshots: memorySnapshots() });
    const first = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    const second = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    expect(manager.state(second.id)?.live).toBe(true);
    expect(repo.get(first.id)?.status).toBe("closed");
    // Evicted, not forgotten: the row is there and the snapshot paints it.
    expect(manager.state(first.id)?.live).toBe(false);
    // And it comes back on demand, which is what the row's `closed` is for.
    const reloaded = await manager.load(first.id);
    expect(reloaded.status).toBe("idle");
  });

  /**
   * The warm adapter is spawned before any session exists and adopted by the
   * first one that wants that agent in that directory — which is where a
   * Codex session's whole `initialize` goes (README, "Opening a session").
   * A second session finds the pool empty and spawns its own.
   */
  it("hands the warm adapter to the first session and spawns for the second", async () => {
    const { manager, cwd } = await setup();
    await manager.warmAgents();
    // Nothing to warm: an empty index says which agents are in use, and it
    // is empty. So a session first, then a warm, then a load of it.
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    manager.close(session.id);
    await manager.warmAgents();
    await until(() => (manager.warmed("claude-code") ? true : undefined));

    const state = await manager.load(session.id);
    expect(state.status).toBe("idle");
    expect(state.turns.map((turn) => turn.role)).toEqual(["user", "agent"]);
    // Handed out once: the pool's replacement is a different process, and
    // the adapter this load adopted is the session's now.
    expect(manager.state(session.id)?.live).toBe(true);
  });

  /**
   * A warm adapter was spawned with the options of its moment: the PATH the
   * runtime had then, the skills root, the launch. A Python override changed
   * since, a sign-in that refreshed the shell's environment, a skills root
   * materialised after the warm — adopting it would give the session the old
   * ones. It is closed instead, and the session spawns with the options now.
   */
  it("does not hand out a warm adapter spawned with options that have since changed", async () => {
    const file = path.join(await tempDir("text-to-cad-record-"), "frames.jsonl");
    let runtime = "/a";
    const { manager, cwd } = await setup({
      launchOverride: () => ({ ...fakeProvider.launch, env: { FAKE_AGENT_RECORD: file } }),
      runtimePath: () => [runtime],
    });
    const first = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    manager.close(first.id);
    await manager.warmAgents();
    await until(() => (manager.warmed("claude-code") ? true : undefined));

    runtime = "/b";
    await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    const lines = (await readFile(file, "utf8")).trim().split("\n").map((line) => JSON.parse(line) as { kind: string; params: Record<string, unknown> });
    const created = lines.filter((line) => line.kind === "session/new").at(-1)!.params;
    expect(String(created.PATH).split(path.delimiter)[0]).toBe("/b");
  });

  it("skips warming an agent whose directory is gone", async () => {
    const { manager, repo, cwd } = await setup();
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    manager.close(session.id);
    repo.upsert({ ...repo.get(session.id)!, cwd: path.join(cwd, "removed") });
    await manager.warmAgents();
    expect(manager.warmed("claude-code")).toBe(false);
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
          branch: `text-to-cad/${name ?? "generated"}`,
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
      branch: "text-to-cad/Model the wrist",
      worktreePath: `${cwd}/wt`,
      sessionHead: "worktree-head",
    });
    expect(repo.get(worktree.id)?.cwd).toBe(`${cwd}/wt`);
  });

  it("marks the working tree, uncommitted work included, when each turn begins, and unpins the marks on delete", async () => {
    const { head, snapshotTree, dropMarks, status } = await import("@main/projects/git");
    const { resolveDiffScope } = await import("@shared/types");
    const { execFileSync } = await import("node:child_process");
    const { repo, manager, cwd } = await setup({ head, snapshot: snapshotTree, dropMarks });
    const run = (...args: string[]) =>
      execFileSync("git", ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", ...args], { cwd, encoding: "utf8" }).trim();
    run("init", "-q");
    await writeFile(path.join(cwd, "base.txt"), "base\n");
    run("add", "-A");
    run("commit", "-q", "-m", "base");

    const session = await manager.create({ projectId: cwd, agentId: "claude-code", cwd, gitMode: "none" });
    // The first turn leaves a.txt uncommitted; the second starts after it.
    await writeFile(path.join(cwd, "a.txt"), "turn one\n");
    await manager.prompt(session.id, [{ type: "text", text: "one" }]);
    await manager.prompt(session.id, [{ type: "text", text: "two" }]);
    await writeFile(path.join(cwd, "b.txt"), "turn two\n");
    // Turn two began with a.txt already there, so only b.txt is the turn's.
    const row = repo.get(session.id);
    const last = await status(cwd, resolveDiffScope({ kind: "turn" }, row));
    expect(last.files.map((file) => file.path)).toEqual(["b.txt"]);

    expect(run("for-each-ref", "refs/text-to-cad/")).toContain(`refs/text-to-cad/${session.id}/turn`);
    await manager.delete(session.id);
    expect(run("for-each-ref", "refs/text-to-cad/")).toBe("");
  });

  it("does not leave a ref behind when the session is deleted while its turn mark is being taken", async () => {
    const { head, snapshotTree, dropMarks } = await import("@main/projects/git");
    const { execFileSync } = await import("node:child_process");
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    let reached = false;
    const { manager, cwd } = await setup({
      head,
      dropMarks,
      snapshot: async (dir, mark) => {
        if (mark.endsWith("/turn")) {
          reached = true;
          await gate;
        }
        return snapshotTree(dir, mark);
      },
    });
    const run = (...args: string[]) =>
      execFileSync("git", ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", ...args], { cwd, encoding: "utf8" }).trim();
    run("init", "-q");
    await writeFile(path.join(cwd, "base.txt"), "base\n");
    run("add", "-A");
    run("commit", "-q", "-m", "base");

    const session = await manager.create({ projectId: cwd, agentId: "claude-code", cwd, gitMode: "none" });
    const turn = manager.prompt(session.id, [{ type: "text", text: "one" }]);
    turn.catch(() => undefined);
    await until(() => (reached ? true : undefined));
    await manager.delete(session.id);
    release();
    await expect(turn).rejects.toThrow(/no such session/);
    expect(run("for-each-ref", "refs/text-to-cad/")).toBe("");
  });

  it("a session that opens an existing worktree starts from the tree as it is, not from a commit", async () => {
    const { head, snapshotTree, dropMarks, status } = await import("@main/projects/git");
    const { resolveDiffScope } = await import("@shared/types");
    const { execFileSync } = await import("node:child_process");
    const { repo, manager, cwd } = await setup({ head, snapshot: snapshotTree, dropMarks });
    const run = (...args: string[]) =>
      execFileSync("git", ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", ...args], { cwd, encoding: "utf8" }).trim();
    run("init", "-q");
    await writeFile(path.join(cwd, "base.txt"), "base\n");
    run("add", "-A");
    run("commit", "-q", "-m", "base");
    // Earlier work in the worktree, uncommitted, before this session exists.
    await writeFile(path.join(cwd, "earlier.txt"), "before\n");

    const session = await manager.create({ projectId: cwd, agentId: "claude-code", cwd, gitMode: "worktree" });
    await writeFile(path.join(cwd, "mine.txt"), "after\n");
    const listed = await status(cwd, resolveDiffScope({ kind: "session" }, repo.get(session.id)));
    expect(listed.files.map((file) => file.path)).toEqual(["mine.txt"]);
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
  });

  it("refuses a block the agent did not say it takes before the turn is marked, titled or begun", async () => {
    let head = "the-session-starts-here";
    const { repo, manager, cwd } = await setup({
      head: async () => head,
      launchOverride: () => ({ ...fakeProvider.launch, env: { FAKE_AGENT_PROMPT_CAPABILITIES: "{}" } }),
    });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    head = "would-be-the-turn";

    const answer = await manager
      .prompt(session.id, [{ type: "text", text: "look" }, { type: "image", data: "AAAA", mimeType: "image/png", uri: null }])
      .catch(() => null);

    // Nothing moved: `Last turn` still measures the last turn that happened,
    // and the refusal is not a failed turn — no error state, no Retry.
    const row = repo.get(session.id)!;
    expect(row.turnHead).toBe("the-session-starts-here");
    expect(row.title).toBe("New session");
    expect(manager.state(session.id)?.state.status).toBe("idle");
    expect(manager.state(session.id)?.state.turns).toEqual([]);
    // The reason, as an answer the renderer shows beside the draft it keeps.
    expect(answer).toEqual({
      stopReason: "refused",
      refused: "Claude Code cannot take an image in a prompt. Remove the attachment to send.",
    });
  });

  it("keeps the previous turn mark when git cannot read HEAD at the next turn", async () => {
    const head = vi.fn<(cwd: string) => Promise<string | null>>()
      .mockResolvedValueOnce("the-session-starts-here")
      .mockRejectedValueOnce(new Error("fatal: unable to read index"));
    const { repo, manager, cwd } = await setup({ head });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    await manager.prompt(session.id, [{ type: "text", text: "hello" }]);
    const row = repo.get(session.id)!;
    expect(row.turnHead).toBe(row.sessionHead);
    expect(row.turnHead).toBe("the-session-starts-here");
  });

  it("counts a created session by its registry id, and nothing else about it", async () => {
    const track = vi.fn();
    const { manager, cwd } = await setup({ track });
    await expect(manager.create({ projectId: "p1", agentId: "nope", cwd, gitMode: "none" })).rejects.toThrow(/unknown agent/);
    expect(track).not.toHaveBeenCalled();
    await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none", name: "a secret prompt" });
    // No path, project, title or prompt: the README's Telemetry table.
    expect(track.mock.calls).toEqual([[{ name: "session_created", agent: "claude-code" }]]);
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

  it("a create that fails after its worktree was made releases that worktree", async () => {
    const released: { worktreePath: string | undefined; options: unknown }[] = [];
    const { repo, manager, cwd } = await setup({
      workspace: async () => ({ cwd: `${cwd}/wt`, worktreePath: `${cwd}/wt` }),
      releaseWorkspace: async (session, options) => {
        released.push({ worktreePath: session.worktreePath, options });
      },
      // An adapter that is not there: the spawn fails after the worktree exists.
      launchOverride: () => ({ command: path.join(cwd, "no-such-agent"), args: [], env: {} }),
    });
    await expect(manager.create({ projectId: "p1", agentId: "claude-code", gitMode: "worktree" })).rejects.toThrow();
    expect(repo.rows.size).toBe(0);
    expect(released).toEqual([{ worktreePath: `${cwd}/wt`, options: { abandoned: true } }]);
  });

  it("a create whose row cannot be written releases the worktree it cut and unpins its marks", async () => {
    const released: { worktreePath: string | undefined; options: unknown }[] = [];
    const unpinned: string[] = [];
    const repo = memoryRepo();
    let calls = 0;
    const upsert = repo.upsert;
    repo.upsert = (session) => {
      if (++calls === 1) throw new Error("SQLITE_BUSY");
      return upsert(session);
    };
    const { manager } = await setup({
      repo,
      workspace: async () => ({ cwd: `/wt/cut-1`, worktreePath: `/wt/cut-1` }),
      releaseWorkspace: async (session, options) => {
        released.push({ worktreePath: session.worktreePath, options });
      },
      dropMarks: async (_cwd, id) => {
        unpinned.push(id);
      },
    });
    await expect(manager.create({ projectId: "p1", agentId: "claude-code", gitMode: "worktree" })).rejects.toThrow("SQLITE_BUSY");
    expect(released).toEqual([{ worktreePath: `/wt/cut-1`, options: { abandoned: true } }]);
    expect(unpinned.length).toBeGreaterThan(0);
  });

  it("a create whose row can neither be written nor removed still releases and unpins, and rejects with the write error", async () => {
    const released: string[] = [];
    const unpinned: string[] = [];
    const repo = memoryRepo();
    repo.upsert = () => {
      throw new Error("SQLITE_BUSY: upsert");
    };
    repo.remove = () => {
      throw new Error("SQLITE_READONLY: remove");
    };
    const { manager } = await setup({
      repo,
      workspace: async () => ({ cwd: `/wt/cut-1`, worktreePath: `/wt/cut-1` }),
      releaseWorkspace: async (session) => {
        released.push(session.worktreePath ?? "");
      },
      dropMarks: async (_cwd, id) => {
        unpinned.push(id);
      },
    });
    await expect(manager.create({ projectId: "p1", agentId: "claude-code", gitMode: "worktree" })).rejects.toThrow("SQLITE_BUSY: upsert");
    expect(released).toEqual([`/wt/cut-1`]);
    expect(unpinned.length).toBeGreaterThan(0);
  });

  it("a failed create revokes the integration tokens it minted for the session", async () => {
    const forgotten: string[] = [];
    const { manager, cwd } = await setup({
      forgetSession: (id) => forgotten.push(id),
      launchOverride: () => ({ command: path.join("/nonexistent", "no-such-agent"), args: [], env: {} }),
    });
    await expect(manager.create({ projectId: "p1", agentId: "claude-code", gitMode: "none", cwd })).rejects.toThrow();
    expect(forgotten).toEqual(["s1-xxxxxxxx"]);
  });

  it("a failed create in a worktree it was given leaves that worktree alone", async () => {
    const released: string[] = [];
    const { manager, cwd } = await setup({
      workspace: async ({ cwd: given }) => ({ cwd: given!, worktreePath: given! }),
      releaseWorkspace: async (session) => {
        released.push(session.worktreePath ?? "");
      },
      launchOverride: () => ({ command: path.join(cwd, "no-such-agent"), args: [], env: {} }),
    });
    await expect(manager.create({ projectId: "p1", agentId: "claude-code", gitMode: "worktree", cwd })).rejects.toThrow();
    expect(released).toEqual([]);
  });

  it("says a created workspace is settled only once its row exists", async () => {
    const seen: (string | undefined)[] = [];
    const { repo, manager, cwd } = await setup({
      workspace: async () => ({ cwd, worktreePath: `${cwd}/wt` }),
      workspaceSettled: (workspace) => {
        seen.push([...repo.rows.values()].find((row) => row.worktreePath === workspace.worktreePath)?.worktreePath);
      },
    });
    await manager.create({ projectId: "p1", agentId: "claude-code", gitMode: "worktree" });
    expect(seen).toEqual([`${cwd}/wt`]);
  });

  it("delete removes the row, then runs beforeRelease, then releases the worktree", async () => {
    const order: string[] = [];
    const { repo, manager, cwd } = await setup({
      workspace: async () => ({ cwd, worktreePath: `${cwd}/wt` }),
      releaseWorkspace: async () => {
        order.push("release");
      },
    });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", gitMode: "worktree" });
    await manager.delete(session.id, {
      beforeRelease: () => {
        order.push(repo.get(session.id) ? "dispose (row still there)" : "dispose");
      },
    });
    expect(order).toEqual(["dispose", "release"]);
  });

  it("a delete whose row cannot be removed disposes nothing and releases nothing", async () => {
    const released: string[] = [];
    const disposed: string[] = [];
    const { repo, manager, cwd } = await setup({
      workspace: async () => ({ cwd, worktreePath: `${cwd}/wt` }),
      releaseWorkspace: async () => {
        released.push("release");
      },
    });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", gitMode: "worktree" });
    repo.remove = () => {
      throw new Error("database is locked");
    };
    await expect(manager.delete(session.id, { beforeRelease: () => { disposed.push("dispose"); } })).rejects.toThrow("database is locked");
    expect(disposed).toEqual([]);
    expect(released).toEqual([]);
  });

  it("a delete whose row cannot be removed leaves the adapter alive and the row as it was", async () => {
    const { repo, manager, cwd } = await setup();
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    repo.remove = () => {
      throw new Error("database is locked");
    };
    await expect(manager.delete(session.id)).rejects.toThrow("database is locked");
    expect(repo.get(session.id)?.status).toBe("idle");
    expect(manager.state(session.id)).not.toBeNull();
  });

  it("a beforeRelease that throws after the row went still resolves, and keeps the worktree", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const released: string[] = [];
    try {
      const { repo, manager, cwd } = await setup({
        workspace: async () => ({ cwd, worktreePath: `${cwd}/wt` }),
        releaseWorkspace: async () => {
          released.push("release");
        },
      });
      const session = await manager.create({ projectId: "p1", agentId: "claude-code", gitMode: "worktree" });
      await expect(
        manager.delete(session.id, {
          beforeRelease: () => {
            throw new Error("terminal stuck");
          },
        }),
      ).resolves.toBeUndefined();
      expect(repo.get(session.id)).toBeNull();
      expect(released).toEqual([]);
    } finally {
      warn.mockRestore();
    }
  });

  it("a beforeRelease that throws still unpins the session's marks", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    try {
      const dropped: string[] = [];
      const { manager, cwd } = await setup({
        workspace: async () => ({ cwd, worktreePath: `${cwd}/wt` }),
        dropMarks: async (_repository, sessionId) => {
          dropped.push(sessionId);
        },
      });
      const session = await manager.create({ projectId: "p1", agentId: "claude-code", gitMode: "worktree" });
      await manager.delete(session.id, {
        beforeRelease: () => {
          throw new Error("x");
        },
      });
      expect(dropped).toContain(session.id);
    } finally {
      warn.mockRestore();
    }
  });

  it("an archive whose write throws leaves the adapter alive and the row not archived", async () => {
    const { repo, manager, cwd } = await setup();
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    const upsert = repo.upsert;
    repo.upsert = () => {
      throw new Error("database is locked");
    };
    await expect(manager.archive(session.id, true)).rejects.toThrow("database is locked");
    repo.upsert = upsert;
    expect(repo.get(session.id)).toMatchObject({ archived: false, status: "idle" });
    expect(manager.state(session.id)).not.toBeNull();
  });

  it("archive then unarchive leaves updatedAt where it was (Undo restores the row's place)", async () => {
    const { repo, manager, cwd } = await setup();
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    repo.upsert({ ...repo.get(session.id)!, updatedAt: 100 });
    await manager.archive(session.id, true);
    expect(repo.get(session.id)).toMatchObject({ archived: true, status: "closed", updatedAt: 100 });
    await manager.archive(session.id, false);
    expect(repo.get(session.id)).toMatchObject({ archived: false, updatedAt: 100 });
  });

  it("says why a worktree was kept when releaseWorkspace does not remove it", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    try {
      const { manager, cwd } = await setup({
        workspace: async () => ({ cwd, worktreePath: `${cwd}/wt` }),
        releaseWorkspace: async () => ({ removed: false, reason: "has uncommitted changes" }),
      });
      const session = await manager.create({ projectId: "p1", agentId: "claude-code", gitMode: "worktree" });
      await manager.delete(session.id);
      expect(warn.mock.calls.map((call) => String(call[0]))).toContainEqual(expect.stringContaining("has uncommitted changes"));
      expect(warn.mock.calls.map((call) => String(call[0]))).toContainEqual(expect.stringContaining(`${cwd}/wt`));
    } finally {
      warn.mockRestore();
    }
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

  /** The fake agent's current model and effort, as it reports them (tests/fake-agent, `settings`). */
  async function settingsIn(manager: SessionManager, sessionId: string): Promise<string> {
    await manager.prompt(sessionId, [{ type: "text", text: "settings" }]);
    const parts = manager.state(sessionId)!.state.turns.at(-1)!.parts;
    const text = parts.find((part) => part.type === "text");
    return text?.type === "text" ? text.text : "";
  }

  /** What the fake agent says it was configured with, in order (tests/fake-agent). */
  async function appliedIn(manager: SessionManager, sessionId: string): Promise<string> {
    await manager.prompt(sessionId, [{ type: "text", text: "applied" }]);
    const parts = manager.state(sessionId)!.state.turns.at(-1)!.parts;
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
    const state = manager.state(session.id)!.state;
    expect(state.configOptions.find((option) => option.id === "model")?.currentValue).toBe("smart");
    expect(state.currentModeId).toBe("auto");
    // And the session's own snapshot went to the cache — the modes with the
    // options, because the new-session screen's mode chip is drawn from them.
    expect(recorder.remembered.at(-1)?.ids).toContain("model");
    expect(recorder.remembered.at(-1)?.modes).toEqual(["default", "plan", "auto", "full"]);
  });

  it("resolves a create whose setup failed after session/new: one idle row, the failure told to the index", async () => {
    const recorder = optionRecorder({ model: null });
    const deps = {
      ...recorder.deps,
      // The first call is the store settling on the agent's defaults during session/new; the second is applyPreferences.
      remember: (...args: Parameters<typeof recorder.deps.remember>) => {
        if (recorder.remembered.length >= 1) throw new Error("SQLITE_BUSY");
        recorder.deps.remember(...args);
      },
    };
    const { repo, manager, broadcasts, cwd } = await setup({ agentOptions: deps });
    const created = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    const id = "s1-xxxxxxxx";
    expect(created).toMatchObject({ id, status: "idle", acpSessionId: "fake-session-1" });
    expect(repo.list()).toHaveLength(1);
    expect(repo.get(id)?.status).toBe("idle");
    expect(broadcasts.some((b) => b.channel === "session.state" && (b.payload as { sessionId: string }).sessionId === id)).toBe(true);
    const note = broadcasts.find((b) => b.channel === "session.status" && (b.payload as { error: string | null }).error);
    expect((note?.payload as { error: string }).error).toContain("SQLITE_BUSY");
  });

  it("retrySetup re-runs the setup on the live session and, when it goes through, says no note remains", async () => {
    const recorder = optionRecorder({ model: null });
    let failing = true;
    const deps = {
      ...recorder.deps,
      remember: (...args: Parameters<typeof recorder.deps.remember>) => {
        if (failing && recorder.remembered.length >= 1) throw new Error("SQLITE_BUSY");
        recorder.deps.remember(...args);
      },
    };
    const { manager, broadcasts, cwd } = await setup({ agentOptions: deps });
    const created = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    const notes = () => broadcasts.filter((b) => b.channel === "session.status" && (b.payload as { error: string | null }).error);
    expect(notes()).toHaveLength(1);
    const remembered = recorder.remembered.length;

    // Still failing: the steps ran again (not a load), and the failure is told again as the note.
    await expect(manager.retrySetup(created.id)).resolves.toEqual({ error: expect.stringContaining("SQLITE_BUSY") });
    expect(notes()).toHaveLength(2);

    failing = false;
    broadcasts.length = 0;
    await expect(manager.retrySetup(created.id)).resolves.toEqual({ error: null });
    expect(recorder.remembered.length).toBe(remembered + 1);
    expect(notes()).toHaveLength(0);
    expect(manager.state(created.id)?.state.status).toBe("idle");
  });

  it("broadcasts a status only when it changed or carries a note", async () => {
    const { manager, broadcasts, cwd } = await setup();
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    const setStatus = (status: string, error?: string) =>
      (manager as unknown as { setStatus: (id: string, status: string, error?: string) => void }).setStatus(session.id, status, error);
    const statuses = () => broadcasts.filter((b) => b.channel === "session.status").map((b) => b.payload);
    broadcasts.length = 0;
    setStatus("idle");
    expect(statuses()).toEqual([]);
    setStatus("idle", "a note");
    expect(statuses()).toEqual([{ sessionId: session.id, status: "idle", error: "a note" }]);
  });

  it("abandons a create whose settle fails too, rather than leave a live connection on a connecting row", async () => {
    const recorder = optionRecorder({ model: null });
    const deps = {
      ...recorder.deps,
      remember: (...args: Parameters<typeof recorder.deps.remember>) => {
        if (recorder.remembered.length >= 1) throw new Error("SQLITE_BUSY");
        recorder.deps.remember(...args);
      },
    };
    const { repo, manager, cwd } = await setup({ agentOptions: deps });
    const upsert = repo.upsert;
    // The store is down for good: nothing goes idle.
    repo.upsert = (session) => {
      if (session.status === "idle") throw new Error("SQLITE_BUSY");
      return upsert(session);
    };
    await expect(manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" })).rejects.toThrow("SQLITE_BUSY");
    expect(repo.list()).toHaveLength(0);
    expect((manager as unknown as { live: { get(id: string): unknown } }).live.get("s1-xxxxxxxx")).toBeUndefined();
  });

  it("rejects a create whose row was deleted under it with the error the renderer swallows", async () => {
    let release!: (tree: string) => void;
    const { repo, manager, cwd } = await setup({ snapshot: () => new Promise<string>((resolve) => (release = resolve)) });
    const creating = manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    const id = (await until(() => (repo.list()[0]?.acpSessionId ? repo.list()[0] : undefined))).id;
    await manager.delete(id);
    release("tree");
    await expect(creating).rejects.toThrow(DELETED_WHILE_STARTING);
    expect(repo.list()).toHaveLength(0);
  });

  it("rejects a create whose adapter died after session/new, and leaves no row behind", async () => {
    const recorder = optionRecorder({ model: null });
    const made = {} as Awaited<ReturnType<typeof setup>>;
    const deps = {
      ...recorder.deps,
      remember: (...args: Parameters<typeof recorder.deps.remember>) => {
        if (recorder.remembered.length >= 1) {
          // The adapter is gone without anyone closing it (a crash), so the row is still `connecting`.
          const live = (made.manager as unknown as { live: { get(id: string): object | undefined } }).live.get("s1-xxxxxxxx");
          Object.defineProperty(live, "alive", { get: () => false });
          throw new Error("SQLITE_BUSY");
        }
        recorder.deps.remember(...args);
      },
    };
    Object.assign(made, await setup({ agentOptions: deps }));
    await expect(made.manager.create({ projectId: "p1", agentId: "claude-code", cwd: made.cwd, gitMode: "none" })).rejects.toThrow("SQLITE_BUSY");
    expect(made.repo.list()).toHaveLength(0);
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
    expect(manager.state(session.id)!.state.configOptions.find((option) => option.id === "reasoning_effort")?.currentValue).toBe(
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

  it("brings a model's remembered effort along when the model is switched mid-thread", async () => {
    // The fake agent resets its level to Medium on every model switch, so
    // only the app's memory can put Xhigh back.
    const recorder = optionRecorder({ model: null, efforts: { smart: "xhigh" } });
    const { manager, cwd } = await setup({ agentOptions: recorder.deps });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    await manager.setConfigOption(session.id, "model", "smart");
    expect(recorder.asked).toContain("smart");
    expect(await settingsIn(manager, session.id)).toMatch(/model=smart effort=xhigh/);
    // A model with nothing remembered keeps whatever the agent gave it.
    await manager.setConfigOption(session.id, "model", "fast");
    expect(await settingsIn(manager, session.id)).toMatch(/model=fast effort=medium/);
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

  it("says which agents a probe would run for: an installed CLI, or a launch override", async () => {
    expect(await (await setup()).manager.canProbe("claude-code")).toBe(false);
    expect(await (await setup({ launchOverride: () => fakeProvider.launch })).manager.canProbe("claude-code")).toBe(true);
    expect(await (await setup()).manager.canProbe("no-such-agent")).toBe(false);
  });

  it("does not call an agent absent on the last launch's row: the CLI may have been installed since", async () => {
    const stale = { ...fakeProvider, installed: false, binaryPath: null, version: null, auth: "not-required", checkedAt: 1 } as const;
    let probeStarts!: () => void;
    const held = new Promise<void>((resolve) => (probeStarts = resolve));
    const detector = new AgentDetector([fakeProvider], {
      env: async () => {
        await held;
        return { PATH: "/bin" };
      },
      isExecutable: async (file) => file === "/bin/fake",
      exists: async () => false,
      exec: async () => ({ stdout: "1.0.0", stderr: "", code: 0 }),
      homeDir: () => os.homedir(),
      platform: process.platform,
    }, { read: () => [stale], write: () => {} });
    // A warm launch: the table held is the last launch's, and this launch's probe has not landed.
    expect(detector.list()[0]?.installed).toBe(false);
    const { manager } = await setup({ detector });
    const asked = manager.canProbe("claude-code");
    probeStarts();
    expect(await asked).toBe(true);
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

  /**
   * A warm launch holds the last launch's table until the probe lands, and a
   * restored session auto-loads before that. An `installed: false` in it is a
   * guess (the CLI may have been installed since), not a reason to refuse.
   */
  it("does not refuse an agent as not installed on the last launch's row before this launch's probe lands", async () => {
    const gemini = AGENT_PROVIDERS.find((provider) => provider.id === "gemini-cli")!;
    const staleRow = {
      ...gemini,
      installed: false,
      binaryPath: null,
      version: null,
      auth: "unknown" as const,
      checkedAt: 1,
    };
    // The shell answers only once the load is under way; this launch finds the CLI.
    let release: () => void = () => {};
    const shell = new Promise<{ PATH: string }>((resolve) => {
      release = () => resolve({ PATH: "/usr/local/bin" });
    });
    const detector = new AgentDetector(
      [gemini],
      {
        env: () => shell,
        isExecutable: async (file) => file === "/usr/local/bin/gemini",
        exists: async () => false,
        exec: async () => ({ stdout: "1.0.0", stderr: "", code: 0 }),
        homeDir: () => os.homedir(),
        platform: process.platform,
      },
      { read: () => [staleRow], write: () => {} },
    );
    // The row is made by a manager with a settled detector, and loaded by one that is still warming.
    const { manager: creator, repo, cwd } = await setup();
    const session = await creator.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    creator.close(session.id);
    repo.upsert({ ...repo.get(session.id)!, agentId: "gemini-cli" });
    await rm(cwd, { recursive: true, force: true });
    const { manager } = await setup({ detector, repo });

    // Past the refusal the missing directory is the next thing `connect` says; no agent starts.
    const loading = manager.load(session.id).catch((error: unknown) => error);
    release();
    const failure = await loading;
    expect(String(failure)).not.toMatch(/not installed/);
    expect(String(failure)).toMatch(/directory no longer exists/);
  });

  /**
   * Closing kills the adapter, and the SDK then rejects the turn that was
   * running. That rejection is the closed connection's, not the session's:
   * the row stays `closed` (so the next click reconnects), its place in the
   * sidebar does not move, and the renderer hears `closed` once.
   */
  it("a close during a running turn leaves the row closed, with no prompt/error after it", async () => {
    const { repo, broadcasts, manager, cwd } = await setup();
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    // Through a load, so the session has a tally the turn's failure would persist.
    manager.close(session.id);
    await manager.load(session.id);
    const turn = manager.prompt(session.id, [{ type: "text", text: "slow" }]);
    const settled = turn.catch((error: unknown) => error);
    await until(() => (repo.get(session.id)?.status === "running" ? true : undefined));
    broadcasts.length = 0;

    manager.close(session.id);
    // A stamp no write made, so any `update` after the close shows.
    repo.upsert({ ...repo.get(session.id)!, updatedAt: 1 });
    expect(await settled).toBeInstanceOf(Error);

    expect(repo.get(session.id)?.status).toBe("closed");
    expect(repo.get(session.id)?.updatedAt).toBe(1);
    const events = broadcasts
      .filter((b) => b.channel === "session.update")
      .map((b) => (b.payload as { event: { type: string } }).event.type);
    expect(events).not.toContain("prompt/error");
    const statuses = broadcasts.filter((b) => b.channel === "session.status").map((b) => b.payload);
    expect(statuses).toEqual([{ sessionId: session.id, status: "closed", error: null }]);
  });

  /**
   * `retire` takes the connection out of `live` before it closes, so the
   * `closed` event that ends the turn never reaches `onEvent`; the snapshot
   * `close` flushes has to be the closed connection's state, not the last
   * one before it.
   */
  it("a close during a running turn files the snapshot with the turn ended", async () => {
    const store = memorySnapshots();
    const { repo, manager, cwd } = await setup({ snapshots: store });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    const turn = manager.prompt(session.id, [{ type: "text", text: "slow" }]).catch((error: unknown) => error);
    await until(() => (repo.get(session.id)?.status === "running" ? true : undefined));

    manager.close(session.id);
    await turn;
    const stored = JSON.parse(store.rows.get(session.id)!) as { turns: { role: string; endedAt: number | null }[] };
    expect(stored.turns.at(-1)?.role).toBe("agent");
    expect(stored.turns.at(-1)?.endedAt).not.toBeNull();
  });

  /**
   * A session still in `session/load` is not a candidate for eviction:
   * closing it would reject the load, and with it a prompt waiting on that
   * load in `ensureLive`.
   */
  it("never evicts a session whose load is still running", async () => {
    const { repo, manager, cwd } = await setup({
      keepAlive: 1,
      launchOverride: () => ({ ...fakeProvider.launch, args: [FAKE_AGENT, "--load-delay", "600"] }),
    });
    const first = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    expect(repo.get(first.id)?.status).toBe("closed");

    const loading = manager.load(first.id).catch((error: unknown) => error);
    const prompted = manager.prompt(first.id, [{ type: "text", text: "after the load" }]).catch((error: unknown) => error);
    await until(() => (repo.get(first.id)?.status === "connecting" ? true : undefined));
    // A third session is created while the first is mid-load: the limit is 1.
    await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });

    expect(await loading).toMatchObject({ status: "idle" });
    expect(await prompted).toEqual({ stopReason: "end_turn" });
  });

  it("a retired connection's late writes and a load a delete overtook count nothing for the deleted session", async () => {
    const { broadcasts, manager, cwd } = await setup();
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    manager.close(session.id);
    const tallies = (manager as unknown as { tallies: Map<string, unknown> }).tallies;

    // Deleted while its load is on the way (reading the adapter's options, before it spawns):
    // the load's answer is for nobody.
    const loading = manager.load(session.id).catch(() => undefined);
    await manager.delete(session.id);
    await loading;
    expect(tallies.has(session.id)).toBe(false);
    // Nor is an adapter left live for it, which nothing would ever retire.
    expect(manager.state(session.id)).toBeNull();

    // The listeners of a connection that is not the session's live one — closed, evicted,
    // replaced — still hear its adapter's writes, and none of them is about the row any more.
    const retired = { connection: {} as never };
    const options = (manager as unknown as {
      sessionOptions: (row: Session, replay: object, owner: object) => { onFilesChanged: (paths: string[]) => void };
    }).sessionOptions(session, {}, retired);
    broadcasts.length = 0;
    options.onFilesChanged([path.join(cwd, "late.txt")]);
    expect(tallies.has(session.id)).toBe(false);
    expect(broadcasts.filter((b) => b.channel === "files.changed")).toEqual([]);
  });

  /**
   * The renderer learns a session was closed from `session.update` — that is
   * what sends its next click through `session/load` and clears what it held
   * for the adapter. An eviction and a `close` each say so exactly once.
   */
  it("broadcasts one closed session.update when an adapter is evicted or closed", async () => {
    const { broadcasts, manager, cwd } = await setup({ keepAlive: 1 });
    const closedUpdates = (id: string) =>
      broadcasts.filter((b) => {
        const payload = b.payload as { sessionId: string; event: { type: string; status?: string } };
        return (
          b.channel === "session.update" &&
          payload.sessionId === id &&
          payload.event.type === "status" &&
          payload.event.status === "closed"
        );
      });
    const first = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    const second = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    expect(closedUpdates(first.id)).toHaveLength(1);

    manager.close(second.id);
    expect(closedUpdates(second.id)).toHaveLength(1);
  });

  /**
   * A reconnect main starts on its own — a prompt into a session whose
   * adapter crashed — replaces the dead connection quietly: the renderer is
   * not reconnecting, and a `closed` would show it Disconnected until the new
   * adapter's `session/connected`.
   */
  it("replaces a crashed adapter on the next prompt without announcing closed", async () => {
    const { repo, broadcasts, manager, cwd } = await setup();
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    await expect(manager.prompt(session.id, [{ type: "text", text: "please crash" }])).rejects.toThrow();
    await until(() => (repo.get(session.id)?.status === "error" ? true : undefined));
    broadcasts.length = 0;

    expect(await manager.prompt(session.id, [{ type: "text", text: "ok again" }])).toEqual({ stopReason: "end_turn" });
    const statuses = broadcasts
      .filter((b) => b.channel === "session.update")
      .map((b) => (b.payload as { event: { type: string; status?: string } }).event)
      .filter((event) => event.type === "status");
    expect(statuses).toEqual([]);
  });

  /**
   * The quiet replace means the renderer hears nothing when the old adapter
   * goes; a `connect` that then throws (the shell env probe here, a spawn in
   * the app) has to say so itself, or the row stays `connecting` and the
   * renderer keeps its last status.
   */
  it("says so when the reconnect itself fails after the quiet retire", async () => {
    let probes = 0;
    const { repo, broadcasts, manager, cwd } = await setup({
      runtimePath: () => {
        if (++probes > 1) throw new Error("runtime probe failed");
        return [];
      },
    });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    await expect(manager.prompt(session.id, [{ type: "text", text: "please crash" }])).rejects.toThrow();
    await until(() => (repo.get(session.id)?.status === "error" ? true : undefined));
    broadcasts.length = 0;

    await expect(manager.prompt(session.id, [{ type: "text", text: "ok again" }])).rejects.toThrow(/runtime probe failed/);
    expect(repo.get(session.id)?.status).toBe("error");
    const statuses = broadcasts
      .filter((b) => b.channel === "session.update")
      .map((b) => (b.payload as { event: { type: string; status?: string; error?: string } }).event)
      .filter((event) => event.type === "status");
    expect(statuses).toMatchObject([{ status: "error", error: "runtime probe failed" }]);
  });

  /** A failed load is an error the person should see, not a `closed` row. */
  it("a failed load leaves the row in error, not closed", async () => {
    const dir = await tempDir("text-to-cad-noload-");
    const fixture = path.join(dir, "no-load.jsonl");
    await writeFile(
      fixture,
      [
        { dir: "out", msg: { jsonrpc: "2.0", id: 0, method: "initialize", params: {} } },
        { dir: "in", msg: { jsonrpc: "2.0", id: 0, result: { protocolVersion: 1, agentCapabilities: { loadSession: false }, authMethods: [] } } },
      ]
        .map((frame) => JSON.stringify(frame))
        .join("\n"),
    );
    const { repo, broadcasts, manager, cwd } = await setup({
      launchOverride: () => ({ ...fakeProvider.launch, args: [FAKE_AGENT, "--fixture", fixture] }),
    });
    const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
    manager.close(session.id);

    await expect(manager.load(session.id)).rejects.toThrow(/cannot resume/);
    expect(repo.get(session.id)?.status).toBe("error");
    // The renderer hears it where it listens, once, with the reason.
    const errors = broadcasts.filter(
      (b) =>
        b.channel === "session.update" &&
        (b.payload as { sessionId: string; event: { type: string; status?: string } }).sessionId === session.id &&
        (b.payload as { event: { type: string; status?: string } }).event.type === "status" &&
        (b.payload as { event: { status?: string } }).event.status === "error",
    );
    expect(errors).toHaveLength(1);
    expect(errors[0]!.payload).toMatchObject({ event: { error: expect.stringMatching(/cannot resume/) } });
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
    const file = path.join(await tempDir("text-to-cad-record-"), "frames.jsonl");
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

  it("does not send it again on the reload of an answered session whose adapter replays nothing", async () => {
    const file = path.join(await tempDir("text-to-cad-record-"), "frames.jsonl");
    let launchArgs = [FAKE_AGENT];
    const { manager, cwd } = await setup({
      snapshots: memorySnapshots(),
      launchOverride: () => ({ ...fakeProvider.launch, args: launchArgs, env: { FAKE_AGENT_RECORD: file } }),
      skills: { root: () => "/data/skills/1.2.3", preamble: () => "SKILLS: /data/skills/1.2.3" },
    });
    const session = await manager.create({ projectId: "p1", agentId: "gemini-cli", cwd, gitMode: "none" });
    await manager.prompt(session.id, [{ type: "text", text: "first" }]);
    manager.close(session.id);
    // The reload replays no transcript; the stored one is the evidence.
    launchArgs = [FAKE_AGENT, "--load-empty"];
    await manager.prompt(session.id, [{ type: "text", text: "second" }]);
    const prompts = (await readFile(file, "utf8"))
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line) as { kind: string; params: Record<string, unknown> })
      .filter((line) => line.kind === "prompt");
    expect(prompts).toHaveLength(2);
    expect(prompts[1]!.params.prompt).toEqual([{ type: "text", text: "second" }]);
  });
});

/** How many `session/connected` events have been broadcast: `session/new` has answered that many times. */
function connectedCount(broadcasts: { channel: IpcEventChannel; payload: unknown }[]): number {
  return broadcasts.filter(
    (b) => b.channel === "session.update" && (b.payload as { event: { type: string } }).event.type === "session/connected",
  ).length;
}

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
