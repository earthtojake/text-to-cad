/**
 * The Hardcore MCP server (plan §8): the app's actions, as tools an agent
 * can call. One process per integration per session, on stdio, spawned by the agent because
 * Hardcore passes it in `session/new`'s `mcpServers`.
 *
 * The server knows nothing about Electron. It reads four environment
 * variables for the bridge URL, a scoped token, session metadata and integration ID,
 * and forwards every tool call to main as `POST <bridge>/rpc` (see
 * `src/main/integrations/mcp-bridge.ts`). Main does the work; this file is the
 * agent-facing description of it.
 *
 * Two tools are answered here instead: `list_skills` and `read_skill` read the
 * skills root the app materialised (`HARDCORE_SKILLS_ROOT`,
 * `src/main/integrations/skills.ts`), which is static files on disk and needs neither
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
import { integrationById } from "../../src/main/integrations/registry.mjs";

export const BRIDGE_ENV = {
  url: "HARDCORE_BRIDGE_URL",
  token: "HARDCORE_BRIDGE_TOKEN",
  cwd: "HARDCORE_CWD",
  session: "HARDCORE_SESSION_ID",
};

/** Where the app put its skills. Shared with `src/main/integrations/skills.ts` by name. */
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
  return async (method, params, signal) => {
    const response = await fetch(`${url}/rpc`, {
      method: "POST",
      signal,
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
  const integration = integrationById(options.integration ?? process.env.HARDCORE_INTEGRATION ?? "workspace");
  const skillsRoot = options.skillsRoot ?? process.env[SKILLS_ROOT_ENV] ?? null;
  const server = new McpServer({ name: `hardcore-${integration.id}`, version: options.version ?? "0.0.0" });
  for (const definition of integration.tools) {
    server.registerTool(definition.name, {
      description: definition.description,
      inputSchema: definition.inputSchema,
    }, async (params, extra) => {
      try {
        if (definition.name === "list_skills") return text(readSkills(skillsRoot));
        if (definition.name === "read_skill") return text(readSkillFile(skillsRoot, params.name, params.path));
        const result = await bridge(definition.name, params, extra.signal);
        if (definition.output === "image") {
          if (!result?.base64 || !result?.mimeType) throw new Error("Capture did not return an image");
          const { base64, mimeType, ...metadata } = result;
          return { content: [
            { type: "image", data: base64, mimeType },
            { type: "text", text: JSON.stringify(metadata) },
          ] };
        }
        return text(result);
      } catch (error) { return failure(error); }
    });
  }
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
