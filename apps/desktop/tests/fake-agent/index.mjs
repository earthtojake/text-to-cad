#!/usr/bin/env node
/**
 * A scripted ACP agent on stdio, built on the SDK's agent side, for the
 * connection tests and the Playwright e2e.
 *
 *   node tests/fake-agent/index.mjs                       the built-in script
 *   node tests/fake-agent/index.mjs --fixture <file.jsonl> replay a recording
 *   node tests/fake-agent/index.mjs --mode-option           modes as a `mode`
 *                                                          config option
 *
 * `--mode-option` is the second shape ACP allows for the same thing: the
 * session answers with **no** `modes` and a `mode`-category select config
 * option instead, switched by `session/set_config_option` — which is how the
 * app's one mode chip has to work for an adapter that sends it that way
 * (`src/shared/acp/options.ts`, `modeChoice`). Everything else is identical,
 * including which mode asks about what.
 *
 * The built-in script reacts to words in the prompt so a test can ask for
 * exactly the behaviour it is checking:
 *
 *   "permission"  ask session/request_permission before the tool call —
 *                 unless the session is in the full-access mode, which asks
 *                 about nothing, the way Claude's `Bypass permissions` and
 *                 Codex's `Full access` do
 *   "terminal"    create a terminal (`echo` + args), poll it, wait, release
 *   "read"        fs/read_text_file on the path after "read "
 *   "write"       fs/write_text_file "hello" to the path after "write "
 *   "open"        call the Hardcore MCP server's `open_file` on the path
 *                 after "open " — the server `session/new` carried in
 *                 `mcpServers`, spawned the way an adapter spawns it
 *   "mention"     reply with prose naming files — real and missing paths,
 *                 a CAD reference, one in backticks — for the transcript's
 *                 links
 *   "subagent"    the draft subagent_spawned / child update / state_update
 *   "context"     a usage_update carrying a category breakdown of the window
 *                 in `_meta.contextBreakdown` — the shape the context
 *                 popover reads. No shipping adapter sends one (Claude's
 *                 `usage_update` is used/size/cost, Codex's is used/size),
 *                 so this is the only place the categories exist
 *   "limits"      three usage_updates carrying `_meta._claude/rateLimit` —
 *                 the SDK's `rate_limit_event` as the Claude adapter
 *                 forwards it, one limit type per event, in the SDK's own
 *                 units (`utilization` 0…1, `resetsAt` epoch seconds) — so
 *                 the panel's plan rows have something to draw
 *   "thought"     an agent_thought_chunk first
 *   "slow"        wait until cancelled
 *   "crash"       exit(3) mid-turn
 *   "showcase"    a Codex-shaped turn for the session UI's e2e: thoughts,
 *                 reads, edits with diffs, a streamed command, a plan, a
 *                 permission request that waits for the answer, a subagent,
 *                 prose — with small delays so the streaming states can be
 *                 seen
 *   "skills"      call the Hardcore MCP server's `list_skills`, and
 *                 `read_skill` on the `cad` skill, and reply with what came
 *                 back — the universal path an agent with no skill-root
 *                 feature takes
 *   "which"       run `command -v cadgen` in a terminal, so a test can see
 *                 what a session's PATH resolves `cadgen` to
 *   "applied"     reply with what the client configured on this session and
 *                 in which order — `model,reasoning_effort,mode:auto` — plus
 *                 the mode it ended in, so a test can assert that a new
 *                 session applies the stored model before the effort (the
 *                 model decides which efforts exist) and lands in the mode
 *                 the new-session screen's chip was on
 *
 * and always ends with the text "ok" and `end_turn` (or `cancelled`).
 *
 * `FAKE_AGENT_REFUSE=<configId>` makes `session/set_config_option` throw for
 * that option, the way an adapter refuses a model an account cannot use.
 *
 * `FAKE_AGENT_RECORD=<file.jsonl>` appends one JSON line per session/new,
 * session/load and prompt — the params as they arrived, and the adapter's own
 * `PATH` — so a spec can assert what the client sent. Appended, not
 * overwritten: a suite runs several of these processes against one file.
 *
 * A cwd containing a `.fake-auth-required` file makes `session/new` answer
 * "Authentication required", the way an adapter whose CLI is signed out does.
 *
 * A fixture replays the agent→client frames of each recorded prompt turn in
 * order: notifications are re-sent (with the live session id), requests are
 * re-issued and awaited (terminal ids are mapped from the recorded response
 * to the live one), and the recorded prompt response is returned.
 */
import { appendFileSync, existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { Readable, Writable } from "node:stream";

import { AgentSideConnection, PROTOCOL_VERSION, RequestError, ndJsonStream } from "@agentclientprotocol/sdk";
import { Client as McpClient } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const args = process.argv.slice(2);
const recordFile = process.env.FAKE_AGENT_RECORD || null;

/** One line per client request worth asserting on. Best effort. */
function record(kind, params) {
  if (!recordFile) {
    return;
  }
  try {
    appendFileSync(recordFile, `${JSON.stringify({ kind, at: Date.now(), pid: process.pid, params })}\n`);
  } catch {
    /* a test's record file is not worth failing a turn over */
  }
}

const fixturePath = args.includes("--fixture") ? args[args.indexOf("--fixture") + 1] : null;
const fixture = fixturePath ? loadFixture(fixturePath) : null;
/** Codex's shape: no `modes`, a `mode` config option carrying the same list. */
const modeAsOption = args.includes("--mode-option");

const stream = ndJsonStream(Writable.toWeb(process.stdout), Readable.toWeb(process.stdin));

/**
 * The two config options the composer draws as dropdowns of its own: the
 * model, and the effort beside it (Codex's `reasoning_effort`, Claude's
 * `effort`). Kept as state so `session/set_config_option` answers with what
 * the session now is, which is what the agents do.
 */
const chosen = { model: "fast", reasoning_effort: "medium" };
/**
 * Which mode the session is in, and every configuration the client applied,
 * in order (`applied` above). A real session starts in the adapter's own
 * default and the client moves it to the auto preset; keeping both here is
 * what lets a test see that it did.
 */
let currentModeId = "default";
const applied = [];
const refuse = process.env.FAKE_AGENT_REFUSE || null;

/**
 * The session's modes, named the way Claude names its own. `auto` carries
 * ACP's `_meta.kind: auto_review`, which is how both real adapters name their
 * own auto-approval preset — and how the app finds it without knowing either
 * provider's id for it; `full` carries `full_access`, the one mode that asks
 * about nothing at all, and the one the menu says so under.
 */
function modeList() {
  return [
    { id: "default", name: "Manual", _meta: { kind: "standard" } },
    { id: "plan", name: "Plan", description: "Read only", _meta: { kind: "plan" } },
    { id: "auto", name: "Auto", description: "Answers its own permission requests", _meta: { kind: "auto_review" } },
    { id: "full", name: "Full access", description: "Never asks", _meta: { kind: "full_access" } },
  ];
}

/** The `mode` config option, for the `--mode-option` shape only. */
function modeConfigOption() {
  return {
    id: "mode",
    name: "Mode",
    description: "Approval and sandboxing preset for the session",
    category: "mode",
    type: "select",
    currentValue: currentModeId,
    options: modeList().map((mode) => ({
      value: mode.id,
      name: mode.name,
      description: mode.description,
      _meta: mode._meta,
    })),
  };
}

function configOptions() {
  return [
    ...(modeAsOption ? [modeConfigOption()] : []),
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
/** The MCP servers `session/new` named, so a prompt can call one (below). */
let mcpServers = [];

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
    record("session/new", { ...params, PATH: process.env.PATH ?? null });
    if (fixture?.newSession) {
      return fixture.newSession;
    }
    if (params?.cwd && existsSync(path.join(params.cwd, ".fake-auth-required"))) {
      throw RequestError.authRequired();
    }
    mcpServers = Array.isArray(params?.mcpServers) ? params.mcpServers : [];
    currentModeId = "default";
    applied.length = 0;
    return {
      sessionId: SESSION_ID,
      ...(modeAsOption ? {} : { modes: { currentModeId, availableModes: modeList() } }),
      configOptions: configOptions(),
    };
  },

  async loadSession(params) {
    record("session/load", params);
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
    return modeAsOption
      ? { configOptions: configOptions() }
      : { modes: { currentModeId, availableModes: modeList() } };
  },

  async setSessionMode(params) {
    currentModeId = params.modeId;
    applied.push(`mode:${params.modeId}`);
    await conn.sessionUpdate({
      sessionId: params.sessionId,
      update: { sessionUpdate: "current_mode_update", currentModeId },
    });
    return {};
  },

  async setSessionConfigOption(params) {
    if (refuse && params.configId === refuse) {
      throw RequestError.invalidParams(`${params.configId} is not available`);
    }
    applied.push(params.configId === "mode" ? `mode:${params.value}` : params.configId);
    if (params.configId in chosen) {
      chosen[params.configId] = String(params.value);
    }
    if (params.configId === "mode") {
      currentModeId = String(params.value);
    }
    // Both adapters also announce the new set on the session; the client
    // caches it against the agent, so the notification is part of the shape.
    await conn.sessionUpdate({
      sessionId: params.sessionId,
      update: { sessionUpdate: "config_option_update", configOptions: configOptions() },
    });
    return { configOptions: configOptions() };
  },

  async prompt(params) {
    record("prompt", params);
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
  // The LAST text block, not all of them joined: a session with an agent that
  // does not load skill roots carries Hardcore's preamble in front of the
  // person's first prompt, and its prose ("read the one that fits…") would
  // otherwise trigger half the keywords below.
  const text = params.prompt.filter((block) => block.type === "text").map((block) => block.text).at(-1) ?? "";
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

  if (text.includes("applied")) {
    await send({
      sessionUpdate: "agent_message_chunk",
      content: { type: "text", text: `applied: ${applied.join(",")} in ${currentModeId}` },
    });
    return { stopReason: "end_turn" };
  }

  if (text.includes("thought")) {
    await send({ sessionUpdate: "agent_thought_chunk", content: { type: "text", text: "thinking…" } });
  }

  if (text.includes("context")) {
    await send({
      sessionUpdate: "usage_update",
      used: 31_500,
      size: 258_400,
      _meta: {
        contextBreakdown: [
          { id: "system_prompt", name: "System prompt", tokens: 2_800 },
          { id: "system_tools", name: "System tools", tokens: 11_200 },
          { id: "mcp_tools", name: "MCP tools", tokens: 4_100 },
          { id: "memory_files", name: "Memory files", tokens: 1_900 },
          { id: "messages", name: "Messages", tokens: 11_500 },
        ],
      },
    });
  }

  if (text.includes("limits")) {
    // One event per limit type, the way the SDK sends them: the adapter
    // attaches the window it last saw to each. `resetsAt` is epoch seconds
    // and `utilization` a fraction — the units the renderer normalises.
    const seconds = Math.floor(Date.now() / 1000);
    for (const rateLimit of [
      { status: "allowed", rateLimitType: "five_hour", utilization: 0.17, resetsAt: seconds + 4 * 3600 + 300 },
      { status: "allowed", rateLimitType: "seven_day", utilization: 0.63, resetsAt: seconds + 3 * 86_400 },
      {
        status: "allowed_warning",
        rateLimitType: "seven_day_opus",
        utilization: 0.96,
        resetsAt: seconds + 3 * 86_400,
        isUsingOverage: true,
      },
    ]) {
      await send({ sessionUpdate: "usage_update", used: 292_300, size: 1_000_000, _meta: { "_claude/rateLimit": rateLimit } });
    }
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

  if (text.includes("mention")) {
    const prose =
      "Look at README.md and `apps/desktop/AGENTS.md`; the part is models/examples/imported/import-smoke.step#o1 " +
      "(nope/missing.md does not exist, and 0.5.0 is a version).\n";
    await send({ sessionUpdate: "agent_message_chunk", content: { type: "text", text: prose } });
  }

  if (text.includes("open")) {
    // The real thing, end to end: the stdio server Hardcore put in
    // `session/new`, spawned with the environment it gave (bridge URL, the
    // session's token and cwd), and its `open_file` tool called over MCP.
    const file = after("open");
    await send({ sessionUpdate: "tool_call", toolCallId: "open-1", title: `open_file ${file}`, kind: "other", status: "in_progress", rawInput: { path: file } });
    try {
      const result = await callHardcoreTool("open_file", { path: file });
      await send({ sessionUpdate: "tool_call_update", toolCallId: "open-1", status: result.isError ? "failed" : "completed", rawOutput: result });
    } catch (error) {
      await send({ sessionUpdate: "tool_call_update", toolCallId: "open-1", status: "failed", content: [{ type: "content", content: { type: "text", text: String(error.message ?? error) } }] });
    }
  }

  if (text.includes("skills")) {
    // The universal path: the skills the app put on disk, read through its own
    // MCP server rather than through any skill-root feature of the agent's.
    await send({ sessionUpdate: "tool_call", toolCallId: "skills-1", title: "list_skills", kind: "other", status: "in_progress" });
    try {
      const listed = await callHardcoreTool("list_skills", {});
      const read = await callHardcoreTool("read_skill", { name: "cad" });
      const answer = JSON.parse(listed.content[0].text);
      const names = answer.skills.map((skill) => skill.name);
      record("skills", { root: answer.root, names, cad: JSON.parse(read.content[0].text) });
      await send({ sessionUpdate: "tool_call_update", toolCallId: "skills-1", status: "completed", rawOutput: { names } });
      await send({
        sessionUpdate: "agent_message_chunk",
        content: {
          type: "text",
          text: `skills: ${names.join(",")} · cad starts ${JSON.parse(read.content[0].text).text.slice(0, 3)}`,
        },
      });
    } catch (error) {
      await send({ sessionUpdate: "tool_call_update", toolCallId: "skills-1", status: "failed", content: [{ type: "content", content: { type: "text", text: String(error.message ?? error) } }] });
    }
  }

  if (text.includes("which")) {
    // What this session's PATH resolves `cadgen` to. `sh -c`, not `-lc`: a
    // login shell would rebuild PATH from the person's dotfiles and answer a
    // different question.
    const { terminalId } = await conn.request("terminal/create", {
      sessionId,
      command: "sh",
      args: ["-c", "command -v cadgen || echo none"],
      outputByteLimit: 4096,
    });
    await conn.request("terminal/wait_for_exit", { sessionId, terminalId });
    const output = await conn.request("terminal/output", { sessionId, terminalId });
    await conn.request("terminal/release", { sessionId, terminalId });
    const resolved = String(output.output ?? "").trim();
    record("which", { cadgen: resolved, PATH: process.env.PATH ?? null });
    await send({ sessionUpdate: "agent_message_chunk", content: { type: "text", text: `cadgen: ${resolved}` } });
  }

  if (text.includes("permission")) {
    await send({ sessionUpdate: "tool_call", toolCallId: "cmd-1", title: "Run ls", kind: "execute", status: "pending", rawInput: { command: "ls" } });
    // Full access asks about nothing: the command just runs. This is the
    // whole point of the mode being the permission control — the app answers
    // no requests on anybody's behalf, so a mode that does not ask is the
    // only way nothing is asked.
    if (currentModeId === "full") {
      await send({ sessionUpdate: "tool_call_update", toolCallId: "cmd-1", status: "completed", rawOutput: { selected: "full-access" } });
      await send({ sessionUpdate: "agent_message_chunk", content: { type: "text", text: "ok" } });
      return { stopReason: "end_turn" };
    }
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
    // Both cache fields, the way Claude's adapter reports a turn: the
    // context popover has a row per field and leaves out the ones nobody
    // sent, so a fake that only ever sent two would only ever test two.
    usage: { totalTokens: 12, inputTokens: 10, outputTokens: 2, cachedReadTokens: 6, cachedWriteTokens: 4 },
  };
}

/** Spawn the `hardcore` MCP server from `session/new`, call one tool, and let it go. */
async function callHardcoreTool(name, args) {
  const server = mcpServers.find((candidate) => candidate.name === "hardcore") ?? mcpServers[0];
  if (!server) {
    throw new Error("session/new carried no MCP servers");
  }
  const env = { ...process.env };
  for (const entry of server.env ?? []) {
    env[entry.name] = entry.value;
  }
  const transport = new StdioClientTransport({ command: server.command, args: server.args ?? [], env });
  const client = new McpClient({ name: "fake-agent", version: "0.0.0" });
  await client.connect(transport);
  try {
    return await client.callTool({ name, arguments: args });
  } finally {
    await client.close().catch(() => {});
  }
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
