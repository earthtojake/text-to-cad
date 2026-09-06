#!/usr/bin/env node
/**
 * A scripted ACP agent on stdio, built on the SDK's agent side, for the
 * connection tests and the Playwright e2e.
 *
 *   node tests/fake-agent/index.mjs                       the built-in script
 *   node tests/fake-agent/index.mjs --fixture <file.jsonl> replay a recording
 *
 * The built-in script reacts to words in the prompt so a test can ask for
 * exactly the behaviour it is checking:
 *
 *   "permission"  ask session/request_permission before the tool call
 *   "terminal"    create a terminal (`echo` + args), poll it, wait, release
 *   "read"        fs/read_text_file on the path after "read "
 *   "write"       fs/write_text_file "hello" to the path after "write "
 *   "subagent"    the draft subagent_spawned / child update / state_update
 *   "thought"     an agent_thought_chunk first
 *   "slow"        wait until cancelled
 *   "crash"       exit(3) mid-turn
 *   "showcase"    a Codex-shaped turn for the session UI's e2e: thoughts,
 *                 reads, edits with diffs, a streamed command, a plan, a
 *                 permission request that waits for the answer, a subagent,
 *                 prose — with small delays so the streaming states can be
 *                 seen
 *
 * and always ends with the text "ok" and `end_turn` (or `cancelled`).
 *
 * A cwd containing a `.fake-auth-required` file makes `session/new` answer
 * "Authentication required", the way an adapter whose CLI is signed out does.
 *
 * A fixture replays the agent→client frames of each recorded prompt turn in
 * order: notifications are re-sent (with the live session id), requests are
 * re-issued and awaited (terminal ids are mapped from the recorded response
 * to the live one), and the recorded prompt response is returned.
 */
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { Readable, Writable } from "node:stream";

import { AgentSideConnection, PROTOCOL_VERSION, RequestError, ndJsonStream } from "@agentclientprotocol/sdk";

const args = process.argv.slice(2);
const fixturePath = args.includes("--fixture") ? args[args.indexOf("--fixture") + 1] : null;
const fixture = fixturePath ? loadFixture(fixturePath) : null;

const stream = ndJsonStream(Writable.toWeb(process.stdout), Readable.toWeb(process.stdin));

/**
 * The two config options the composer draws as dropdowns of its own: the
 * model, and the effort beside it (Codex's `reasoning_effort`, Claude's
 * `effort`). Kept as state so `session/set_config_option` answers with what
 * the session now is, which is what the agents do.
 */
const chosen = { model: "fast", reasoning_effort: "medium" };

function configOptions() {
  return [
    {
      id: "model",
      name: "Model",
      category: "model",
      type: "select",
      currentValue: chosen.model,
      options: [
        { value: "fast", name: "Fast" },
        { value: "smart", name: "Smart" },
      ],
    },
    {
      id: "reasoning_effort",
      name: "Effort",
      category: "thought_level",
      type: "select",
      currentValue: chosen.reasoning_effort,
      options: [
        { value: "low", name: "Low" },
        { value: "medium", name: "Medium" },
        { value: "high", name: "High" },
      ],
    },
  ];
}

let cancelled = false;
let cancelWaiter = null;

const SESSION_ID = fixture?.newSession?.sessionId ?? "fake-session-1";

new AgentSideConnection((conn) => ({
  async initialize() {
    if (fixture?.initialize) {
      return { ...fixture.initialize, protocolVersion: PROTOCOL_VERSION };
    }
    return {
      protocolVersion: PROTOCOL_VERSION,
      agentInfo: { name: "fake-agent", version: "0.0.0" },
      agentCapabilities: { loadSession: true, promptCapabilities: { image: true, embeddedContext: true } },
      authMethods: [],
    };
  },

  async authenticate() {
    return {};
  },

  async newSession(params) {
    if (fixture?.newSession) {
      return fixture.newSession;
    }
    if (params?.cwd && existsSync(path.join(params.cwd, ".fake-auth-required"))) {
      throw RequestError.authRequired();
    }
    return {
      sessionId: SESSION_ID,
      modes: {
        currentModeId: "default",
        availableModes: [
          { id: "default", name: "Default" },
          { id: "plan", name: "Plan", description: "Read only" },
        ],
      },
      configOptions: configOptions(),
    };
  },

  async loadSession(params) {
    if (fixture?.load) {
      await replay(conn, fixture.load.frames, params.sessionId);
      return fixture.load.response ?? {};
    }
    await conn.sessionUpdate({
      sessionId: params.sessionId,
      update: { sessionUpdate: "user_message_chunk", content: { type: "text", text: "earlier prompt" } },
    });
    await conn.sessionUpdate({
      sessionId: params.sessionId,
      update: { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "earlier reply" } },
    });
    return { modes: { currentModeId: "default", availableModes: [{ id: "default", name: "Default" }] } };
  },

  async setSessionMode(params) {
    await conn.sessionUpdate({
      sessionId: params.sessionId,
      update: { sessionUpdate: "current_mode_update", currentModeId: params.modeId },
    });
    return {};
  },

  async setSessionConfigOption(params) {
    if (params.configId in chosen) {
      chosen[params.configId] = String(params.value);
    }
    return { configOptions: configOptions() };
  },

  async prompt(params) {
    cancelled = false;
    if (fixture) {
      const turn = fixture.turns.shift();
      if (!turn) {
        return { stopReason: "end_turn" };
      }
      await replay(conn, turn.frames, params.sessionId);
      return turn.response ?? { stopReason: "end_turn" };
    }
    return script(conn, params);
  },

  async cancel() {
    cancelled = true;
    cancelWaiter?.();
  },
}), stream);

/* -------------------------------------------------------------------------- */
/* The built-in script                                                        */
/* -------------------------------------------------------------------------- */

async function script(conn, params) {
  const sessionId = params.sessionId;
  const text = params.prompt
    .filter((block) => block.type === "text")
    .map((block) => block.text)
    .join("\n");
  const words = text.split(/\s+/);
  const after = (word) => words[words.indexOf(word) + 1];
  const send = (update) => conn.sessionUpdate({ sessionId, update });

  if (text.includes("crash")) {
    await send({ sessionUpdate: "agent_message_chunk", content: { type: "text", text: "about to " } });
    process.exit(3);
  }

  if (text.includes("showcase")) {
    return showcase(conn, sessionId);
  }

  if (text.includes("thought")) {
    await send({ sessionUpdate: "agent_thought_chunk", content: { type: "text", text: "thinking…" } });
  }

  if (text.includes("slow")) {
    await send({ sessionUpdate: "agent_message_chunk", content: { type: "text", text: "working" } });
    await new Promise((resolve) => {
      cancelWaiter = resolve;
      setTimeout(resolve, 30_000);
    });
    return { stopReason: cancelled ? "cancelled" : "end_turn" };
  }

  if (text.includes("read")) {
    const file = after("read");
    await send({ sessionUpdate: "tool_call", toolCallId: "read-1", title: `Read ${file}`, kind: "read", status: "in_progress", locations: [{ path: file }] });
    const { content } = await conn.readTextFile({ sessionId, path: file });
    await send({ sessionUpdate: "tool_call_update", toolCallId: "read-1", status: "completed", content: [{ type: "content", content: { type: "text", text: content } }] });
  }

  if (text.includes("write")) {
    const file = after("write");
    await send({ sessionUpdate: "tool_call", toolCallId: "write-1", title: `Write ${file}`, kind: "edit", status: "in_progress", locations: [{ path: file }] });
    try {
      await conn.writeTextFile({ sessionId, path: file, content: "hello\n" });
      await send({ sessionUpdate: "tool_call_update", toolCallId: "write-1", status: "completed", content: [{ type: "diff", path: file, oldText: null, newText: "hello\n" }] });
    } catch (error) {
      await send({ sessionUpdate: "tool_call_update", toolCallId: "write-1", status: "failed", content: [{ type: "content", content: { type: "text", text: String(error.message ?? error) } }] });
    }
  }

  if (text.includes("permission")) {
    await send({ sessionUpdate: "tool_call", toolCallId: "cmd-1", title: "Run ls", kind: "execute", status: "pending", rawInput: { command: "ls" } });
    const answer = await conn.requestPermission({
      sessionId,
      toolCall: { toolCallId: "cmd-1", title: "Run ls", kind: "execute", status: "pending", rawInput: { command: "ls" } },
      options: [
        { optionId: "allow-once", name: "Yes", kind: "allow_once" },
        { optionId: "allow-always", name: "Yes, always", kind: "allow_always" },
        { optionId: "reject", name: "No", kind: "reject_once" },
      ],
      _meta: { permission: { version: 1, title: "Run ls?", description: "Lists the directory." } },
    });
    const selected = answer.outcome.outcome === "selected" ? answer.outcome.optionId : null;
    if (selected === null || selected === "reject") {
      await send({ sessionUpdate: "tool_call_update", toolCallId: "cmd-1", status: "failed", rawOutput: { rejected: true } });
      await send({ sessionUpdate: "agent_message_chunk", content: { type: "text", text: "denied" } });
      return { stopReason: answer.outcome.outcome === "cancelled" ? "cancelled" : "end_turn" };
    }
    await send({ sessionUpdate: "tool_call_update", toolCallId: "cmd-1", status: "completed", rawOutput: { selected } });
  }

  if (text.includes("terminal")) {
    // `conn.createTerminal` answers with the SDK's TerminalHandle; the raw
    // request keeps the fake close to the wire.
    const { terminalId } = await conn.request("terminal/create", { sessionId, command: "echo", args: ["from", "the", "terminal"], outputByteLimit: 4096 });
    await send({ sessionUpdate: "tool_call", toolCallId: "term-1", title: "echo from the terminal", kind: "execute", status: "in_progress", content: [{ type: "terminal", terminalId }] });
    await conn.request("terminal/wait_for_exit", { sessionId, terminalId });
    const output = await conn.request("terminal/output", { sessionId, terminalId });
    await conn.request("terminal/release", { sessionId, terminalId });
    await send({ sessionUpdate: "tool_call_update", toolCallId: "term-1", status: "completed", rawOutput: output });
  }

  if (text.includes("subagent")) {
    const childId = `${sessionId}:child-1`;
    await send({ sessionUpdate: "tool_call", toolCallId: "task-1", title: "Task: explore", kind: "think", status: "in_progress" });
    await send({ sessionUpdate: "subagent_spawned", subagentSessionId: childId, name: "explorer", task: "look around", parentToolCallId: "task-1", capabilities: {} });
    await conn.sessionUpdate({ sessionId: childId, update: { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "child says hi" } } });
    await conn.sessionUpdate({ sessionId: childId, update: { sessionUpdate: "tool_call", toolCallId: "child-read-1", title: "Read README", kind: "read", status: "completed" } });
    await send({ sessionUpdate: "subagent_state_update", subagentSessionId: childId, state: "completed" });
    await send({ sessionUpdate: "tool_call_update", toolCallId: "task-1", status: "completed" });
  }

  if (text.includes("plan")) {
    await send({ sessionUpdate: "plan", entries: [{ content: "first", priority: "high", status: "in_progress" }, { content: "second", priority: "low", status: "pending" }] });
  }

  await send({ sessionUpdate: "agent_message_chunk", content: { type: "text", text: "o" } });
  await send({ sessionUpdate: "agent_message_chunk", content: { type: "text", text: "k" } });
  return {
    stopReason: cancelled ? "cancelled" : "end_turn",
    usage: { totalTokens: 12, inputTokens: 10, outputTokens: 2 },
  };
}

/* -------------------------------------------------------------------------- */
/* The showcase turn                                                          */
/* -------------------------------------------------------------------------- */

const pause = (ms) =>
  new Promise((resolve) => {
    setTimeout(resolve, ms);
  });

/** A turn shaped like a real Codex turn, paced so each state is visible. */
async function showcase(conn, sessionId) {
  const send = (update) => conn.sessionUpdate({ sessionId, update });
  const text = (chunk) => send({ sessionUpdate: "agent_message_chunk", content: { type: "text", text: chunk } });
  const thought = (chunk) => send({ sessionUpdate: "agent_thought_chunk", content: { type: "text", text: chunk } });
  const STEP = 120;

  for (const chunk of ["The user wants a greeting script. ", "I should look at what is here, ", "then write it and check the directory."]) {
    await thought(chunk);
    await pause(STEP);
  }

  await send({
    sessionUpdate: "plan",
    entries: [
      { content: "Read the project notes", priority: "medium", status: "in_progress" },
      { content: "Write hello.py and update the README", priority: "high", status: "pending" },
      { content: "Run it and tidy up", priority: "low", status: "pending" },
    ],
  });

  await text("I'll look at the notes first, then write the script.\n\n");
  await pause(STEP);

  await send({ sessionUpdate: "tool_call", toolCallId: "sc-read-1", title: "Read README.md", kind: "read", status: "in_progress", locations: [{ path: "README.md" }] });
  await pause(STEP * 2);
  await send({ sessionUpdate: "tool_call_update", toolCallId: "sc-read-1", status: "completed", content: [{ type: "content", content: { type: "text", text: "# Scratch\n\nA place to try things.\n" } }] });
  await send({ sessionUpdate: "tool_call", toolCallId: "sc-read-2", title: "Read notes.md", kind: "read", status: "completed", locations: [{ path: "docs/notes.md" }] });
  await pause(STEP);

  await send({
    sessionUpdate: "plan",
    entries: [
      { content: "Read the project notes", priority: "medium", status: "completed" },
      { content: "Write hello.py and update the README", priority: "high", status: "in_progress" },
      { content: "Run it and tidy up", priority: "low", status: "pending" },
    ],
  });

  await send({ sessionUpdate: "tool_call", toolCallId: "sc-edit-1", title: "Write hello.py", kind: "edit", status: "in_progress", locations: [{ path: "hello.py" }] });
  await pause(STEP * 2);
  await send({
    sessionUpdate: "tool_call_update",
    toolCallId: "sc-edit-1",
    status: "completed",
    content: [{ type: "diff", path: "hello.py", oldText: null, newText: 'def main():\n    print("hello from the fake agent")\n\n\nif __name__ == "__main__":\n    main()\n' }],
  });
  await send({ sessionUpdate: "tool_call", toolCallId: "sc-edit-2", title: "Edit README.md", kind: "edit", status: "in_progress", locations: [{ path: "README.md" }] });
  await pause(STEP);
  await send({
    sessionUpdate: "tool_call_update",
    toolCallId: "sc-edit-2",
    status: "completed",
    content: [{ type: "diff", path: "README.md", oldText: "# Scratch\n\nA place to try things.\n", newText: "# Scratch\n\nA place to try things.\n\nRun `python hello.py` for a greeting.\n" }],
  });

  await send({ sessionUpdate: "tool_call", toolCallId: "sc-exec-1", title: "python hello.py", kind: "execute", status: "in_progress", rawInput: { command: "python hello.py" } });
  await pause(STEP);
  await send({ sessionUpdate: "tool_call_update", toolCallId: "sc-exec-1", _meta: { terminal_output_delta: { data: "hello from the fake agent\n" } } });
  await pause(STEP);
  await send({ sessionUpdate: "tool_call_update", toolCallId: "sc-exec-1", status: "completed", rawOutput: { formatted_output: "hello from the fake agent\n", exit_code: 0 } });
  await send({ sessionUpdate: "tool_call", toolCallId: "sc-exec-2", title: "ls -la", kind: "execute", status: "completed", rawInput: { command: "ls -la" }, rawOutput: { formatted_output: "total 16\n-rw-r--r--  1 user  staff   61 hello.py\n-rw-r--r--  1 user  staff   72 README.md\n", exit_code: 0 } });
  await pause(STEP);

  await text("The script runs. There is a stale `build/` directory here — removing it needs your say-so.\n\n");
  await send({ sessionUpdate: "tool_call", toolCallId: "sc-rm-1", title: "rm -rf build", kind: "delete", status: "pending", rawInput: { command: "rm -rf build" } });
  const answer = await conn.requestPermission({
    sessionId,
    toolCall: { toolCallId: "sc-rm-1", title: "rm -rf build", kind: "delete", status: "pending", rawInput: { command: "rm -rf build" } },
    options: [
      { optionId: "allow-once", name: "Yes", kind: "allow_once" },
      { optionId: "allow-always", name: "Yes, always", kind: "allow_always" },
      { optionId: "reject", name: "No", kind: "reject_once" },
    ],
    _meta: { permission: { version: 1, title: "Delete the build directory?", description: "Runs `rm -rf build` in the project. This cannot be undone." } },
  });
  const selected = answer.outcome.outcome === "selected" ? answer.outcome.optionId : null;
  if (selected === null || selected === "reject") {
    await send({ sessionUpdate: "tool_call_update", toolCallId: "sc-rm-1", status: "failed", rawOutput: { rejected: true } });
    await text("Understood — I left `build/` alone.");
    return { stopReason: answer.outcome.outcome === "cancelled" ? "cancelled" : "end_turn" };
  }
  await send({ sessionUpdate: "tool_call_update", toolCallId: "sc-rm-1", status: "completed", rawOutput: { removed: "build" } });
  await pause(STEP);

  const childId = `${sessionId}:child-showcase`;
  await send({ sessionUpdate: "tool_call", toolCallId: "sc-task-1", title: "Task: check the docs", kind: "think", status: "in_progress" });
  await send({ sessionUpdate: "subagent_spawned", subagentSessionId: childId, name: "Docs checker", task: "confirm the README mentions the script", parentToolCallId: "sc-task-1", capabilities: {} });
  await conn.sessionUpdate({ sessionId: childId, update: { sessionUpdate: "tool_call", toolCallId: "sc-child-read", title: "Read README.md", kind: "read", status: "completed", locations: [{ path: "README.md" }] } });
  await conn.sessionUpdate({ sessionId: childId, update: { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "The README now documents `python hello.py`." } } });
  await pause(STEP * 2);
  await send({ sessionUpdate: "subagent_state_update", subagentSessionId: childId, state: "completed" });
  await send({ sessionUpdate: "tool_call_update", toolCallId: "sc-task-1", status: "completed" });

  await send({
    sessionUpdate: "plan",
    entries: [
      { content: "Read the project notes", priority: "medium", status: "completed" },
      { content: "Write hello.py and update the README", priority: "high", status: "completed" },
      { content: "Run it and tidy up", priority: "low", status: "completed" },
    ],
  });
  await send({ sessionUpdate: "usage_update", used: 18_420, size: 258_400 });

  for (const chunk of ["Done. ", "`hello.py` prints a greeting, ", "the README says how to run it, ", "and the stale build directory is gone."]) {
    await text(chunk);
    await pause(STEP);
  }
  return {
    stopReason: cancelled ? "cancelled" : "end_turn",
    usage: { totalTokens: 18_420, inputTokens: 17_900, outputTokens: 520, cachedReadTokens: 12_000 },
  };
}

/* -------------------------------------------------------------------------- */
/* Fixture replay                                                              */
/* -------------------------------------------------------------------------- */

function loadFixture(file) {
  const frames = readFileSync(file, "utf8")
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line));
  const responseTo = (id) =>
    frames.find((frame) => frame.dir === "in" && frame.msg.id === id && !("method" in frame.msg))?.msg;
  const requestOut = (method) => frames.find((frame) => frame.dir === "out" && frame.msg.method === method)?.msg;

  const initialize = responseTo(requestOut("initialize")?.id)?.result ?? null;
  const newSession = responseTo(requestOut("session/new")?.id)?.result ?? null;

  const turns = [];
  let load = null;
  frames.forEach((frame, index) => {
    if (frame.dir !== "out" || !frame.msg.method) {
      return;
    }
    if (frame.msg.method !== "session/prompt" && frame.msg.method !== "session/load") {
      return;
    }
    const id = frame.msg.id;
    const collected = [];
    let response = null;
    for (let i = index + 1; i < frames.length; i += 1) {
      const candidate = frames[i];
      if (candidate.dir === "in" && candidate.msg.id === id && !("method" in candidate.msg)) {
        response = candidate.msg.result ?? null;
        break;
      }
      if (candidate.dir === "in" && candidate.msg.method) {
        // A request carries the client's recorded answer along, so replay
        // can map ids the client minted (terminals) onto the live ones.
        const recordedResponse =
          "id" in candidate.msg
            ? (frames
                .slice(i + 1)
                .find((f) => f.dir === "out" && f.msg.id === candidate.msg.id && !("method" in f.msg))
                ?.msg?.result ?? null)
            : null;
        collected.push({ ...candidate.msg, recordedResponse });
      }
    }
    if (frame.msg.method === "session/load") {
      load = { frames: collected, response };
    } else {
      turns.push({ frames: collected, response });
    }
  });
  return { initialize, newSession, turns, load };
}

async function replay(conn, frames, liveSessionId) {
  const terminalIds = new Map();
  const rootRecorded = frames.find((msg) => msg.params?.sessionId)?.params?.sessionId;
  const mapSession = (id) => (id === rootRecorded ? liveSessionId : id);
  for (const { recordedResponse, ...msg } of frames) {
    const params = { ...(msg.params ?? {}) };
    if (typeof params.sessionId === "string") {
      params.sessionId = mapSession(params.sessionId);
    }
    if (typeof params.terminalId === "string" && terminalIds.has(params.terminalId)) {
      params.terminalId = terminalIds.get(params.terminalId);
    }
    if (!("id" in msg)) {
      // A notification (session/update or an extension).
      if (msg.method === "session/update") {
        await conn.sessionUpdate(params);
      } else {
        await conn.notify(msg.method, params);
      }
      continue;
    }
    try {
      const result = await conn.request(msg.method, params);
      if (msg.method === "terminal/create" && result?.terminalId && recordedResponse?.terminalId) {
        terminalIds.set(recordedResponse.terminalId, result.terminalId);
      }
    } catch (error) {
      process.stderr.write(`[fake-agent] ${msg.method} failed: ${error.message ?? error}\n`);
    }
  }
}
