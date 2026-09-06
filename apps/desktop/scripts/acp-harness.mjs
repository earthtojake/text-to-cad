#!/usr/bin/env node
/**
 * Run a real ACP session from the terminal, through the app's own
 * `SessionConnection` (src/main/acp) — the same code main runs, minus
 * Electron and node-pty (terminals use the child_process backend).
 *
 *   node scripts/acp-harness.mjs <agentId> <cwd> "<prompt>" ["<prompt>"...]
 *       [--record tests/fixtures/acp/<name>.jsonl]   write every wire frame
 *       [--approval ask|approve-for-me]              default approve-for-me
 *       [--load <acpSessionId>]                      session/load instead of session/new
 *       [--json]                                     print raw updates as JSON
 *
 * Prints every session update as it arrives, the permission requests it
 * auto-answers, terminal output, and a summary of the reduced SessionState
 * at the end. With `--approval ask` a permission request is answered from
 * stdin (type the option id).
 *
 * The TypeScript sources are loaded through Vite's SSR module loader so the
 * harness needs no build step and no extra dependency.
 */
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";

import { createServer } from "vite";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function usage(message) {
  if (message) {
    console.error(message);
  }
  console.error(
    'usage: acp-harness.mjs <agentId> <cwd> "<prompt>" [...] [--record file] [--approval ask|approve-for-me] [--load id] [--json]',
  );
  process.exit(2);
}

const positional = [];
const flags = { record: null, approval: "approve-for-me", load: null, json: false };
for (let i = 2; i < process.argv.length; i += 1) {
  const arg = process.argv[i];
  if (arg === "--record") {
    flags.record = process.argv[++i];
  } else if (arg === "--approval") {
    flags.approval = process.argv[++i];
  } else if (arg === "--load") {
    flags.load = process.argv[++i];
  } else if (arg === "--json") {
    flags.json = true;
  } else if (arg.startsWith("--")) {
    usage(`unknown flag ${arg}`);
  } else {
    positional.push(arg);
  }
}
const [agentId, cwdArg, ...prompts] = positional;
if (!agentId || !cwdArg || (prompts.length === 0 && !flags.load)) {
  usage();
}
if (flags.approval !== "ask" && flags.approval !== "approve-for-me") {
  usage("--approval must be ask or approve-for-me");
}
const cwd = path.resolve(cwdArg);

/** The live connection; set before the first event can arrive. */
let connection = null;

const server = await createServer({
  configFile: false,
  root: appRoot,
  logLevel: "error",
  appType: "custom",
  resolve: {
    alias: {
      "@main": path.join(appRoot, "src", "main"),
      "@shared": path.join(appRoot, "src", "shared"),
    },
  },
  server: { middlewareMode: true, hmr: false, watch: null },
  optimizeDeps: { noDiscovery: true, include: [] },
});

try {
  const acp = await server.ssrLoadModule("/src/main/acp/index.ts");
  const agents = await server.ssrLoadModule("/src/main/agents/index.ts");
  const reduce = await server.ssrLoadModule("/src/shared/acp/reduce.ts");

  const provider = agents.agentProvider(agentId);
  if (!provider) {
    usage(`unknown agent ${agentId}; known: ${agents.AGENT_PROVIDERS.map((p) => p.id).join(", ")}`);
  }

  console.log(`[harness] resolving login shell environment`);
  const env = await agents.loginEnv();
  console.log(`[harness] PATH has ${env.PATH.split(path.delimiter).length} entries`);
  console.log(`[harness] launching ${provider.launch.command} ${provider.launch.args.join(" ")} in ${cwd}`);

  if (flags.record) {
    mkdirSync(path.dirname(flags.record), { recursive: true });
    writeFileSync(flags.record, "");
  }

  const rl = flags.approval === "ask" ? readline.createInterface({ input: process.stdin }) : null;
  const askLine = (question) =>
    new Promise((resolve) => {
      rl.question(question, resolve);
    });

  connection = new acp.SessionConnection({
    sessionId: "harness",
    agentId,
    launch: provider.launch,
    env,
    cwd,
    spawnTerminal: acp.spawnProcessTerminal,
    approvalMode: flags.approval,
    clientVersion: "harness",
    onStderr: (line) => console.error(`[${agentId} stderr] ${line}`),
    onTerminalOutput: (terminalId, data, exit) => {
      if (data) {
        process.stdout.write(`[terminal ${terminalId.slice(0, 8)}] ${data}`);
      }
      if (exit) {
        console.log(`[terminal ${terminalId.slice(0, 8)}] exit ${exit.exitCode ?? exit.signal}`);
      }
    },
    onFilesChanged: (paths) => console.log(`[files changed] ${paths.join(", ")}`),
    record: flags.record
      ? (frame) => appendFileSync(flags.record, `${JSON.stringify(frame)}\n`)
      : undefined,
    onEvent: (event) => {
      printEvent(event);
      if (event.type === "permission/request" && flags.approval === "ask") {
        const { request } = event;
        const options = request.options.map((o) => `${o.optionId} (${o.kind}: ${o.name})`).join("\n    ");
        void askLine(`  answer [${request.options.map((o) => o.optionId).join("|")}|cancel]:\n    ${options}\n  > `).then(
          (answer) => {
            connection.respondPermission(request.requestId, answer.trim() === "cancel" ? null : answer.trim());
          },
        );
      }
    },
  });

  const init = await connection.initialize();
  console.log(`[initialize] agent ${init.agentInfo?.name ?? "?"} ${init.agentInfo?.version ?? ""} protocol ${init.protocolVersion}`);
  console.log(`[initialize] capabilities ${JSON.stringify(init.agentCapabilities)}`);
  console.log(`[initialize] authMethods ${JSON.stringify(init.authMethods)}`);
  if (init._meta) {
    console.log(`[initialize] _meta ${JSON.stringify(init._meta)}`);
  }

  if (flags.load) {
    console.log(`[session/load] ${flags.load}`);
    const loaded = await connection.loadSession(flags.load);
    console.log(`[session/load] done modes=${JSON.stringify(loaded.modes)} configOptions=${JSON.stringify(loaded.configOptions)}`);
  } else {
    const created = await connection.newSession();
    console.log(`[session/new] ${created.sessionId}`);
    console.log(`[session/new] modes ${JSON.stringify(created.modes)}`);
    console.log(`[session/new] configOptions ${JSON.stringify(created.configOptions)}`);
  }

  for (const prompt of prompts) {
    console.log(`\n[prompt] ${prompt}`);
    const response = await connection.prompt([{ type: "text", text: prompt }]);
    console.log(`[prompt] stopReason=${response.stopReason} usage=${JSON.stringify(response.usage ?? null)}`);
  }

  const state = connection.state;
  console.log(`\n[state] status=${state.status} acpSessionId=${state.acpSessionId} mode=${state.currentModeId}`);
  console.log(`[state] modes=${state.modes.map((m) => m.id).join(",")} configOptions=${state.configOptions.map((c) => `${c.id}=${c.currentValue}`).join(",")}`);
  console.log(`[state] commands=${state.availableCommands.length} subagents=${state.subagentSessionIds.length}`);
  for (const turn of state.turns) {
    console.log(`[state] turn ${turn.id} ${turn.role} parts=${turn.parts.map(describePart).join(" | ")}`);
  }
  console.log(`[state] last text: ${JSON.stringify(reduce.lastAgentText(state))}`);
  console.log(`[state] tool calls: ${reduce.allToolCalls(state).map((t) => `${t.kind}:${t.title}:${t.status}`).join(", ")}`);

  rl?.close();
  connection.close();
  await connection.exited;
} finally {
  await server.close();
}

function describePart(part) {
  switch (part.type) {
    case "text":
    case "thought":
      return `${part.type}(${part.text.length})`;
    case "tool_call":
      return `tool_call[${part.kind}:${part.title}:${part.status}${part.content.length ? ` ${part.content.map((c) => c.type).join("+")}` : ""}${part.children.length ? ` children=${part.children.length}` : ""}]`;
    case "subagent":
      return `subagent[${part.name}:${part.state} parts=${part.parts.length}]`;
    case "permission_request":
      return `permission[${part.outcome.state}]`;
    case "plan":
      return `plan(${part.entries.length})`;
    default:
      return part.type;
  }
}

function printEvent(event) {
  if (event.type !== "session/update") {
    if (event.type === "permission/request") {
      const { request } = event;
      console.log(`[permission] ${request.requestId} ${request.kind ?? ""} ${request.title ?? ""} options=${request.options.map((o) => `${o.optionId}/${o.kind}`).join(",")}`);
    } else if (event.type === "permission/resolve") {
      console.log(`[permission] ${event.requestId} -> ${JSON.stringify(event.outcome)}`);
    } else if (event.type === "status") {
      console.log(`[status] ${event.status}${event.error ? ` ${event.error}` : ""}`);
    }
    return;
  }
  const u = event.update;
  const root = connection?.state.acpSessionId;
  const child = root && event.acpSessionId !== root ? ` (${event.acpSessionId.slice(0, 8)})` : "";
  if (flags.json) {
    console.log(`[update${child}] ${JSON.stringify(u)}`);
    return;
  }
  switch (u.sessionUpdate) {
    case "agent_message_chunk":
    case "agent_thought_chunk":
    case "user_message_chunk": {
      const text = u.content?.type === "text" ? u.content.text : `<${u.content?.type}>`;
      console.log(`[${u.sessionUpdate}${child}] ${JSON.stringify(text)}`);
      break;
    }
    case "tool_call":
    case "tool_call_update":
      console.log(
        `[${u.sessionUpdate}${child}] ${u.toolCallId} kind=${u.kind ?? "-"} status=${u.status ?? "-"} title=${JSON.stringify(u.title ?? null)} name=${u.name ?? "-"} content=${(u.content ?? []).map((c) => c.type).join("+") || "-"} locations=${(u.locations ?? []).map((l) => l.path).join(",") || "-"}${u._meta ? ` _meta=${JSON.stringify(u._meta)}` : ""}`,
      );
      if (u.rawInput !== undefined) {
        console.log(`    rawInput=${JSON.stringify(u.rawInput).slice(0, 300)}`);
      }
      break;
    default:
      console.log(`[${u.sessionUpdate}${child}] ${JSON.stringify({ ...u, sessionUpdate: undefined }).slice(0, 600)}`);
  }
}
