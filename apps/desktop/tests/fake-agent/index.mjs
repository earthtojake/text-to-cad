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
 *
 * and always ends with the text "ok" and `end_turn` (or `cancelled`).
 *
 * A fixture replays the agent→client frames of each recorded prompt turn in
 * order: notifications are re-sent (with the live session id), requests are
 * re-issued and awaited (terminal ids are mapped from the recorded response
 * to the live one), and the recorded prompt response is returned.
 */
import { readFileSync } from "node:fs";
import { Readable, Writable } from "node:stream";

import { AgentSideConnection, PROTOCOL_VERSION, ndJsonStream } from "@agentclientprotocol/sdk";

const args = process.argv.slice(2);
const fixturePath = args.includes("--fixture") ? args[args.indexOf("--fixture") + 1] : null;
const fixture = fixturePath ? loadFixture(fixturePath) : null;

const stream = ndJsonStream(Writable.toWeb(process.stdout), Readable.toWeb(process.stdin));

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

  async newSession() {
    if (fixture?.newSession) {
      return fixture.newSession;
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
      configOptions: [
        {
          id: "model",
          name: "Model",
          category: "model",
          type: "select",
          currentValue: "fast",
          options: [
            { value: "fast", name: "Fast" },
            { value: "smart", name: "Smart" },
          ],
        },
      ],
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
    return {
      configOptions: [
        {
          id: "model",
          name: "Model",
          category: "model",
          type: "select",
          currentValue: String(params.value),
          options: [
            { value: "fast", name: "Fast" },
            { value: "smart", name: "Smart" },
          ],
        },
      ],
    };
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
