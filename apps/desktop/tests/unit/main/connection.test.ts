import { mkdtemp, readFile, realpath } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

import { SessionConnection, type RecordedFrame } from "@main/acp/connection";
import { spawnProcessTerminal } from "@main/acp/process-backend";
import { allToolCalls, lastAgentText } from "@shared/acp/reduce";
import type { SessionEvent } from "@shared/acp/types";

const FAKE_AGENT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "fake-agent", "index.mjs");
const FIXTURES = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "fixtures", "acp");

const open: SessionConnection[] = [];

function connect(options: {
  cwd: string;
  fixture?: string;
  approvalMode?: "ask" | "approve-for-me";
  onEvent?: (event: SessionEvent) => void;
  record?: (frame: RecordedFrame) => void;
  onTerminalOutput?: (terminalId: string, data: string) => void;
  onFilesChanged?: (paths: string[]) => void;
}) {
  const args = [FAKE_AGENT, ...(options.fixture ? ["--fixture", options.fixture] : [])];
  const connection = new SessionConnection({
    sessionId: "test-session",
    agentId: "fake",
    launch: { command: process.execPath, args, env: {} },
    env: { PATH: process.env.PATH ?? "" },
    cwd: options.cwd,
    spawnTerminal: spawnProcessTerminal,
    approvalMode: options.approvalMode,
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
});

async function scratch() {
  return realpath(await mkdtemp(path.join(os.tmpdir(), "hardcore-conn-")));
}

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

  it("approve-for-me answers allow_once without waiting", async () => {
    const connection = connect({ cwd: await scratch(), approvalMode: "approve-for-me" });
    await connection.newSession();
    const response = await connection.prompt([{ type: "text", text: "needs permission" }]);
    expect(response.stopReason).toBe("end_turn");
    expect(connection.state.pendingPermissions).toEqual([]);
    const permissionPart = connection.state.turns[1]?.parts.find((part) => part.type === "permission_request");
    expect(permissionPart).toMatchObject({ outcome: { state: "selected", optionId: "allow-once" } });
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

    const outside = path.join(os.tmpdir(), "hardcore-escape.txt");
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
    await new Promise((resolve) => setTimeout(resolve, 200));
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
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(connection.alive).toBe(false);
    expect(connection.state.status).toBe("error");
    expect(events.some((event) => event.type === "status" && event.status === "error" && /code 3/.test(event.error ?? ""))).toBe(true);
    expect(events.some((event) => event.type === "prompt/error")).toBe(true);
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
