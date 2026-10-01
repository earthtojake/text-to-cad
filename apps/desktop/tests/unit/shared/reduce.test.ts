import path from "node:path";

import { describe, expect, it, vi } from "vitest";

import { allToolCalls, lastAgentText, reduce, withoutParked } from "@shared/acp/reduce";
import {
  SessionEventSchema,
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
    expect(state.turns[1]?.parts.map((part) => part.type)).not.toContain("usage");
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

describe("reduce: what a session/load keeps", () => {
  it("keeps the title it was connected with, and settles every replayed agent turn as ended", () => {
    // A replay sends no `session_info_update` and no stop reasons: the title
    // comes from what the app already knew, and a turn in the history has
    // ended even though nothing says how.
    let state = reduce(initialSessionState("s1", "fake"), {
      type: "session/connected",
      acpSessionId: root,
      modes: null,
      configOptions: null,
      loading: true,
      title: "Design a gripper",
      at,
    });
    state = update(state, { sessionUpdate: "user_message_chunk", content: { type: "text", text: "earlier" } });
    state = update(state, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "reply" } });
    state = update(state, { sessionUpdate: "user_message_chunk", content: { type: "text", text: "again" } });
    state = update(state, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "done" } });
    state = reduce(state, { type: "session/loaded", at });
    expect(state.title).toBe("Design a gripper");
    expect(state.turns.map((turn) => `${turn.role}:${turn.stopReason}`)).toEqual([
      "user:null",
      "agent:end_turn",
      "user:null",
      "agent:end_turn",
    ]);
  });

  it("keeps a title it already had when the connect names none", () => {
    let state = update(connected(), { sessionUpdate: "session_info_update", title: "Hello" });
    state = reduce(state, {
      type: "session/connected",
      acpSessionId: root,
      modes: null,
      configOptions: null,
      loading: true,
      at,
    });
    expect(state.title).toBe("Hello");
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

  /**
   * There is no app-side approval level any more: the session's mode is the
   * whole of what the person decides, so a state that carried an
   * `approvalMode` and an event that changed it would be a second answer to
   * a question that has one.
   */
  it("has no approval mode of its own, in the state or in the events", () => {
    expect(initialSessionState("s1", "fake")).not.toHaveProperty("approvalMode");
    expect(
      SessionEventSchema.safeParse({ type: "approval", mode: "approve-for-me", at }).success,
    ).toBe(false);
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
    expect(state.contextUsage).toEqual({ used: 10, size: 100, cost: { amount: 0.5, currency: "USD" }, breakdown: null });
    expect(state.title).toBe("Hello");
    expect(state.configOptions).toMatchObject([
      { id: "model", type: "select", currentValue: "a", options: [{ value: "a", name: "A", group: "Group" }] },
      { id: "fast", type: "boolean", currentValue: true },
    ]);
    // No turn was open, so none of it became a part.
    expect(state.turns).toEqual([]);
  });

  it("keeps a mid-turn commands list on the session, so a live turn's parts are what its replay's are", () => {
    // The Claude adapter sends `available_commands_update` at session/new
    // and again mid-turn (129 commands). Folded into the open turn, the whole
    // list rode on every turn, live and in the snapshot, and disappeared
    // after a session/load — whose replay carries no such update.
    const commands = Array.from({ length: 129 }, (_, index) => ({ name: `c${index}`, description: "" }));
    let live = started(connected());
    live = update(live, { sessionUpdate: "available_commands_update", availableCommands: commands });
    live = update(live, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "ok" } });
    live = reduce(live, { type: "prompt/end", stopReason: "end_turn", usage: null, at });

    let replay = reduce(initialSessionState("s1", "fake"), {
      type: "session/connected",
      acpSessionId: root,
      modes: null,
      configOptions: null,
      loading: true,
      at,
    });
    replay = update(replay, { sessionUpdate: "user_message_chunk", content: { type: "text", text: "hi" } });
    replay = update(replay, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "ok" } });
    replay = reduce(replay, { type: "session/loaded", at });

    expect(live.turns.map((turn) => turn.parts)).toEqual(replay.turns.map((turn) => turn.parts));
    expect(live.turns[1]?.parts).toEqual([{ type: "text", text: "ok" }]);
    expect(live.availableCommands).toHaveLength(129);
  });

  it("adds every turn's usage up and keeps the last turn's", () => {
    let state = connected();
    const turn = (index: number, usage: Record<string, number>) => {
      state = reduce(state, { type: "prompt/start", turnId: `t${index}`, content: [{ type: "text", text: "hi" }], at });
      state = reduce(state, {
        type: "prompt/end",
        stopReason: "end_turn",
        usage: {
          thoughtTokens: null,
          cachedReadTokens: null,
          cachedWriteTokens: null,
          ...usage,
        } as never,
        at,
      });
    };
    expect(state.sessionUsage).toBeNull();
    turn(1, { totalTokens: 100, inputTokens: 10, outputTokens: 20, cachedReadTokens: 30, cachedWriteTokens: 40 });
    turn(2, { totalTokens: 7, inputTokens: 1, outputTokens: 2 });
    expect(state.sessionUsage).toEqual({
      turns: 2,
      totalTokens: 107,
      inputTokens: 11,
      outputTokens: 22,
      // The second turn reported neither cache field, which counts as zero.
      cachedReadTokens: 30,
      cachedWriteTokens: 40,
    });
    expect(state.lastTurnUsage?.totalTokens).toBe(7);
    // A turn that reported nothing leaves both alone.
    state = reduce(state, { type: "prompt/start", turnId: "t3", content: [{ type: "text", text: "hi" }], at });
    state = reduce(state, { type: "prompt/end", stopReason: "cancelled", usage: null, at });
    expect(state.sessionUsage?.turns).toBe(2);
    expect(state.lastTurnUsage?.totalTokens).toBe(7);
  });

  it("reads a category breakdown out of usage_update's _meta, and none when there is none", () => {
    // No adapter sends one today, so `_meta` is where one can arrive at all:
    // any key ending in `breakdown`, bare or namespaced the way the Claude
    // adapter namespaces its own metadata.
    let state = update(connected(), {
      sessionUpdate: "usage_update",
      used: 31_500,
      size: 258_400,
      _meta: {
        contextBreakdown: [
          { id: "system_prompt", name: "System prompt", tokens: 2_800 },
          { id: "messages", name: "Messages", tokens: 11_500 },
          // Nothing in it is nothing to draw.
          { id: "empty", name: "Empty", tokens: 0 },
        ],
      },
    });
    expect(state.contextUsage?.breakdown).toEqual([
      { id: "system_prompt", name: "System prompt", tokens: 2_800 },
      { id: "messages", name: "Messages", tokens: 11_500 },
    ]);

    // A namespaced key and a plain name → tokens map read the same way.
    state = update(state, {
      sessionUpdate: "usage_update",
      used: 10,
      size: 100,
      _meta: { "_claude/contextBreakdown": { "System prompt": 4, Messages: 6 } },
    });
    expect(state.contextUsage?.breakdown).toEqual([
      { id: "System prompt", name: "System prompt", tokens: 4 },
      { id: "Messages", name: "Messages", tokens: 6 },
    ]);

    // The real shape of both adapters: no `_meta`, or one about something
    // else. The popover then shows no categories rather than inventing any.
    state = update(state, { sessionUpdate: "usage_update", used: 32_658, size: 1_000_000 });
    expect(state.contextUsage?.breakdown).toBeNull();
    state = update(state, {
      sessionUpdate: "usage_update",
      used: 32_658,
      size: 1_000_000,
      cost: { amount: 0.28, currency: "USD" },
      _meta: { "_claude/origin": { kind: "human" } },
    });
    expect(state.contextUsage?.breakdown).toBeNull();
  });

  it("keeps the latest of each plan limit out of usage_update's _meta", () => {
    // What the Claude adapter forwards: the SDK's `rate_limit_event`
    // verbatim under `_claude/rateLimit`, on a `usage_update` carrying the
    // window. One event is one limit type.
    let state = update(connected(), {
      sessionUpdate: "usage_update",
      used: 292_300,
      size: 1_000_000,
      _meta: {
        "_claude/rateLimit": {
          status: "allowed",
          rateLimitType: "five_hour",
          utilization: 0.17,
          resetsAt: 1_800_000_000,
        },
      },
    });
    expect(state.rateLimits.five_hour).toEqual({
      type: "five_hour",
      status: "allowed",
      utilization: 0.17,
      // Epoch seconds on the wire, epoch milliseconds in the state.
      resetsAt: 1_800_000_000_000,
      isUsingOverage: null,
    });
    // The window came along with it and is not lost to the limit.
    expect(state.contextUsage?.used).toBe(292_300);

    // A second type is a second row, and a second event of a type replaces
    // it rather than adding to it.
    state = update(state, {
      sessionUpdate: "usage_update",
      used: 292_300,
      size: 1_000_000,
      _meta: {
        "_claude/rateLimit": {
          status: "allowed_warning",
          rateLimitType: "seven_day",
          utilization: 0.63,
          isUsingOverage: true,
        },
      },
    });
    state = update(state, {
      sessionUpdate: "usage_update",
      used: 292_300,
      size: 1_000_000,
      _meta: {
        "_claude/rateLimit": { status: "rejected", rateLimitType: "seven_day", utilization: 0.96 },
      },
    });
    expect(Object.keys(state.rateLimits).sort()).toEqual(["five_hour", "seven_day"]);
    expect(state.rateLimits.seven_day).toMatchObject({ status: "rejected", utilization: 0.96 });
    expect(state.rateLimits.five_hour?.utilization).toBe(0.17);

    // Milliseconds already, and a percentage where a fraction was expected:
    // both are read for what they can only mean.
    state = update(state, {
      sessionUpdate: "usage_update",
      used: 1,
      size: 2,
      _meta: {
        "_claude/rateLimit": {
          status: "allowed",
          rateLimitType: "seven_day_opus",
          utilization: 96,
          resetsAt: 1_800_000_000_000,
        },
      },
    });
    expect(state.rateLimits.seven_day_opus).toMatchObject({
      utilization: 0.96,
      resetsAt: 1_800_000_000_000,
    });
  });

  it("ignores a malformed rate limit rather than throwing on it", () => {
    const before = update(connected(), {
      sessionUpdate: "usage_update",
      used: 10,
      size: 100,
      _meta: { "_claude/rateLimit": { status: "allowed", rateLimitType: "five_hour", utilization: 0.4 } },
    });
    const malformed = [
      // No type: `rateLimits` is keyed by it and there is nowhere to put this.
      { status: "allowed", utilization: 0.4 },
      // No utilization: a bar with no length.
      { status: "allowed", rateLimitType: "five_hour" },
      // The wrong shapes entirely.
      { rateLimitType: 7, utilization: "lots" },
      "rejected",
      null,
      [],
    ];
    for (const value of malformed) {
      const after = update(before, {
        sessionUpdate: "usage_update",
        used: 10,
        size: 100,
        _meta: { "_claude/rateLimit": value },
      });
      expect(after.rateLimits).toEqual(before.rateLimits);
    }
    // An unknown status is the harmless one; the rest of the event stands.
    const odd = update(before, {
      sessionUpdate: "usage_update",
      used: 10,
      size: 100,
      _meta: { "_claude/rateLimit": { status: "hmm", rateLimitType: "overage", utilization: 150 } },
    });
    // An unreadable status reads as `allowed` and a bar cannot run past its end.
    expect(odd.rateLimits.overage).toMatchObject({ status: "allowed", utilization: 1 });
    // And an update with no window at all still lands its limit.
    const windowless = update(before, {
      sessionUpdate: "usage_update",
      _meta: { "_claude/rateLimit": { status: "allowed", rateLimitType: "seven_day", utilization: 0.5 } },
    });
    expect(windowless.rateLimits.seven_day?.utilization).toBe(0.5);
    expect(windowless.contextUsage).toEqual(before.contextUsage);
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
    expect(state.contextUsage).toEqual({ used: 0, size: 1_000_000, cost: { amount: 0, currency: "USD" }, breakdown: null });
    const agentTurn = state.turns.find((turn) => turn.role === "agent");
    expect(agentTurn?.parts.map((part) => part.type)).toEqual(["error"]);
  });
});

describe("reduce: turn endings settle what was still running", () => {
  function withWork(): SessionState {
    let state = started(connected());
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "p1", title: "ls", kind: "execute", status: "pending" });
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "r1", title: "Task", kind: "think", status: "in_progress" });
    state = update(state, {
      sessionUpdate: "tool_call",
      toolCallId: "r1-child",
      title: "Read",
      kind: "read",
      status: "in_progress",
      _meta: { claudeCode: { parentToolUseId: "r1" } },
    });
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "done", title: "cat", kind: "execute", status: "completed" });
    state = update(state, { sessionUpdate: "subagent_spawned", subagentSessionId: "kid", name: "explorer" });
    return state;
  }

  it("cancels pending and running calls and subagents when a cancelled turn ends", () => {
    const state = reduce(withWork(), { type: "prompt/end", stopReason: "cancelled", usage: null, at });
    expect(Object.fromEntries(allToolCalls(state).map((call) => [call.id, call.status]))).toEqual({
      p1: "cancelled",
      r1: "cancelled",
      "r1-child": "cancelled",
      done: "completed",
    });
    expect(state.turns[1]?.parts.find((part) => part.type === "subagent")).toMatchObject({ state: "cancelled" });
    expect(SessionStateSchema.safeParse(state).success).toBe(true);
  });

  it("fails them when the prompt errors, and leaves them alone on a normal end", () => {
    const failed = reduce(withWork(), { type: "prompt/error", message: "boom", at });
    expect(allToolCalls(failed).filter((call) => call.id !== "done").map((call) => call.status)).toEqual(["failed", "failed", "failed"]);
    expect(failed.turns[1]?.parts.find((part) => part.type === "subagent")).toMatchObject({ state: "failed" });
    // A background command can outlive an ordinary end of turn.
    const ended = reduce(withWork(), { type: "prompt/end", stopReason: "end_turn", usage: null, at });
    expect(allToolCalls(ended).find((call) => call.id === "p1")?.status).toBe("pending");
  });
});

describe("reduce: content that arrives after prompt/end", () => {
  it.each([
    ["an agent_message_chunk", { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "late" } }],
    ["an agent_thought_chunk", { sessionUpdate: "agent_thought_chunk", content: { type: "text", text: "late" } }],
    ["a tool_call", { sessionUpdate: "tool_call", toolCallId: "late", title: "ls", kind: "execute", status: "in_progress" }],
  ])("does not open a turn nothing ends for %s", (_name, late) => {
    let state = started(connected());
    state = reduce(state, { type: "prompt/end", stopReason: "end_turn", usage: null, at });
    const turns = state.turns.length;
    state = update(state, late);
    expect(state.turns).toHaveLength(turns);
    expect(state.turns.at(-1)?.endedAt).not.toBeNull();
    expect(state.turns.at(-1)?.parts.length).toBeGreaterThan(0);
  });

  it("gives a late chunk a text part of its own, and joins the chunks behind it to that one", () => {
    let state = started(connected());
    state = update(state, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "First answer." } });
    state = reduce(state, { type: "prompt/end", stopReason: "end_turn", usage: null, at });
    state = update(state, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "Background task " } });
    expect(state.turns.at(-1)?.parts).toEqual([
      { type: "text", text: "First answer." },
      { type: "text", text: "Background task " },
    ]);
    state = update(state, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "finished." } });
    expect(state.turns.at(-1)?.parts).toEqual([
      { type: "text", text: "First answer." },
      { type: "text", text: "Background task finished." },
    ]);
    expect(state.turns.at(-1)?.endedAt).not.toBeNull();
  });

  it("starts a late chunk's own part again after the next turn", () => {
    let state = started(connected());
    state = reduce(state, { type: "prompt/end", stopReason: "end_turn", usage: null, at });
    state = update(state, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "late one" } });
    state = reduce(state, { type: "prompt/start", turnId: "t2", content: [{ type: "text", text: "again" }], at });
    state = update(state, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "answer" } });
    state = reduce(state, { type: "prompt/end", stopReason: "end_turn", usage: null, at });
    state = update(state, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "late two" } });
    expect(state.turns.at(-1)?.parts).toEqual([
      { type: "text", text: "answer" },
      { type: "text", text: "late two" },
    ]);
  });

  it("does not open a turn for a subagent spawned behind prompt/end", () => {
    let state = started(connected());
    state = reduce(state, { type: "prompt/end", stopReason: "end_turn", usage: null, at });
    const before = state.turns.length;
    state = update(state, { sessionUpdate: "subagent_spawned", subagentSessionId: "kid", name: "explorer" });
    expect(state.turns).toHaveLength(before);
    expect(state.turns.at(-1)?.endedAt).not.toBeNull();
    expect(state.subagentSessionIds).toContain("kid");
  });

  it("gives a chunk behind a session's closed user turn a closed agent turn of its own", () => {
    let state = connected();
    state = reduce(state, { type: "prompt/start", turnId: "t1", content: [{ type: "text", text: "hi" }], at });
    state = { ...state, turns: state.turns.slice(0, 1) }; // the agent turn is gone: only the user's, closed
    state = update(state, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "late" } });
    expect(state.turns.map((turn) => turn.role)).toEqual(["user", "agent"]);
    expect(state.turns[1]?.endedAt).not.toBeNull();
  });
});

describe("reduce: a crash mid-turn", () => {
  it("puts the error in the turn it ended, whichever of the status and the rejection comes first", () => {
    let state = started(connected());
    state = update(state, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "working" } });
    state = reduce(state, { type: "status", status: "error", error: "adapter died", at });
    state = reduce(state, { type: "prompt/error", message: "adapter died", at });
    expect(state.turns.map((turn) => turn.role)).toEqual(["user", "agent"]);
    expect(state.turns.at(-1)?.parts.at(-1)).toEqual({ type: "error", message: "adapter died" });
    expect(state.turns.at(-1)?.endedAt).not.toBeNull();
    expect(state.status).toBe("error");
  });
});

describe("reduce: a settled call stays settled", () => {
  it("does not let a late in_progress bring a failed call back to life", () => {
    let state = started(connected());
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "r1", title: "sleep", kind: "execute", status: "in_progress" });
    state = reduce(state, { type: "prompt/error", message: "boom", at });
    expect(allToolCalls(state)[0]?.status).toBe("failed");
    state = update(state, { sessionUpdate: "tool_call_update", toolCallId: "r1", status: "in_progress" });
    expect(allToolCalls(state)[0]?.status).toBe("failed");
    // The agent saying how it ended still lands.
    state = update(state, { sessionUpdate: "tool_call_update", toolCallId: "r1", status: "completed" });
    expect(allToolCalls(state)[0]?.status).toBe("completed");
  });
});

describe("reduce: tool call updates across turns", () => {
  it("updates a closed turn's call in place instead of opening a phantom turn", () => {
    let state = started(connected());
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "bg", title: "sleep", kind: "execute", status: "in_progress" });
    state = reduce(state, { type: "prompt/end", stopReason: "end_turn", usage: null, at });
    state = update(state, { sessionUpdate: "tool_call_update", toolCallId: "bg", status: "completed" });
    expect(state.turns.map((turn) => turn.role)).toEqual(["user", "agent"]);
    expect(state.turns[1]?.endedAt).toBe(at);
    expect(allToolCalls(state)).toMatchObject([{ id: "bg", title: "sleep", status: "completed" }]);
    // An update for an id nobody announced, with no turn open, is dropped.
    state = update(state, { sessionUpdate: "tool_call_update", toolCallId: "ghost", status: "completed" });
    expect(state.turns).toHaveLength(2);
    expect(allToolCalls(state).map((call) => call.id)).toEqual(["bg"]);
  });

  it("updates a previous turn's call during the next turn rather than duplicating it", () => {
    let state = started(connected());
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "bg", title: "sleep", kind: "execute", status: "in_progress" });
    state = reduce(state, { type: "prompt/end", stopReason: "end_turn", usage: null, at });
    state = reduce(state, { type: "prompt/start", turnId: "t2", content: [{ type: "text", text: "next" }], at });
    state = update(state, { sessionUpdate: "tool_call_update", toolCallId: "bg", status: "completed" });
    expect(allToolCalls(state).map((call) => `${call.id}:${call.status}`)).toEqual(["bg:completed"]);
    expect(state.turns[3]?.parts).toEqual([]);
  });

  it("gives a fresh announcement of a reused id its own row in the open turn, and sends its updates there", () => {
    let state = started(connected());
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "write-1", title: "Write a", kind: "edit", status: "completed" });
    state = reduce(state, { type: "prompt/end", stopReason: "end_turn", usage: null, at });
    state = reduce(state, { type: "prompt/start", turnId: "t2", content: [{ type: "text", text: "again" }], at });
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "write-1", title: "Write b", kind: "edit", status: "in_progress" });
    state = update(state, { sessionUpdate: "tool_call_update", toolCallId: "write-1", status: "failed" });
    expect(allToolCalls(state).map((call) => `${call.title}:${call.status}`)).toEqual(["Write a:completed", "Write b:failed"]);
  });
});

describe("reduce: session ids", () => {
  it("does not let a subagent's session-level updates replace the root's", () => {
    const child = "child-session";
    let state = started(connected());
    state = update(state, { sessionUpdate: "subagent_spawned", subagentSessionId: child, name: "explorer" });
    state = update(state, { sessionUpdate: "usage_update", used: 10, size: 100 });
    state = update(state, { sessionUpdate: "session_info_update", title: "Root" });
    state = update(state, { sessionUpdate: "plan", entries: [{ content: "root", priority: "high", status: "pending" }] });
    state = update(state, { sessionUpdate: "usage_update", used: 99, size: 200 }, child);
    state = update(state, { sessionUpdate: "current_mode_update", currentModeId: "plan" }, child);
    state = update(state, { sessionUpdate: "session_info_update", title: "Child" }, child);
    state = update(state, { sessionUpdate: "available_commands_update", availableCommands: [{ name: "x", description: "" }] }, child);
    state = update(state, { sessionUpdate: "plan", entries: [{ content: "child", priority: "high", status: "pending" }] }, child);
    expect(state.contextUsage).toMatchObject({ used: 10, size: 100 });
    expect(state.currentModeId).toBe("default");
    expect(state.title).toBe("Root");
    expect(state.availableCommands).toEqual([]);
    expect(state.plan?.[0]?.content).toBe("root");
    const rootPlan = state.turns[1]?.parts.find((part) => part.type === "plan");
    expect(rootPlan).toMatchObject({ entries: [{ content: "root" }] });
    // The child's own plan lands inside its part.
    const sub = state.turns[1]?.parts.find((part) => part.type === "subagent");
    expect(sub?.type === "subagent" && sub.parts.map((part) => part.type)).toEqual(["plan"]);
  });

  it("parks an unknown child's updates until its spawn arrives, instead of gluing them onto the root", () => {
    const child = "late-child";
    let state = started(connected());
    state = update(state, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "root " } });
    state = update(state, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "child says" } }, child);
    expect(lastAgentText(state)).toBe("root ");
    state = update(state, { sessionUpdate: "subagent_spawned", subagentSessionId: child, name: "explorer" });
    const sub = state.turns[1]?.parts.find((part) => part.type === "subagent");
    expect(sub?.type === "subagent" && sub.parts).toEqual([{ type: "text", text: "child says" }]);
    expect(SessionStateSchema.safeParse(state).success).toBe(true);
  });

  it("keeps only a bounded number of parked updates", () => {
    let state = started(connected());
    for (let i = 0; i < 1000; i += 1) {
      state = update(state, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "x" } }, "never-spawned");
    }
    expect(JSON.stringify(state).length).toBeLessThan(50_000);
    expect(lastAgentText(state)).toBe("");
  });
});

describe("reduce: replayed user messages", () => {
  it("keeps two consecutive user messages apart by message id", () => {
    let state = reduce(initialSessionState("s1", "fake"), {
      type: "session/connected",
      acpSessionId: root,
      modes: null,
      configOptions: null,
      loading: true,
      at,
    });
    state = update(state, { sessionUpdate: "user_message_chunk", messageId: "m1", content: { type: "text", text: "A" } });
    state = update(state, { sessionUpdate: "user_message_chunk", messageId: "m1", content: { type: "text", text: "a" } });
    state = update(state, { sessionUpdate: "user_message_chunk", messageId: "m2", content: { type: "text", text: "B" } });
    state = reduce(state, { type: "session/loaded", at });
    const texts = state.turns.map((turn) => turn.parts.map((part) => ("text" in part ? part.text : "")).join("|"));
    expect(texts).toEqual(["Aa", "B"]);
    expect(SessionStateSchema.safeParse(state).success).toBe(true);
  });

  it("keeps separate blocks apart when the agent sends no message id", () => {
    let state = connected();
    state = update(state, { sessionUpdate: "user_message_chunk", content: { type: "text", text: "A" } });
    state = update(state, { sessionUpdate: "user_message_chunk", content: { type: "text", text: "B" } });
    expect(state.turns[0]?.parts).toEqual([
      { type: "text", text: "A" },
      { type: "text", text: "B" },
    ]);
  });
});

describe("reduce: permission/resolve status", () => {
  it("goes idle, not running, when the answer arrives after the turn ended", () => {
    let state = started(connected());
    state = reduce(state, {
      type: "permission/request",
      request: { requestId: "perm-1", acpSessionId: root, toolCallId: "c1", title: null, description: null, kind: null, input: null, options: [] },
      at,
    });
    // The turn closes without the connection's cleanup reaching the reducer first.
    state = { ...state, turns: state.turns.map((turn) => ({ ...turn, endedAt: turn.endedAt ?? at })) };
    state = reduce(state, { type: "permission/resolve", requestId: "perm-1", outcome: { state: "cancelled" }, at });
    expect(state.status).toBe("idle");
  });
});

describe("reduce: permission/resolve identity", () => {
  it("keeps every turn that does not hold the request", () => {
    let state = started(connected());
    state = reduce(state, { type: "prompt/end", stopReason: "end_turn", usage: null, at });
    state = started(state);
    state = reduce(state, {
      type: "permission/request",
      request: { requestId: "perm-1", acpSessionId: root, toolCallId: "c1", title: null, description: null, kind: null, input: null, options: [] },
      at,
    });
    const before = state.turns;
    const after = reduce(state, { type: "permission/resolve", requestId: "perm-1", outcome: { state: "cancelled" }, at }).turns;
    expect(after[0]).toBe(before[0]);
    expect(after.at(-1)).not.toBe(before.at(-1));
  });
});

describe("reduce: a permission request outside an open turn", () => {
  const late = { requestId: "perm-1", acpSessionId: root, toolCallId: "c1", title: null, description: null, kind: null, input: null, options: [] };

  it("does not open a turn, so the answer leaves the session idle", () => {
    let state = started(connected());
    state = reduce(state, { type: "prompt/end", stopReason: "end_turn", usage: null, at });
    const turns = state.turns.length;
    state = reduce(state, { type: "permission/request", request: late, at });
    expect(state.status).toBe("waiting");
    expect(state.turns).toHaveLength(turns);
    expect(state.turns.at(-1)?.parts.at(-1)).toMatchObject({ type: "permission_request", outcome: { state: "pending" } });
    state = reduce(state, { type: "permission/resolve", requestId: "perm-1", outcome: { state: "selected", optionId: "x" }, at });
    expect(state.status).toBe("idle");
    expect(state.turns.at(-1)?.endedAt).not.toBeNull();
  });

  it("gives a session with no turn at all a closed one to hold it", () => {
    const state = reduce(connected(), { type: "permission/request", request: late, at });
    expect(state.turns).toHaveLength(1);
    expect(state.turns[0]?.endedAt).not.toBeNull();
  });
});

describe("reduce: a permission card when the adapter goes away", () => {
  const ask = { requestId: "perm-1", acpSessionId: root, toolCallId: "c1", title: null, description: null, kind: null, input: null, options: [] };

  it("ends the open turn and settles its running work when the adapter closes mid-turn", () => {
    let state = started(connected());
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "r1", title: "sleep", kind: "execute", status: "in_progress" });
    state = update(state, { sessionUpdate: "subagent_spawned", subagentSessionId: "kid", name: "explorer" });
    state = reduce(state, { type: "status", status: "closed", error: null, at });
    expect(state.turns.at(-1)?.endedAt).not.toBeNull();
    expect(state.turns.at(-1)?.stopReason).toBe("cancelled");
    expect(allToolCalls(state)[0]?.status).toBe("cancelled");
    expect(state.turns.at(-1)?.parts.find((part) => part.type === "subagent")).toMatchObject({ state: "cancelled" });
  });

  it("fails the running work, and ends the turn, when the adapter errors mid-turn", () => {
    let state = started(connected());
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "r1", title: "sleep", kind: "execute", status: "in_progress" });
    state = reduce(state, { type: "status", status: "error", error: "adapter died", at });
    expect(state.turns.at(-1)?.endedAt).not.toBeNull();
    expect(allToolCalls(state)[0]?.status).toBe("failed");
    expect(state.error).toBe("adapter died");
  });

  it.each(["closed", "error"] as const)("marks a pending card cancelled on status %s", (status) => {
    let state = started(connected());
    state = reduce(state, { type: "permission/request", request: ask, at });
    state = reduce(state, { type: "status", status, error: null, at });
    expect(state.turns[1]?.parts.at(-1)).toMatchObject({ type: "permission_request", outcome: { state: "cancelled" } });
    expect(state.pendingPermissions).toEqual([]);
  });
});

describe("reduce: a turn that ends with a request unanswered", () => {
  const ask = { requestId: "perm-1", acpSessionId: root, toolCallId: "c1", title: null, description: null, kind: null, input: null, options: [] };

  it.each([
    ["prompt/error", { type: "prompt/error", message: "boom", at }],
    ["prompt/end end_turn", { type: "prompt/end", stopReason: "end_turn", usage: null, at }],
    ["prompt/end refusal", { type: "prompt/end", stopReason: "refusal", usage: null, at }],
  ] as const)("cancels the pending card on %s", (_name, end) => {
    let state = started(connected());
    state = reduce(state, { type: "permission/request", request: ask, at });
    state = reduce(state, end);
    const cards = state.turns.flatMap((turn) => turn.parts).filter((part) => part.type === "permission_request");
    expect(cards).toMatchObject([{ outcome: { state: "cancelled" } }]);
    expect(state.pendingPermissions).toEqual([]);
  });
});

describe("reduce: embedded resources", () => {
  const resource = { type: "resource" as const, uri: "attachment:///notes%20v2.md", text: "# notes", mimeType: "text/markdown" };

  it("keeps a prompt's embedded resource whole, text and all", () => {
    const state = reduce(connected(), { type: "prompt/start", turnId: "t1", content: [{ type: "text", text: "see" }, resource], at });
    expect(state.turns[0]?.parts).toEqual([
      { type: "text", text: "see" },
      { type: "resource", uri: resource.uri, name: "notes v2.md", text: "# notes", mimeType: "text/markdown" },
    ]);
    expect(SessionStateSchema.safeParse(state).success).toBe(true);
  });

  it("replays a user's embedded resource as a resource, not as text glued onto the prompt", () => {
    let state = connected();
    state = update(state, { sessionUpdate: "user_message_chunk", messageId: "m1", content: { type: "text", text: "see" } });
    state = update(state, {
      sessionUpdate: "user_message_chunk",
      messageId: "m1",
      content: { type: "resource", resource: { uri: resource.uri, text: "# notes", mimeType: "text/markdown" } },
    });
    expect(state.turns[0]?.parts).toEqual([
      { type: "text", text: "see" },
      { type: "resource", uri: resource.uri, name: "notes v2.md", text: "# notes", mimeType: "text/markdown" },
    ]);
  });
});

describe("reduce: streamed output", () => {
  it("keeps only the tail of a long stream and says it was cut", () => {
    let state = started(connected());
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "c1", title: "yes", kind: "execute", status: "in_progress" });
    const chunk = "y\n".repeat(4096);
    for (let i = 0; i < 40; i += 1) {
      state = update(state, { sessionUpdate: "tool_call_update", toolCallId: "c1", _meta: { terminal_output_delta: { data: chunk } } });
    }
    state = update(state, { sessionUpdate: "tool_call_update", toolCallId: "c1", _meta: { terminal_output_delta: { data: "END" } } });
    const [call] = allToolCalls(state);
    expect(call?.stream.length).toBeLessThanOrEqual(64 * 1024);
    expect(call?.stream.endsWith("END")).toBe(true);
    expect(call?.streamTruncated).toBe(true);
    expect(SessionStateSchema.safeParse(state).success).toBe(true);
  });
});

describe("reduce: a tool call id belongs to its session", () => {
  it("sends a subagent's update to its own row, not to a root row with the same id", () => {
    const child = "child-session";
    let state = started(connected());
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "c1", title: "root call", kind: "execute", status: "in_progress" });
    state = update(state, { sessionUpdate: "subagent_spawned", subagentSessionId: child, name: "explorer" });
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "c1", title: "child call", kind: "read", status: "in_progress" }, child);
    state = update(state, { sessionUpdate: "tool_call_update", toolCallId: "c1", status: "completed" }, child);
    expect(allToolCalls(state).map((call) => `${call.title}:${call.status}`)).toEqual(["root call:in_progress", "child call:completed"]);
  });

  it("merges an announcement with no turn open into its session's row, rather than opening a turn with a duplicate", () => {
    let state = started(connected());
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "c1", title: "old", kind: "execute", status: "in_progress" });
    state = reduce(state, { type: "prompt/end", stopReason: "end_turn", usage: null, at });
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "c1", title: "again", kind: "execute", status: "completed" });
    expect(state.turns).toHaveLength(2);
    expect(allToolCalls(state).map((call) => `${call.title}:${call.status}`)).toEqual(["again:completed"]);
    // An announcement for an id no row has rides on the last, closed turn: a new one nothing ends is worse.
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "c2", title: "new", kind: "execute", status: "in_progress" });
    expect(state.turns).toHaveLength(2);
    expect(state.turns.at(-1)?.endedAt).not.toBeNull();
    expect(allToolCalls(state).map((call) => call.id)).toEqual(["c1", "c2"]);
  });
});

describe("reduce: parked updates stay small and local", () => {
  const big = (n: number) => ({ sessionUpdate: "tool_call", toolCallId: `b${n}`, rawOutput: "x".repeat(10_000) });

  it("caps what is parked by bytes as well as by count, and says so once", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    let state = started(connected());
    for (let i = 0; i < 100; i += 1) {
      state = update(state, big(i), "never-spawned");
    }
    expect(JSON.stringify(state.parked ?? []).length).toBeLessThanOrEqual(256 * 1024 + 4096);
    expect(state.parked?.at(-1)?.update).toMatchObject({ toolCallId: "b99" });
    expect(warn).toHaveBeenCalledTimes(1);
    warn.mockRestore();
  });

  it("keeps the newest update even when it alone is over the byte cap", () => {
    let state = started(connected());
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "huge", rawOutput: "x".repeat(300_000) }, "late-child");
    expect(state.parked?.map((entry) => (entry.update as { toolCallId?: string }).toolCallId)).toEqual(["huge"]);
  });

  it("measures the cap in UTF-8 bytes, not UTF-16 units", () => {
    let state = started(connected());
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "ascii", rawOutput: "x".repeat(100_000) }, "late-child");
    // 100k two-byte characters: 200 KB on the wire, 100k units in a JS string.
    state = update(state, { sessionUpdate: "tool_call", toolCallId: "accents", rawOutput: "é".repeat(100_000) }, "late-child");
    expect(state.parked?.map((entry) => (entry.update as { toolCallId?: string }).toolCallId)).toEqual(["accents"]);
  });

  it("is not part of the state a snapshot or session.state carries", () => {
    let state = started(connected());
    state = update(state, { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "early" } }, "late-child");
    expect(state.parked).toHaveLength(1);
    const wire = SessionStateSchema.parse(state);
    expect(wire).not.toHaveProperty("parked");
    expect(JSON.parse(JSON.stringify(withoutParked(state)))).not.toHaveProperty("parked");
  });
});
