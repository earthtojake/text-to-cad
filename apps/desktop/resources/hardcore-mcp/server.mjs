/**
 * The Hardcore MCP server (plan §8): the app's actions, as tools an agent
 * can call. One process per session, on stdio, spawned by the agent because
 * Hardcore passes it in `session/new`'s `mcpServers`.
 *
 * The server knows nothing about Electron. It reads four environment
 * variables — the bridge URL, a per-session token, the session's cwd and id —
 * and forwards every tool call to main as `POST <bridge>/rpc` (see
 * `src/main/cad/mcp-bridge.ts`). Main does the work; this file is the
 * agent-facing description of it.
 *
 * `createServer` is exported so the unit test can drive the same tools over
 * an in-memory transport against a fake bridge; the stdio wiring at the
 * bottom runs only when this file is the entry point. In a packaged app the
 * script the agent runs is the esbuild bundle of this file
 * (scripts/build-mcp.mjs), so it needs no `node_modules` beside it; in a
 * checkout the source itself resolves the SDK from `apps/desktop`.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

export const BRIDGE_ENV = {
  url: "HARDCORE_BRIDGE_URL",
  token: "HARDCORE_BRIDGE_TOKEN",
  cwd: "HARDCORE_CWD",
  session: "HARDCORE_SESSION_ID",
};

/** A bridge over HTTP, from the environment. */
export function httpBridge(env = process.env) {
  const url = env[BRIDGE_ENV.url];
  const token = env[BRIDGE_ENV.token];
  if (!url || !token) {
    throw new Error(
      `${BRIDGE_ENV.url} and ${BRIDGE_ENV.token} must be set — this server is started by Hardcore, not by hand`,
    );
  }
  return async (method, params) => {
    const response = await fetch(`${url}/rpc`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
      body: JSON.stringify({ method, params }),
    });
    const body = await response.json().catch(() => ({ ok: false, error: `bridge answered HTTP ${response.status}` }));
    if (!response.ok || !body.ok) {
      throw new Error(body.error ?? `bridge answered HTTP ${response.status}`);
    }
    return body.result;
  };
}

const text = (value) => ({
  content: [{ type: "text", text: typeof value === "string" ? value : JSON.stringify(value, null, 2) }],
});

const failure = (error) => ({
  isError: true,
  content: [{ type: "text", text: error instanceof Error ? error.message : String(error) }],
});

/**
 * Build the server over a bridge function `(method, params) => result`.
 *
 * The descriptions are written for the agent reading them, because that is
 * who reads them: what the tool does in the person's window, when to call it,
 * and what to pass.
 */
export function createServer(bridge, options = {}) {
  const cwd = options.cwd ?? process.env[BRIDGE_ENV.cwd] ?? process.cwd();
  const server = new McpServer({ name: "hardcore", version: options.version ?? "0.0.0" });

  const pathField = z
    .string()
    .min(1)
    .describe(
      `A file path: relative to the session's working directory (${cwd}) or absolute. Must be inside the project.`,
    );

  const call = async (method, params, render = text) => {
    try {
      return render(await bridge(method, params));
    } catch (error) {
      return failure(error);
    }
  };

  server.registerTool(
    "open_file",
    {
      title: "Open a file in the explorer",
      description:
        "Show the person a file. Hardcore opens it in its explorer pane with the right renderer for its type — " +
        "the CAD Viewer for .step/.stp/.glb/.stl/.3mf/.dxf/.urdf/.srdf/.sdf, a code editor for source, " +
        "a rendered preview for markdown, an image viewer for images — focuses that tab and reveals the file in the tree. " +
        "Call it on the artifact you want looked at (the STEP, not the script that wrote it), after the file is fully written. " +
        "This replaces starting a viewer or posting a link: inside Hardcore, never do either.",
      inputSchema: { path: pathField },
    },
    ({ path: target }) => call("open_file", { path: target }),
  );

  server.registerTool(
    "reveal",
    {
      title: "Reveal a file or folder in the tree",
      description:
        "Expand the explorer's file tree to a file or folder and select it, without changing which file is open. " +
        "Use it to point at something — a folder of outputs, a script the person should look at next — when opening it would be too much.",
      inputSchema: { path: pathField },
    },
    ({ path: target }) => call("reveal", { path: target }),
  );

  server.registerTool(
    "open_url",
    {
      title: "Open a web page beside the work",
      description:
        "Open an http(s) URL in a browser tab inside Hardcore's explorer, next to the person's files: a datasheet, " +
        "documentation, a step.parts listing. The person can keep it open while you work. Not for local viewer URLs — there are none to open.",
      inputSchema: { url: z.string().url().describe("An http:// or https:// URL.") },
    },
    ({ url }) => call("open_url", { url }),
  );

  server.registerTool(
    "list_open_tabs",
    {
      title: "List the explorer's open tabs",
      description:
        "What the person has open in the explorer: file tabs with their paths, browser tabs with their URLs, terminal and review tabs, " +
        "and which one is active. Call it before opening more files, or to find out what 'this file' refers to.",
      inputSchema: {},
    },
    () => call("list_open_tabs", {}),
  );

  server.registerTool(
    "viewer_state",
    {
      title: "What the CAD viewer is showing",
      description:
        "The file currently open in the explorer's active tab, whether it is a CAD file rendered by the viewer, and whatever the viewer " +
        "exposes about its state (a selection or a camera preset when available, otherwise null). " +
        "Use it to resolve 'this part', 'that face' or 'the current model' before acting.",
      inputSchema: {},
    },
    () => call("viewer_state", {}),
  );

  server.registerTool(
    "attach_snapshot",
    {
      title: "Attach a snapshot image to the conversation",
      description:
        "Put a PNG (or JPEG/WebP/GIF) into the transcript so the person sees it inline — the way to show a `cadgen step snapshot` " +
        "you rendered. The image is returned as image content. Prefer this over describing a snapshot in words or leaving the person to find the file.",
      inputSchema: { path: pathField },
    },
    ({ path: target }) =>
      call("attach_snapshot", { path: target }, (result) => ({
        content: [
          { type: "image", data: result.base64, mimeType: result.mimeType },
          { type: "text", text: `Attached ${result.path}` },
        ],
      })),
  );

  return server;
}

export async function main() {
  const version = readVersion();
  const server = createServer(httpBridge(), { version });
  await server.connect(new StdioServerTransport());
}

function readVersion() {
  // Beside the bundle in a packaged app (scripts/build-mcp.mjs writes it);
  // absent in a checkout, where the version is not what matters.
  try {
    const here = path.dirname(fileURLToPath(import.meta.url));
    return fs.readFileSync(path.join(here, "VERSION"), "utf8").trim() || "0.0.0";
  } catch {
    return "0.0.0";
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`hardcore-mcp: ${error instanceof Error ? error.message : String(error)}\n`);
    process.exit(1);
  });
}
