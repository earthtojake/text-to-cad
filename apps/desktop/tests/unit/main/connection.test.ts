import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it, vi } from "vitest";

import { SessionConnection, type RecordedFrame } from "@main/acp/connection";
import { spawnProcessTerminal } from "@main/acp/process-backend";
import { allToolCalls, lastAgentText } from "@shared/acp/reduce";
import type { SessionEvent } from "@shared/acp/types";
import { cleanTempDirs, tempDir } from "./temp-dirs";

const FAKE_AGENT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "fake-agent", "index.mjs");
const FIXTURES = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "fixtures", "acp");

const open: SessionConnection[] = [];

function connect(options: {
  cwd: string;
  fixture?: string;
  /** More switches for the fake agent. */
  agentArgs?: string[];
  skillsRoot?: string | null;
  preamble?: string | null;
  onEvent?: (event: SessionEvent) => void;
  record?: (frame: RecordedFrame) => void;
  onTerminalOutput?: (terminalId: string, data: string) => void;
  onFilesChanged?: (paths: string[]) => void;
  agentId?: string;
  /** The adapter's own environment, for the fake agent's switches. */
  env?: Record<string, string>;
}) {
  const args = [FAKE_AGENT, ...(options.fixture ? ["--fixture", options.fixture] : []), ...(options.agentArgs ?? [])];
  const connection = new SessionConnection({
    sessionId: "test-session",
    agentId: options.agentId ?? "fake",
    launch: { command: process.execPath, args, env: options.env ?? {} },
    env: { PATH: process.env.PATH ?? "" },
    cwd: options.cwd,
    skillsRoot: options.skillsRoot ?? null,
    preamble: options.preamble ?? null,
    spawnTerminal: spawnProcessTerminal,
    onEvent: options.onEvent,
    record: options.record,
    onTerminalOutput: options.onTerminalOutput,
    onFilesChanged: options.onFilesChanged,
  });
  open.push(connection);
  return connection;
}

afterEach(async () => {
  for (const connection of open.splice(0)) {
    connection.close();
    await connection.exited;
  }
  cleanTempDirs();
});

function scratch() {
  return tempDir("text-to-cad-conn-");
}

/**
 * Event-loop ticks until `done`, so nothing here waits on the clock; the cap
 * is a hang turned into a failure that says what never happened.
 */
async function ticksUntil(done: () => boolean, what: string): Promise<void> {
  for (let tick = 0; !done(); tick++) {
    if (tick >= 1_000_000) {
      throw new Error(`gave up waiting for ${what}`);
    }
    await new Promise((resolve) => setImmediate(resolve));
  }
}

describe("the fake agent's slow turn", () => {
  it("leaves no timer behind: once cancelled and its stdin closed, the agent exits by itself", async () => {
    const agent = spawn(process.execPath, [FAKE_AGENT], { stdio: ["pipe", "pipe", "ignore"] });
    const lines: Array<{ id?: number; result?: { sessionId?: string; stopReason?: string } }> = [];
    let buffered = "";
    agent.stdout.on("data", (chunk) => {
      buffered += chunk;
      const parts = buffered.split("\n");
      buffered = parts.pop() ?? "";
      for (const part of parts.filter(Boolean)) lines.push(JSON.parse(part));
    });
    const exited = new Promise<{ code: number | null; signal: NodeJS.Signals | null }>((resolve) =>
      agent.once("exit", (code, signal) => resolve({ code, signal })),
    );
    const send = (message: object) => agent.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", ...message })}\n`);
    try {
      send({ id: 1, method: "initialize", params: { protocolVersion: 1, clientCapabilities: {} } });
      await ticksUntil(() => lines.some((line) => line.id === 1), "initialize");
      send({ id: 2, method: "session/new", params: { cwd: os.tmpdir(), mcpServers: [] } });
      await ticksUntil(() => lines.some((line) => line.id === 2), "session/new");
      const sessionId = lines.find((line) => line.id === 2)!.result!.sessionId!;
      send({ id: 3, method: "session/prompt", params: { sessionId, prompt: [{ type: "text", text: "slow" }] } });
      await ticksUntil(() => lines.some((line) => JSON.stringify(line).includes("working")), "the slow turn to start");
      send({ method: "session/cancel", params: { sessionId } });
      await ticksUntil(() => lines.some((line) => line.id === 3), "the cancelled turn's response");
      expect(lines.find((line) => line.id === 3)!.result!.stopReason).toBe("cancelled");

      agent.stdin.end();
      // No signal is sent: it exits because nothing is left to keep it alive (the vitest timeout is the bound).
      await expect(exited).resolves.toEqual({ code: 0, signal: null });
    } finally {
      agent.kill("SIGKILL");
    }
  });
});

describe("SessionConnection against the fake agent", () => {
  it("initializes, opens a session, and runs a turn to end_turn", async () => {
    const events: SessionEvent[] = [];
    const connection = connect({ cwd: await scratch(), onEvent: (event) => events.push(event) });
    const init = await connection.initialize();
    expect(init.agentInfo?.name).toBe("fake-agent");
    expect(init.agentCapabilities?.loadSession).toBe(true);

    const created = await connection.newSession();
    expect(created.sessionId).toBe("fake-session-1");
    expect(connection.state.status).toBe("idle");
    expect(connection.state.currentModeId).toBe("default");
    expect(connection.state.configOptions.map((option) => option.id)).toEqual(["model", "reasoning_effort"]);

    const response = await connection.prompt([{ type: "text", text: "say ok" }]);
    expect(response.stopReason).toBe("end_turn");
    expect(connection.state.status).toBe("idle");
    expect(lastAgentText(connection.state)).toBe("ok");
    expect(events.map((event) => event.type)).toEqual([
      "session/connected",
      "prompt/start",
      "session/update",
      "session/update",
      "prompt/end",
    ]);
  });

  it("records every frame in both directions", async () => {
    const frames: RecordedFrame[] = [];
    const connection = connect({ cwd: await scratch(), record: (frame) => frames.push(frame) });
    await connection.newSession();
    await connection.prompt([{ type: "text", text: "thought then ok" }]);
    const initialize = frames.find((frame) => frame.dir === "out" && (frame.msg as { method?: string }).method === "initialize");
    expect(initialize?.msg).toMatchObject({
      params: { clientCapabilities: { _meta: { jetbrains: { air: {
        version: 1, capabilities: ["nativeSubagentSessions"],
      } } } } },
    });
    const methods = frames.map((frame) => `${frame.dir}:${(frame.msg as { method?: string }).method ?? "response"}`);
    expect(methods).toEqual([
      "out:initialize",
      "in:response",
      "out:session/new",
      "in:response",
      "out:session/prompt",
      "in:session/update",
      "in:session/update",
      "in:session/update",
      "in:response",
    ]);
  });

  it("asks for permission and continues once the renderer answers", async () => {
    const events: SessionEvent[] = [];
    const connection = connect({ cwd: await scratch(), onEvent: (event) => events.push(event) });
    await connection.newSession();
    const turn = connection.prompt([{ type: "text", text: "needs permission" }]);
    const request = await waitFor(events, "permission/request");
    expect(connection.state.status).toBe("waiting");
    expect(request.request.options.map((option) => option.kind)).toEqual(["allow_once", "allow_always", "reject_once"]);
    expect(request.request.title).toBe("Run ls?");
    expect(connection.respondPermission(request.request.requestId, "allow-once")).toBe(true);
    expect((await turn).stopReason).toBe("end_turn");
    const [call] = allToolCalls(connection.state);
    expect(call).toMatchObject({ id: "cmd-1", status: "completed", output: { selected: "allow-once" } });
    expect(lastAgentText(connection.state)).toBe("ok");
  });

  it("answers a request still pending when the prompt resolves, as the transcript already shows it", async () => {
    const events: SessionEvent[] = [];
    const connection = connect({ cwd: await scratch(), onEvent: (event) => events.push(event) });
    await connection.newSession();
    void connection.client.requestPermission({
      sessionId: connection.state.acpSessionId!,
      toolCall: { toolCallId: "late-1", title: "Run ls?" },
      options: [{ optionId: "allow", name: "Allow", kind: "allow_once" }],
    });
    expect(connection.client.pendingPermissionIds).toHaveLength(1);

    await connection.prompt([{ type: "text", text: "thought then ok" }]);
    expect(connection.client.pendingPermissionIds).toEqual([]);
    expect(events.filter((event) => event.type === "permission/resolve")).toHaveLength(1);
    expect(connection.state.pendingPermissions).toEqual([]);
  });

  /**
   * The reducer's rules for frames behind `prompt/end` (src/shared/acp/reduce.ts): late content
   * rides on the last agent turn as a part of its own and opens no turn nothing would end, and a
   * late `in_progress` does not bring a failed call back. They were unit-only; this is the wire.
   */
  it("settles the turn, then takes the frames behind prompt/end by the reducer's rules", async () => {
    const events: SessionEvent[] = [];
    const connection = connect({ cwd: await scratch(), onEvent: (event) => events.push(event) });
    await connection.newSession();
    const response = await connection.prompt([{ type: "text", text: "late-frames" }]);
    expect(response.stopReason).toBe("end_turn");
    const settled = connection.state.turns.length;
    expect(connection.state.status).toBe("idle");

    // Both late frames, which arrive after the response: the text chunk and the call's update.
    const updates = () => events.filter((event) => event.type === "session/update").length;
    const before = updates();
    await ticksUntil(() => updates() >= before + 2, "the frames behind prompt/end");

    const state = connection.state;
    expect(state.status).toBe("idle");
    // Opened no turn, and left the last one ended rather than streaming.
    expect(state.turns).toHaveLength(settled);
    const turn = state.turns.at(-1)!;
    expect(turn.role).toBe("agent");
    expect(turn.endedAt).not.toBeNull();
    // A part of its own, not glued onto the answer ("First answer.Background task finished.").
    expect(turn.parts.filter((part) => part.type === "text").map((part) => (part as { text: string }).text)).toEqual([
      "First answer.",
      "Background task finished.",
    ]);
    // And the call the turn failed stays failed.
    expect(allToolCalls(state).find((call) => call.id === "late-1")?.status).toBe("failed");
  });

  /**
   * The only way nothing is asked. The client answers no request on
   * anybody's behalf, so a turn with no permission request in it is a turn
   * the agent chose not to ask about — here because the session is in the
   * fake's full-access mode, the way Claude's `Bypass permissions` and
   * Codex's `Full access` behave.
   */
  it("a full-access session gets no permission request at all", async () => {
    const connection = connect({ cwd: await scratch() });
    await connection.newSession();
    await connection.setMode("full");
    const response = await connection.prompt([{ type: "text", text: "needs permission" }]);
    expect(response.stopReason).toBe("end_turn");
    expect(connection.state.pendingPermissions).toEqual([]);
    expect(connection.state.turns[1]?.parts.some((part) => part.type === "permission_request")).toBe(false);
    expect(allToolCalls(connection.state)[0]).toMatchObject({ id: "cmd-1", status: "completed" });
  });

  it("a rejected permission fails the tool call", async () => {
    const events: SessionEvent[] = [];
    const connection = connect({ cwd: await scratch(), onEvent: (event) => events.push(event) });
    await connection.newSession();
    const turn = connection.prompt([{ type: "text", text: "needs permission" }]);
    const request = await waitFor(events, "permission/request");
    connection.respondPermission(request.request.requestId, "reject");
    await turn;
    expect(allToolCalls(connection.state)[0]?.status).toBe("failed");
    expect(lastAgentText(connection.state)).toBe("denied");
  });

  it("serves terminals: create, wait, output, release — and mirrors the output", async () => {
    const chunks: string[] = [];
    const connection = connect({ cwd: await scratch(), onTerminalOutput: (_id, data) => chunks.push(data) });
    await connection.newSession();
    await connection.prompt([{ type: "text", text: "run a terminal" }]);
    const [call] = allToolCalls(connection.state);
    expect(call).toMatchObject({ id: "term-1", status: "completed", content: [{ type: "terminal" }] });
    expect((call?.output as { output: string }).output).toContain("from the terminal");
    expect(chunks.join("")).toContain("from the terminal");
    expect(connection.terminals.has((call!.content[0] as { terminalId: string }).terminalId)).toBe(false);
  });

  it("serves fs reads and cwd-confined writes", async () => {
    const cwd = await scratch();
    const changed: string[][] = [];
    const connection = connect({ cwd, onFilesChanged: (paths) => changed.push(paths) });
    await connection.newSession();

    const inside = path.join(cwd, "note.txt");
    await connection.prompt([{ type: "text", text: `write ${inside}` }]);
    expect(await readFile(inside, "utf8")).toBe("hello\n");
    expect(changed).toEqual([[inside]]);
    expect(allToolCalls(connection.state).at(-1)).toMatchObject({ id: "write-1", status: "completed", content: [{ type: "diff", path: inside }] });

    await connection.prompt([{ type: "text", text: `read ${inside}` }]);
    expect(allToolCalls(connection.state).at(-1)).toMatchObject({ id: "read-1", status: "completed", content: [{ type: "text", text: "hello\n" }] });

    const outside = path.join(os.tmpdir(), "text-to-cad-escape.txt");
    await connection.prompt([{ type: "text", text: `write ${outside}` }]);
    const failed = allToolCalls(connection.state).at(-1);
    expect(failed?.status).toBe("failed");
    expect(JSON.stringify(failed?.content)).toContain("outside the session directory");
  });

  it("carries the draft subagent updates around the SDK schema", async () => {
    const connection = connect({ cwd: await scratch() });
    await connection.newSession();
    await connection.prompt([{ type: "text", text: "use a subagent" }]);
    const parts = connection.state.turns[1]!.parts;
    const subagent = parts.find((part) => part.type === "subagent");
    expect(subagent).toMatchObject({ name: "explorer", task: "look around", state: "completed" });
    expect(subagent?.type === "subagent" && subagent.parts.map((part) => part.type)).toEqual(["text", "tool_call"]);
    expect(connection.state.subagentSessionIds).toEqual(["fake-session-1:child-1"]);
    expect(connection.alive).toBe(true);
  });

  it("cancels a running turn", async () => {
    const connection = connect({ cwd: await scratch() });
    await connection.newSession();
    const turn = connection.prompt([{ type: "text", text: "be slow" }]);
    // The fake agent says "working" and then waits: cancel once it is waiting.
    await vi.waitFor(() => expect(lastAgentText(connection.state)).toBe("working"));
    await connection.cancel();
    expect((await turn).stopReason).toBe("cancelled");
    expect(connection.state.turns[1]?.stopReason).toBe("cancelled");
  });

  it("changes mode and config options", async () => {
    const connection = connect({ cwd: await scratch() });
    await connection.newSession();
    await connection.setMode("plan");
    expect(connection.state.currentModeId).toBe("plan");
    await connection.setConfigOption("model", "smart");
    expect(connection.state.configOptions[0]).toMatchObject({ id: "model", currentValue: "smart" });
    // The effort is a second option of its own, and setting one leaves the
    // other where it was — the composer draws them as two dropdowns.
    await connection.setConfigOption("reasoning_effort", "high");
    expect(connection.state.configOptions).toMatchObject([
      { id: "model", currentValue: "smart" },
      { id: "reasoning_effort", currentValue: "high" },
    ]);
  });

  it("loads a session back through session/load", async () => {
    const connection = connect({ cwd: await scratch() });
    await connection.initialize();
    await connection.loadSession("fake-session-1");
    expect(connection.state.status).toBe("idle");
    expect(connection.state.turns.map((turn) => turn.role)).toEqual(["user", "agent"]);
    expect(lastAgentText(connection.state)).toBe("earlier reply");
    expect(connection.state.currentModeId).toBe("default");
  });

  it("surfaces a crash mid-turn as an error with the exit code", async () => {
    const events: SessionEvent[] = [];
    const connection = connect({ cwd: await scratch(), onEvent: (event) => events.push(event) });
    await connection.newSession();
    await expect(connection.prompt([{ type: "text", text: "please crash" }])).rejects.toThrow();
    await connection.exited;
    await vi.waitFor(() => expect(connection.state.status).toBe("error"));
    expect(connection.alive).toBe(false);
    expect(events.some((event) => event.type === "status" && event.status === "error" && /code 3/.test(event.error ?? ""))).toBe(true);
    expect(events.some((event) => event.type === "prompt/error")).toBe(true);
  });

  it("tells the person which agent stopped during the turn, in words, not as an RPC method", async () => {
    const events: SessionEvent[] = [];
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const connection = connect({ cwd: await scratch(), agentId: "claude-code", onEvent: (event) => events.push(event) });
    await connection.newSession();
    await expect(connection.prompt([{ type: "text", text: "please crash" }])).rejects.toThrow(/^Claude Code exited during the turn\./);
    const shown = events.find((event) => event.type === "prompt/error");
    expect(shown && "message" in shown ? shown.message : "").not.toContain("session/prompt");
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("session/prompt: claude-code exited"));
    warn.mockRestore();
  });

  /**
   * `promptCapabilities` is what the agent said it takes beyond text and a
   * resource link. An image or an embedded file sent to one that did not say
   * so is a prompt it may choke on or silently drop; it is refused here and
   * nothing reaches the agent — nor the transcript: no turn began, so there
   * is no failed turn to show (the manager keeps the draft and says why).
   */
  it("names the agent the way the person knows it, and says what to do, when it refuses", async () => {
    const connection = connect({ cwd: await scratch(), agentId: "claude-code", env: { FAKE_AGENT_PROMPT_CAPABILITIES: "{}" } });
    await connection.newSession();
    expect(connection.refusal([{ type: "image", data: "AAAA", mimeType: "image/png", uri: null }]))
      .toBe("Claude Code cannot take an image in a prompt. Remove the attachment to send.");
    expect(connection.refusal([{ type: "resource", uri: "file:///a.py", text: "print(1)", mimeType: null }]))
      .toBe("Claude Code cannot take a file's contents in a prompt. Remove the attachment to send.");
  });

  it("refuses an image or a file's contents the agent did not say it takes, before the wire", async () => {
    const frames: RecordedFrame[] = [];
    const connection = connect({
      cwd: await scratch(),
      env: { FAKE_AGENT_PROMPT_CAPABILITIES: "{}" },
      record: (frame) => frames.push(frame),
    });
    await connection.newSession();

    await expect(
      connection.prompt([{ type: "text", text: "look" }, { type: "image", data: "AAAA", mimeType: "image/png", uri: null }]),
    ).rejects.toThrow("fake cannot take an image in a prompt. Remove the attachment to send.");
    await expect(
      connection.prompt([{ type: "resource", uri: "file:///a.py", text: "print(1)", mimeType: null }]),
    ).rejects.toThrow("fake cannot take a file's contents in a prompt. Remove the attachment to send.");
    expect(frames.some((frame) => (frame.msg as { method?: string }).method === "session/prompt")).toBe(false);
    expect(connection.state.turns).toEqual([]);
    expect(connection.state.status).toBe("idle");
    expect(connection.refusal([{ type: "resource", uri: "file:///a.py", text: "print(1)", mimeType: null }]))
      .toBe("fake cannot take a file's contents in a prompt. Remove the attachment to send.");

    // Text and a resource link are every agent's baseline.
    const response = await connection.prompt([{ type: "text", text: "say ok" }, { type: "resource_link", uri: "file:///a.py", name: "a.py", mimeType: null, title: null }]);
    expect(response.stopReason).toBe("end_turn");
  });

  it("close is idempotent and ends with a closed status", async () => {
    const connection = connect({ cwd: await scratch() });
    await connection.newSession();
    connection.close();
    connection.close();
    await connection.exited;
    expect(connection.state.status).toBe("closed");
  });
});

/**
 * The Claude adapter's shape, from the fake agent's `claude-code` profile: no
 * successful Claude recording exists to replay (see tests/fake-agent). What
 * is checked is what the smoke showed going wrong — the 129-command list sent
 * after session/new, again mid-turn, and after session/load; the title only
 * ever sent live.
 */
describe("SessionConnection against the Claude adapter's shape", () => {
  const claude = { FAKE_AGENT_PROFILE: "claude-code" };
  const waitFor = async (check: () => boolean) => {
    for (let tries = 0; !check(); tries += 1) {
      if (tries > 200) throw new Error("timed out");
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
  };
  const partTypes = (connection: SessionConnection) =>
    connection.state.turns.flatMap((turn) => turn.parts.map((part) => part.type));

  it("keeps the commands on the session and the title across a reload", async () => {
    const cwd = await scratch();
    const live = connect({ cwd, env: claude });
    const init = await live.initialize();
    expect(init.agentInfo).toMatchObject({ name: "@agentclientprotocol/claude-agent-acp", version: "0.69.0" });
    expect(init.agentCapabilities?.sessionCapabilities).toBeDefined();
    await live.newSession();
    expect(live.state.modes.map((mode) => mode.id)).toEqual([
      "auto",
      "default",
      "acceptEdits",
      "plan",
      "dontAsk",
      "bypassPermissions",
    ]);
    expect(live.state.configOptions.map((option) => option.id)).toEqual(["mode", "model", "effort", "fast"]);
    await waitFor(() => live.state.availableCommands.length === 129);

    await live.prompt([{ type: "text", text: "say ok" }]);
    expect(live.state.title).toBe("Reply with ok");
    expect(live.state.turns[1]).toMatchObject({ stopReason: "end_turn", parts: [{ type: "text", text: "ok" }] });
    expect(partTypes(live)).not.toContain("available_commands");

    const reloaded = connect({ cwd, env: claude });
    await reloaded.initialize();
    await reloaded.loadSession("fake-session-1", live.state.title);
    await waitFor(() => reloaded.state.availableCommands.length === 129);
    expect(reloaded.state.title).toBe("Reply with ok");
    expect(reloaded.state.turns.map((turn) => `${turn.role}:${turn.stopReason}`)).toEqual(["user:null", "agent:end_turn"]);
    expect(partTypes(reloaded)).not.toContain("available_commands");
  });
});

describe("SessionConnection replaying a recorded adapter", () => {
  it("reproduces the Codex session from its fixture", async () => {
    const connection = connect({ cwd: await scratch(), fixture: path.join(FIXTURES, "codex-session.jsonl") });
    const init = await connection.initialize();
    expect(init.agentInfo?.name).toBe("@agentclientprotocol/codex-acp");
    expect(init.authMethods?.map((method) => method.id)).toEqual(["api-key", "chat-gpt"]);
    await connection.newSession();
    expect(connection.state.modes.map((mode) => mode.id)).toEqual(["read-only", "agent", "agent-full-access"]);

    await connection.prompt([{ type: "text", text: "Reply with exactly: ok" }]);
    expect(lastAgentText(connection.state)).toBe("ok");

    await connection.prompt([{ type: "text", text: "Create a file…" }]);
    const [call] = allToolCalls(connection.state);
    expect(call).toMatchObject({ kind: "execute", status: "completed", content: [{ type: "terminal" }] });
    expect(lastAgentText(connection.state)).toContain("hello.txt");
    expect(connection.state.title).toBe("Reply with exactly ok");
    expect(connection.state.status).toBe("idle");
  });
});

describe("SessionConnection resuming a recorded adapter", () => {
  it("replays the Codex history through session/load and continues the conversation", async () => {
    const connection = connect({ cwd: await scratch(), fixture: path.join(FIXTURES, "codex-load.jsonl") });
    await connection.initialize();
    await connection.loadSession("01a0755c-9b28-7702-b62c-7c527c3c3cc0");
    expect(connection.state.status).toBe("idle");
    expect(connection.state.turns.map((turn) => turn.role)).toEqual(["user", "agent", "user", "agent"]);
    expect(allToolCalls(connection.state)).toHaveLength(1);
    await connection.prompt([{ type: "text", text: "Which file did you create?" }]);
    expect(lastAgentText(connection.state)).toBe("hello.txt");
    expect(connection.state.turns).toHaveLength(6);
  });
});

async function waitFor<T extends SessionEvent["type"]>(
  events: SessionEvent[],
  type: T,
  timeoutMs = 5_000,
): Promise<Extract<SessionEvent, { type: T }>> {
  const started = Date.now();
  for (;;) {
    const found = events.find((event) => event.type === type);
    if (found) {
      return found as Extract<SessionEvent, { type: T }>;
    }
    if (Date.now() - started > timeoutMs) {
      throw new Error(`no ${type} event within ${timeoutMs}ms`);
    }
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}

/** The params of one outbound request, from the recorded frames. */
function sent(frames: RecordedFrame[], method: string): Record<string, unknown> | undefined {
  const frame = frames.find(
    (candidate) => candidate.dir === "out" && (candidate.msg as { method?: string }).method === method,
  );
  return frame ? ((frame.msg as { params?: Record<string, unknown> }).params ?? {}) : undefined;
}

function allSent(frames: RecordedFrame[], method: string): Array<Record<string, unknown>> {
  return frames
    .filter((candidate) => candidate.dir === "out" && (candidate.msg as { method?: string }).method === method)
    .map((candidate) => (candidate.msg as { params?: Record<string, unknown> }).params ?? {});
}

describe("an adapter that dies before it answers initialize", () => {
  it("says it exited, with what it printed", async () => {
    const connection = new SessionConnection({
      sessionId: "test-session",
      agentId: "fake",
      launch: { command: process.execPath, args: ["-e", "console.error('boom'); process.exit(2)"], env: {} },
      env: { PATH: process.env.PATH ?? "" },
      cwd: await scratch(),
      spawnTerminal: spawnProcessTerminal,
    });
    open.push(connection);
    await expect(connection.initialize()).rejects.toThrow(/exited.*boom/s);
  });
});

describe("the skills root and the preamble", () => {
  it("names the root in session/new under both spellings, beside the MCP servers", async () => {
    const frames: RecordedFrame[] = [];
    const connection = connect({ cwd: await scratch(), skillsRoot: "/data/skills/1.2.3", record: (frame) => frames.push(frame) });
    await connection.newSession();

    const params = sent(frames, "session/new")!;
    expect(params.additionalDirectories).toEqual(["/data/skills/1.2.3"]);
    expect(params._meta).toMatchObject({ additionalRoots: ["/data/skills/1.2.3"] });
    expect(params.mcpServers).toEqual([]);
  });

  it("names it in session/load too", async () => {
    const frames: RecordedFrame[] = [];
    const connection = connect({ cwd: await scratch(), skillsRoot: "/data/skills/1.2.3", record: (frame) => frames.push(frame) });
    await connection.loadSession("fake-session-1");

    const params = sent(frames, "session/load")!;
    expect(params.additionalDirectories).toEqual(["/data/skills/1.2.3"]);
    expect(params._meta).toMatchObject({ additionalRoots: ["/data/skills/1.2.3"] });
  });

  it("sends no root at all when the app has none", async () => {
    const frames: RecordedFrame[] = [];
    const connection = connect({ cwd: await scratch(), record: (frame) => frames.push(frame) });
    await connection.newSession();

    const params = sent(frames, "session/new")!;
    expect(params).not.toHaveProperty("additionalDirectories");
    expect(params).not.toHaveProperty("_meta");
  });

  it("puts the preamble in front of the first prompt of a new session, and never again", async () => {
    const frames: RecordedFrame[] = [];
    const events: SessionEvent[] = [];
    const connection = connect({
      cwd: await scratch(),
      skillsRoot: "/data/skills/1.2.3",
      preamble: "The skills are at /data/skills/1.2.3.",
      record: (frame) => frames.push(frame),
      onEvent: (event) => events.push(event),
    });
    await connection.newSession();
    await connection.prompt([{ type: "text", text: "hello" }]);
    await connection.prompt([{ type: "text", text: "again" }]);

    const prompts = allSent(frames, "session/prompt");
    expect(prompts).toHaveLength(2);
    expect(prompts[0]!.prompt).toEqual([
      { type: "text", text: "The skills are at /data/skills/1.2.3." },
      { type: "text", text: "hello" },
    ]);
    expect(prompts[1]!.prompt).toEqual([{ type: "text", text: "again" }]);

    // The transcript is what the person wrote; the preamble is not in it.
    const started = events.filter((event) => event.type === "prompt/start");
    expect(started[0]).toMatchObject({ content: [{ type: "text", text: "hello" }] });
  });

  it("carries the preamble again when the first prompt was rejected", async () => {
    const frames: RecordedFrame[] = [];
    const connection = connect({
      cwd: await scratch(),
      skillsRoot: "/data/skills/1.2.3",
      preamble: "The skills are at /data/skills/1.2.3.",
      record: (frame) => frames.push(frame),
    });
    await connection.newSession();
    vi.spyOn(connection.agent, "prompt").mockRejectedValueOnce(new Error("agent refused the turn"));
    await expect(connection.prompt([{ type: "text", text: "hello" }])).rejects.toThrow();
    await connection.prompt([{ type: "text", text: "again" }]);

    expect(allSent(frames, "session/prompt")[0]!.prompt).toEqual([
      { type: "text", text: "The skills are at /data/skills/1.2.3." },
      { type: "text", text: "again" },
    ]);
  });

  it("does not carry the preamble again when the first prompt streamed and then died", async () => {
    const connection = connect({
      cwd: await scratch(),
      skillsRoot: "/data/skills/1.2.3",
      preamble: "The skills are at /data/skills/1.2.3.",
    });
    await connection.newSession();
    const turn = connection.prompt([{ type: "text", text: "slow" }]).catch((error: unknown) => error);
    await ticksUntil(() => lastAgentText(connection.state) === "working", "the agent's first chunk");
    connection.process.kill("SIGKILL");
    expect(await turn).toBeInstanceOf(Error);

    // The dead adapter cannot answer; what matters is what the next prompt is built from.
    const next = vi.spyOn(connection.agent, "prompt").mockResolvedValue({ stopReason: "end_turn" });
    await connection.prompt([{ type: "text", text: "again" }]);
    expect(next.mock.calls[0]![0].prompt).toEqual([{ type: "text", text: "again" }]);
  });

  it("carries the preamble again when the only update heard before the turn failed was housekeeping", async () => {
    const frames: RecordedFrame[] = [];
    const connection = connect({
      cwd: await scratch(),
      skillsRoot: "/data/skills/1.2.3",
      preamble: "The skills are at /data/skills/1.2.3.",
      record: (frame) => frames.push(frame),
    });
    await connection.newSession();
    // The agent announces a title (an update that says nothing of having read
    // the prompt), and then the turn fails.
    const real = connection.agent.prompt.bind(connection.agent);
    vi.spyOn(connection.agent, "prompt").mockImplementationOnce(async (params) => {
      await real(params);
      throw new Error("agent died before reading");
    });
    await expect(connection.prompt([{ type: "text", text: `session-title ${JSON.stringify({ title: "Named" })}` }])).rejects.toThrow();
    await connection.prompt([{ type: "text", text: "again" }]);

    expect(allSent(frames, "session/prompt")[1]!.prompt).toEqual([
      { type: "text", text: "The skills are at /data/skills/1.2.3." },
      { type: "text", text: "again" },
    ]);
  });

  it("never sends the preamble on a resumed session — the transcript already has it", async () => {
    const frames: RecordedFrame[] = [];
    const connection = connect({
      cwd: await scratch(),
      skillsRoot: "/data/skills/1.2.3",
      preamble: "The skills are at /data/skills/1.2.3.",
      record: (frame) => frames.push(frame),
    });
    await connection.loadSession("fake-session-1");
    await connection.prompt([{ type: "text", text: "hello" }]);

    expect(allSent(frames, "session/prompt")[0]!.prompt).toEqual([{ type: "text", text: "hello" }]);
  });

  it("carries the preamble to a session that was created and never prompted, once its connection is replaced", async () => {
    const preamble = "The skills are at /data/skills/1.2.3.";
    const first = connect({ cwd: await scratch(), agentId: "gemini-cli", preamble });
    await first.newSession();
    first.close();

    const frames: RecordedFrame[] = [];
    const second = connect({
      cwd: await scratch(),
      agentId: "gemini-cli",
      preamble,
      agentArgs: ["--load-empty"],
      record: (frame) => frames.push(frame),
    });
    await second.loadSession("fake-session-1");
    await second.prompt([{ type: "text", text: "hello" }]);
    await second.prompt([{ type: "text", text: "again" }]);

    const prompts = allSent(frames, "session/prompt");
    expect(prompts[0]!.prompt).toEqual([
      { type: "text", text: preamble },
      { type: "text", text: "hello" },
    ]);
    expect(prompts[1]!.prompt).toEqual([{ type: "text", text: "again" }]);
  });

  it("dispatches nothing after close, though the SDK rejects the turn that was running", async () => {
    const events: SessionEvent[] = [];
    const connection = connect({ cwd: await scratch(), onEvent: (event) => events.push(event) });
    await connection.newSession();
    const turn = connection.prompt([{ type: "text", text: "slow" }]).catch((error: unknown) => error);
    await ticksUntil(
      () => connection.state.status === "running" && lastAgentText(connection.state) === "working",
      "the turn running with the agent's first chunk",
    );
    connection.close();
    expect(await turn).toBeInstanceOf(Error);
    expect(events.at(-1)).toMatchObject({ type: "status", status: "closed" });
    expect(connection.state.status).toBe("closed");
  });

  /**
   * stderr arrives in whatever chunks the pipe hands over. A line split
   * across two of them is still one line — in `onStderr` and in the tail an
   * unexpected exit shows the person — and a last line with no newline is
   * kept too.
   */
  /**
   * An adapter with a `\r` spinner and no newline writes one line forever.
   * Held whole, that line grows the buffer without end and lands entire in
   * the error the person reads. The line is kept to its tail, and so is the
   * error.
   */
  it("keeps only the tail of a line that never ends, and of the error it ends in", async () => {
    const script = "process.stderr.write('x'.repeat(2e6) + 'the end', () => process.exit(2));";
    const lines: string[] = [];
    const events: SessionEvent[] = [];
    const connection = new SessionConnection({
      sessionId: "test-session",
      agentId: "fake",
      launch: { command: process.execPath, args: ["-e", script], env: {} },
      env: { PATH: process.env.PATH ?? "" },
      cwd: await scratch(),
      spawnTerminal: spawnProcessTerminal,
      onEvent: (event) => events.push(event),
      onStderr: (line) => lines.push(line),
    });
    open.push(connection);
    await connection.exited;
    await ticksUntil(() => events.some((event) => event.type === "status"), "a status event");

    expect(lines).toHaveLength(1);
    expect(lines[0]!.length).toBeLessThanOrEqual(8 * 1024 + 1);
    expect(lines[0]!.endsWith("the end")).toBe(true);
    const exit = events.find((event) => event.type === "status") as { error: string };
    expect(exit.error.length).toBeLessThanOrEqual(4 * 1024 + 100);
    expect(exit.error.startsWith("fake exited unexpectedly (code 2):\n…")).toBe(true);
    expect(exit.error.endsWith("the end")).toBe(true);
  });

  it("reassembles stderr lines that straddle chunks, and keeps an unterminated last line", async () => {
    const script = [
      "process.stderr.write('first half ');",
      "setTimeout(() => process.stderr.write('second half\\nnext line\\npartial '), 40);",
      "setTimeout(() => process.stderr.write('tail'), 80);",
      "setTimeout(() => process.exit(2), 120);",
    ].join("");
    const lines: string[] = [];
    const events: SessionEvent[] = [];
    const connection = new SessionConnection({
      sessionId: "test-session",
      agentId: "fake",
      launch: { command: process.execPath, args: ["-e", script], env: {} },
      env: { PATH: process.env.PATH ?? "" },
      cwd: await scratch(),
      spawnTerminal: spawnProcessTerminal,
      onEvent: (event) => events.push(event),
      onStderr: (line) => lines.push(line),
    });
    open.push(connection);
    await connection.exited;
    // `onProcessExit` runs on the exit promise's own continuation.
    await ticksUntil(() => events.some((event) => event.type === "status"), "a status event");

    expect(lines).toEqual(["first half second half", "next line", "partial tail"]);
    const exit = events.find((event) => event.type === "status");
    expect(exit).toMatchObject({
      status: "error",
      error: "fake exited unexpectedly (code 2):\nfirst half second half\nnext line\npartial tail",
    });
  });
});
