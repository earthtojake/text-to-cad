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
 * Two tools are answered here instead: `list_skills` and `read_skill` read the
 * skills root the app materialised (`HARDCORE_SKILLS_ROOT`,
 * `src/main/cad/skills.ts`), which is static files on disk and needs neither
 * main nor a window. They are how an agent that does not load an additional
 * directory's skills by itself reaches the same files.
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

/** Where the app put its skills. Shared with `src/main/cad/skills.ts` by name. */
export const SKILLS_ROOT_ENV = "HARDCORE_SKILLS_ROOT";

/** The layout inside the skills root that this server reads. */
const SKILLS_LAYOUT = path.join(".claude", "skills");

/** The `name` and `description` of a SKILL.md's front matter, folded onto one line. */
export function skillFrontmatter(text) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---/.exec(text);
  if (!match) {
    return {};
  }
  const fields = {};
  let key = null;
  for (const line of match[1].split(/\r?\n/)) {
    const start = /^([A-Za-z_][\w-]*):\s*(.*)$/.exec(line);
    if (start) {
      key = start[1];
      fields[key] = start[2] ?? "";
    } else if (key && /^\s+\S/.test(line)) {
      fields[key] = `${fields[key]} ${line.trim()}`.trim();
    } else {
      key = null;
    }
  }
  const unquote = (value) => (value ? value.replace(/^['"]|['"]$/g, "").trim() : "");
  return { name: unquote(fields.name), description: unquote(fields.description) };
}

/**
 * The skills on disk, or an empty list when the app did not name a root. The
 * directory name is the skill's identity; the description comes out of its
 * SKILL.md.
 */
export function readSkills(root) {
  if (!root) {
    return [];
  }
  const directory = path.join(root, SKILLS_LAYOUT);
  let entries;
  try {
    entries = fs.readdirSync(directory, { withFileTypes: true });
  } catch {
    return [];
  }
  const skills = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue;
    }
    const file = path.join(directory, entry.name, "SKILL.md");
    if (!fs.existsSync(file)) {
      continue;
    }
    skills.push({ name: entry.name, description: skillFrontmatter(fs.readFileSync(file, "utf8")).description ?? "" });
  }
  return skills.sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * A file inside one skill, refused outside it. `relative` defaults to the
 * SKILL.md; a skill's `references/*.md` is the other thing worth reading.
 */
export function readSkillFile(root, name, relative = "SKILL.md") {
  if (!root) {
    throw new Error("this session was given no skills root");
  }
  const directory = path.resolve(path.join(root, SKILLS_LAYOUT, name));
  const skillRoot = path.resolve(path.join(root, SKILLS_LAYOUT));
  if (path.relative(skillRoot, directory).split(path.sep)[0] === "..") {
    throw new Error(`${name} is not a skill`);
  }
  if (!fs.existsSync(path.join(directory, "SKILL.md"))) {
    throw new Error(`no skill named ${name}; call list_skills`);
  }
  const target = path.resolve(directory, relative);
  if (path.relative(directory, target).split(path.sep)[0] === "..") {
    throw new Error(`${relative} is outside the ${name} skill`);
  }
  if (!fs.existsSync(target) || !fs.statSync(target).isFile()) {
    throw new Error(`${relative} is not a file in the ${name} skill`);
  }
  return { path: path.join(name, relative), text: fs.readFileSync(target, "utf8") };
}

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
  const skillsRoot = options.skillsRoot ?? process.env[SKILLS_ROOT_ENV] ?? null;
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

  server.registerTool(
    "list_skills",
    {
      title: "List the skills Hardcore ships",
      description:
        "The skills this app carries, by name, with what each is for. They are files on disk inside Hardcore — " +
        "not installed into your configuration — so nothing loads them for you: read the one that fits before you start. " +
        "Read `cad` before any CAD, STEP, DXF, mesh or robot-description work, and `hardcore-app-use` before showing " +
        "the person a file or otherwise acting on this app. Call this first in a session that touches either.",
      inputSchema: {},
    },
    () => {
      const skills = readSkills(skillsRoot);
      if (skills.length === 0) {
        return failure(new Error("this session was given no skills"));
      }
      return text({ root: path.join(skillsRoot, SKILLS_LAYOUT), skills });
    },
  );

  server.registerTool(
    "read_skill",
    {
      title: "Read a skill",
      description:
        "The text of a skill's SKILL.md, or of a file inside that skill (its `references/…` pages, its scripts). " +
        "This is the instruction set you are expected to follow for that kind of work — read `cad` before CAD work " +
        "and `hardcore-app-use` before touching this app, and follow what they say over your own defaults.",
      inputSchema: {
        name: z.string().min(1).describe("A skill's name, as `list_skills` reports it."),
        path: z
          .string()
          .min(1)
          .optional()
          .describe("A file inside the skill, relative to its directory. Defaults to SKILL.md."),
      },
    },
    ({ name, path: relative }) => {
      try {
        return text(readSkillFile(skillsRoot, name, relative));
      } catch (error) {
        return failure(error);
      }
    },
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
