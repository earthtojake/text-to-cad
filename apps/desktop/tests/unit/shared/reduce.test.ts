import path from "node:path";

import { describe, expect, it } from "vitest";

import { allToolCalls, lastAgentText, reduce } from "@shared/acp/reduce";
import {
  SessionStateSchema,
  initialSessionState,
  type SessionEvent,
  type SessionState,
} from "@shared/acp/types";

import { FIXTURE_DIR, eventsFromFrames, fixtureFiles, readFixture, stateFromFixture } from "./fixtures";

const at = 1_000;
const root = "root-session";

function connected(state = initialSessionState("s1", "fake")): SessionState {
  return reduce(state, {
    type: "session/connected",
    acpSessionId: root,
    modes: { currentModeId: "default", availableModes: [{ id: "default", name: "Default", description: null, kind: null }] },
    configOptions: null,
    loading: false,
    at,
  });
}

function update(state: SessionState, update: Record<string, unknown>, acpSessionId = root): SessionState {
  return reduce(state, {
    type: "session/update",
    acpSessionId,
    update: update as SessionEvent extends { update: infer U } ? U : never,
    at,
  });
}

function started(state: SessionState): SessionState {
  return reduce(state, { type: "prompt/start", turnId: "t1", content: [{ type: "text", text: "hi" }], at });
}

describe("reduce: turns and chunks", () => {
  it("opens a user turn and an agent turn on prompt/start and closes them on prompt/end", () => {
    let state = started(connected());
    expect(state.status).toBe("running");
    expect(state.turns.map((turn) => turn.role)).toEqual(["user", "agent"]);
    expect(state.turns[0]?.parts).toEqual([{ type: "text", text: "hi" }]);
    state = reduce(state, {
      type: "prompt/end",
      stopReason: "end_turn",
      usage: { totalTokens: 3, inputTokens: 2, outputTokens: 1, thoughtTokens: null, cachedReadTokens: null, cachedWriteTokens: null },
      at,
    });
    expect(state.status).toBe("idle");
    expect(state.turns[1]?.endedAt).toBe(at);
    expect(state.turns[1]?.stopReason).toBe("end_turn");
    expect(state.turns[1]?.parts.at(-1)?.type).toBe("usage");
    expect(state.lastTurnUsage?.totalTokens).toBe(3);
  });

  it("concatenates text chunks and thought chunks separately, and splits them around a tool call", () => {
    let state = started(connected());
    state = update(state, { sessionUpdate: "agent_thought_chunk", content: { type: "text", text: "hm" } });
    state = update(state, { sessionUpdate: "agent_thought_chunk", content: { type: "text", text: "m" } });
    state = update(state, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "o" } });
    state = update(state, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "k" } });
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "c1", title: "ls", kind: "execute" });
    state = update(state, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "done" } });
    expect(state.turns[1]?.parts.map((part) => (part.type === "tool_call" ? "tool_call" : `${part.type}:${"text" in part ? part.text : ""}`))).toEqual([
      "thought:hmm",
      "text:ok",
      "tool_call",
      "text:done",
    ]);
  });

  it("builds turns from replayed history without a prompt/start", () => {
    let state = reduce(initialSessionState("s1", "fake"), {
      type: "session/connected",
      acpSessionId: root,
      modes: null,
      configOptions: null,
      loading: true,
      at,
    });
    expect(state.status).toBe("connecting");
    state = update(state, { sessionUpdate: "user_message_chunk", content: { type: "text", text: "earlier" } });
    state = update(state, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "reply" } });
    state = update(state, { sessionUpdate: "user_message_chunk", content: { type: "text", text: "again" } });
    state = reduce(state, { type: "session/loaded", at });
    expect(state.status).toBe("idle");
    expect(state.turns.map((turn) => `${turn.role}:${turn.endedAt === null ? "open" : "closed"}`)).toEqual([
      "user:closed",
      "agent:closed",
      "user:closed",
    ]);
  });
});

describe("reduce: tool calls", () => {
  it("upserts by id, replacing the fields an update carries and keeping the rest", () => {
    let state = started(connected());
    state = update(state, {
      sessionUpdate: "tool_call",
      toolCallId: "c1",
      title: "Edit a.txt",
      kind: "edit",
      status: "pending",
      rawInput: { path: "a.txt" },
      locations: [{ path: "/p/a.txt", line: 3 }],
    });
    state = update(state, {
      sessionUpdate: "tool_call_update",
      toolCallId: "c1",
      status: "completed",
      content: [{ type: "diff", path: "/p/a.txt", oldText: "a", newText: "b" }],
    });
    const calls = allToolCalls(state);
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({
      id: "c1",
      title: "Edit a.txt",
      kind: "edit",
      status: "completed",
      input: { path: "a.txt" },
      locations: [{ path: "/p/a.txt", line: 3 }],
      content: [{ type: "diff", path: "/p/a.txt", oldText: "a", newText: "b" }],
    });
  });

  it("creates a tool call for an update nobody announced", () => {
    let state = started(connected());
    state = update(state, { sessionUpdate: "tool_call_update", toolCallId: "ghost", status: "in_progress" });
    expect(allToolCalls(state)).toMatchObject([{ id: "ghost", status: "in_progress", kind: "other" }]);
  });

  it("nests Claude's flattened subagent activity under the parent tool call", () => {
    let state = started(connected());
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "task-1", title: "Task", kind: "think" });
    state = update(state, {
      sessionUpdate: "tool_call",
      toolCallId: "child-1",
      title: "Read",
      kind: "read",
      _meta: { claudeCode: { parentToolUseId: "task-1" } },
    });
    state = update(state, {
      sessionUpdate: "agent_message_chunk",
      content: { type: "text", text: "child text" },
      _meta: { claudeCode: { parentToolUseId: "task-1" } },
    });
    const [task] = allToolCalls(state);
    expect(task?.children.map((part) => part.type)).toEqual(["tool_call", "text"]);
    expect(state.turns[1]?.parts).toHaveLength(1);
  });
});

describe("reduce: draft native subagents", () => {
  it("routes a child session's updates into its subagent part and tracks its state", () => {
    const child = "child-session";
    let state = started(connected());
    state = update(state, { sessionUpdate: "subagent_spawned", subagentSessionId: child, name: "explorer", task: "look" });
    state = update(state, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "hi from child" } }, child);
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "c-read", title: "Read", kind: "read", status: "completed" }, child);
    state = update(state, { sessionUpdate: "subagent_state_update", subagentSessionId: child, state: "completed" });
    const [part] = state.turns[1]!.parts;
    expect(part).toMatchObject({ type: "subagent", sessionId: child, name: "explorer", task: "look", state: "completed" });
    expect(part?.type === "subagent" && part.parts.map((p) => p.type)).toEqual(["text", "tool_call"]);
    expect(state.subagentSessionIds).toEqual([child]);
    expect(allToolCalls(state).map((call) => call.id)).toEqual(["c-read"]);
  });
});

describe("reduce: permissions", () => {
  const request = {
    requestId: "perm-1",
    acpSessionId: root,
    toolCallId: "c1",
    title: "Run ls",
    description: null,
    kind: "execute" as const,
    input: { command: "ls" },
    options: [
      { optionId: "allow-once", name: "Yes", kind: "allow_once" as const, description: null },
      { optionId: "reject", name: "No", kind: "reject_once" as const, description: null },
    ],
  };

  it("parks the request, marks the session waiting, and records the answer", () => {
    let state = started(connected());
    state = reduce(state, { type: "permission/request", request, at });
    expect(state.status).toBe("waiting");
    expect(state.pendingPermissions).toHaveLength(1);
    expect(state.turns[1]?.parts.at(-1)).toMatchObject({ type: "permission_request", outcome: { state: "pending" } });
    state = reduce(state, { type: "permission/resolve", requestId: "perm-1", outcome: { state: "selected", optionId: "allow-once" }, at });
    expect(state.status).toBe("running");
    expect(state.pendingPermissions).toEqual([]);
    expect(state.turns[1]?.parts.at(-1)).toMatchObject({ outcome: { state: "selected", optionId: "allow-once" } });
  });

  it("drops unanswered requests when the turn ends", () => {
    let state = started(connected());
    state = reduce(state, { type: "permission/request", request, at });
    state = reduce(state, { type: "prompt/end", stopReason: "cancelled", usage: null, at });
    expect(state.pendingPermissions).toEqual([]);
    expect(state.status).toBe("idle");
  });
});

describe("reduce: session-level facts", () => {
  it("updates modes, config options, commands, usage and title whether or not a turn is open", () => {
    let state = connected();
    state = update(state, { sessionUpdate: "current_mode_update", currentModeId: "plan" });
    state = update(state, { sessionUpdate: "available_commands_update", availableCommands: [{ name: "review", description: "Review", input: { hint: "what" } }] });
    state = update(state, { sessionUpdate: "usage_update", used: 10, size: 100, cost: { amount: 0.5, currency: "USD" } });
    state = update(state, { sessionUpdate: "session_info_update", title: "Hello" });
    state = update(state, {
      sessionUpdate: "config_option_update",
      configOptions: [
        { id: "model", name: "Model", type: "select", currentValue: "a", options: [{ group: "g", name: "Group", options: [{ value: "a", name: "A" }] }] },
        { id: "fast", name: "Fast", type: "boolean", currentValue: true },
      ],
    });
    expect(state.currentModeId).toBe("plan");
    expect(state.availableCommands).toEqual([{ name: "review", description: "Review", hint: "what" }]);
    expect(state.contextUsage).toEqual({ used: 10, size: 100, cost: { amount: 0.5, currency: "USD" } });
    expect(state.title).toBe("Hello");
    expect(state.configOptions).toMatchObject([
      { id: "model", type: "select", currentValue: "a", options: [{ value: "a", name: "A", group: "Group" }] },
      { id: "fast", type: "boolean", currentValue: true },
    ]);
    // No turn was open, so none of it became a part.
    expect(state.turns).toEqual([]);
  });

  it("keeps the latest plan as one part per turn", () => {
    let state = started(connected());
    state = update(state, { sessionUpdate: "plan", entries: [{ content: "a", priority: "high", status: "pending" }] });
    state = update(state, { sessionUpdate: "plan", entries: [{ content: "a", priority: "high", status: "completed" }] });
    const plans = state.turns[1]!.parts.filter((part) => part.type === "plan");
    expect(plans).toHaveLength(1);
    expect(state.plan?.[0]?.status).toBe("completed");
    state = update(state, { sessionUpdate: "plan_removed", planId: "x" });
    expect(state.plan).toBeNull();
  });

  it("surfaces a prompt error as a part and an error status", () => {
    let state = started(connected());
    state = reduce(state, { type: "prompt/error", message: "Authentication required", at });
    expect(state.status).toBe("error");
    expect(state.error).toBe("Authentication required");
    expect(state.turns[1]?.parts.at(-1)).toEqual({ type: "error", message: "Authentication required" });
    expect(state.turns[1]?.endedAt).toBe(at);
  });
});

describe("reduce: recorded adapter transcripts", () => {
  it("has recordings to test against", () => {
    expect(fixtureFiles().length).toBeGreaterThan(0);
  });

  it.each(fixtureFiles().map((file) => [path.basename(file), file]))(
    "%s folds into a schema-valid state with every event applied",
    (_name, file) => {
      const frames = readFixture(file);
      const events = eventsFromFrames(frames);
      expect(events.length).toBeGreaterThan(0);
      const state = stateFromFixture(file);
      expect(() => SessionStateSchema.parse(state)).not.toThrow();
      expect(state.acpSessionId).toBeTruthy();
      expect(state.turns.length).toBeGreaterThan(0);
      // Every turn the fixture closed is closed; the session is not stuck running.
      expect(state.status).not.toBe("running");
    },
  );

  it("codex-session: two turns, the second with a terminal-backed command", () => {
    const state = stateFromFixture(path.join(FIXTURE_DIR, "codex-session.jsonl"));
    expect(state.status).toBe("idle");
    expect(state.currentModeId).toBe("agent");
    expect(state.modes.map((mode) => mode.id)).toEqual(["read-only", "agent", "agent-full-access"]);
    expect(state.configOptions.map((option) => option.id)).toEqual([
      "mode",
      "collaboration_mode",
      "model",
      "reasoning_effort",
      "fast-mode",
    ]);
    expect(state.availableCommands.length).toBeGreaterThan(10);
    expect(state.title).toBe("Reply with exactly ok");
    expect(state.contextUsage?.size).toBe(258400);
    expect(state.turns.map((turn) => turn.role)).toEqual(["user", "agent", "user", "agent"]);

    const [first] = state.turns.filter((turn) => turn.role === "agent");
    expect(first?.parts.find((part) => part.type === "text")).toEqual({ type: "text", text: "ok" });

    const calls = allToolCalls(state);
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({
      kind: "execute",
      status: "completed",
      content: [{ type: "terminal" }],
    });
    expect(calls[0]?.title).toContain("hello.txt");
    expect(lastAgentText(state)).toContain("hello.txt");
    expect(state.lastTurnUsage?.totalTokens).toBe(19598);
  });

  it("codex-load: session/load replays the earlier turns as closed history before the new prompt", () => {
    const state = stateFromFixture(path.join(FIXTURE_DIR, "codex-load.jsonl"));
    expect(state.status).toBe("idle");
    expect(state.acpSessionId).toBe("01a0755c-9b28-7702-b62c-7c527c3c3cc0");
    expect(state.turns.map((turn) => `${turn.role}:${turn.endedAt === null ? "open" : "closed"}`)).toEqual([
      "user:closed",
      "agent:closed",
      "user:closed",
      "agent:closed",
      "user:closed",
      "agent:closed",
    ]);
    // The replayed tool call arrives already completed, terminal ref and all.
    expect(allToolCalls(state)).toMatchObject([{ kind: "execute", status: "completed", content: [{ type: "terminal" }] }]);
    expect(state.turns[1]?.parts).toEqual([{ type: "text", text: "ok" }]);
    expect(lastAgentText(state)).toBe("hello.txt");
    expect(state.title).toBe("Reply with exactly ok");
  });

  it("claude-code-auth-required: the -32000 error ends the turn in an error state", () => {
    const state = stateFromFixture(path.join(FIXTURE_DIR, "claude-code-auth-required.jsonl"));
    expect(state.status).toBe("error");
    expect(state.error).toContain("Authentication required");
    expect(state.modes.map((mode) => mode.id)).toEqual(["default", "acceptEdits", "plan", "auto", "bypassPermissions"]);
    expect(state.configOptions.map((option) => option.id)).toEqual(["mode", "model", "effort", "agent"]);
    expect(state.availableCommands.length).toBeGreaterThan(0);
    expect(state.contextUsage).toEqual({ used: 0, size: 1_000_000, cost: { amount: 0, currency: "USD" } });
    const agentTurn = state.turns.find((turn) => turn.role === "agent");
    expect(agentTurn?.parts.map((part) => part.type)).toEqual(["available_commands", "available_commands", "error"]);
  });
});
