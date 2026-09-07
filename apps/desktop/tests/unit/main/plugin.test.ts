import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  MANIFEST_FILE,
  PLUGIN_ID,
  PluginManager,
  countMcpServers,
  parseClaudePluginList,
  parseCodexPluginList,
  pluginState,
  substitute,
  type PluginHost,
} from "@main/cad/plugin";
import { AGENT_PROVIDERS, agentProvider } from "@main/agents/registry";

const temps: string[] = [];
function tempDir(prefix: string): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  temps.push(dir);
  return dir;
}
afterEach(() => {
  for (const dir of temps.splice(0)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

/* -------------------------------------------------------------------------- */
/* Parsing the agents' answers                                                 */
/* -------------------------------------------------------------------------- */

// Recorded from `claude plugin list --json` (Claude Code 2.1.261) and
// `codex plugin list --json` (codex-cli 0.149.1) after installing the composed
// plugin on 2026-09-06.
const CLAUDE_LIST = JSON.stringify([
  { id: "vercel@claude-plugins-official", version: "0.48.0", scope: "user", enabled: true, mcpServers: { vercel: { type: "http", url: "https://mcp.vercel.com" } } },
  { id: "cad@hardcore", version: "0.5.0", scope: "user", enabled: true, installPath: "/Users/me/.claude/plugins/cache/hardcore/cad/0.5.0" },
]);

const CODEX_LIST = JSON.stringify({
  installed: [
    { pluginId: "pdf@openai-primary-runtime", name: "pdf", marketplaceName: "openai-primary-runtime", version: "26.904.11930", installed: true, enabled: true },
    { pluginId: "cad@hardcore", name: "cad", marketplaceName: "hardcore", version: "0.5.0", installed: true, enabled: true, source: { source: "local", path: "/app/Resources/plugin" } },
  ],
  available: [],
});

describe("plugin list parsing", () => {
  it("finds cad@hardcore in Claude's list", () => {
    expect(parseClaudePluginList(CLAUDE_LIST)).toEqual({ version: "0.5.0" });
    expect(parseClaudePluginList("[]")).toBeNull();
    expect(parseClaudePluginList(JSON.stringify([{ id: "cad@text-to-cad", version: "0.5.0" }]))).toBeNull();
  });

  it("finds cad@hardcore in Codex's list, installed only", () => {
    expect(parseCodexPluginList(CODEX_LIST)).toEqual({ version: "0.5.0" });
    expect(parseCodexPluginList(JSON.stringify({ installed: [], available: [{ pluginId: PLUGIN_ID, installed: false }] }))).toBeNull();
    expect(parseCodexPluginList(JSON.stringify({ installed: [{ pluginId: PLUGIN_ID, version: "0.4.0", installed: false }] }))).toBeNull();
  });

  it("turns versions into a state", () => {
    expect(pluginState(null, "0.5.0")).toBe("not-installed");
    expect(pluginState("0.5.0", "0.5.0")).toBe("installed");
    expect(pluginState("0.4.9", "0.5.0")).toBe("update-available");
  });

  it("substitutes the registry's placeholders", () => {
    expect(substitute(["plugin", "marketplace", "add", "<path>"], { path: "/r/plugin", plugin: PLUGIN_ID, marketplace: "hardcore" })).toEqual([
      "plugin",
      "marketplace",
      "add",
      "/r/plugin",
    ]);
    expect(substitute(["plugin", "install", "<plugin>"], { path: "", plugin: PLUGIN_ID, marketplace: "hardcore" })).toEqual([
      "plugin",
      "install",
      "cad@hardcore",
    ]);
  });

  it("counts the user's own MCP servers where each agent keeps them", () => {
    const home = tempDir("hardcore-home-");
    fs.writeFileSync(path.join(home, ".claude.json"), JSON.stringify({ mcpServers: { a: {}, b: {} } }));
    fs.mkdirSync(path.join(home, ".codex"));
    fs.writeFileSync(path.join(home, ".codex", "config.toml"), '[mcp_servers.github]\nurl = "x"\n[plugins."cad@hardcore"]\nenabled = true\n[mcp_servers.linear]\n');
    expect(countMcpServers("claude-code", home)).toBe(2);
    expect(countMcpServers("codex", home)).toBe(2);
    expect(countMcpServers("gemini-cli", home)).toBe(0);
  });
});

/* -------------------------------------------------------------------------- */
/* The manager                                                                 */
/* -------------------------------------------------------------------------- */

function composedPlugin(dir: string, version: string) {
  fs.mkdirSync(path.join(dir, "skills", "cad"), { recursive: true });
  fs.writeFileSync(path.join(dir, "skills", "cad", "SKILL.md"), "---\nname: cad\n---\n");
  fs.mkdirSync(path.join(dir, "skills", "hardcore-app-use"), { recursive: true });
  fs.writeFileSync(path.join(dir, "skills", "hardcore-app-use", "SKILL.md"), "---\nname: hardcore-app-use\n---\n");
  fs.writeFileSync(path.join(dir, MANIFEST_FILE), JSON.stringify({ name: "cad", marketplace: "hardcore", version, skills: ["cad", "hardcore-app-use"] }));
}

function host(options: {
  version?: string;
  composed?: boolean;
  installed?: Record<string, string>;
  lists?: Record<string, string>;
  commands?: string[];
  failing?: string;
}) {
  const root = tempDir("hardcore-plugin-");
  const pluginDir = path.join(root, "plugin");
  const home = path.join(root, "home");
  fs.mkdirSync(home);
  if (options.composed !== false) {
    composedPlugin(pluginDir, options.version ?? "0.5.0");
  }
  const commands = options.commands ?? [];
  const lists = { ...(options.lists ?? {}) };
  const pluginHost: PluginHost = {
    appVersion: options.version ?? "0.5.0",
    pluginDir,
    homeDir: home,
    stateFile: path.join(root, "userData", "plugin-installs.json"),
    providers: AGENT_PROVIDERS,
    agent: async (agentId) => {
      const binary = options.installed?.[agentId];
      return { installed: Boolean(binary), binaryPath: binary ?? null };
    },
    env: async () => ({ PATH: "/usr/bin" }),
    exec: async (file, args) => {
      const line = `${path.basename(file)} ${args.join(" ")}`;
      commands.push(line);
      if (options.failing && line.startsWith(options.failing)) {
        return { stdout: "", stderr: "boom", code: 1 };
      }
      if (args[0] === "plugin" && args[1] === "list") {
        return { stdout: lists[path.basename(file)] ?? "[]", stderr: "", code: 0 };
      }
      if (line === "claude plugin install cad@hardcore" && lists.claude?.includes(PLUGIN_ID)) {
        return { stdout: 'Plugin "cad@hardcore" is already installed (scope: user)', stderr: "", code: 0 };
      }
      // What the CLI installs is whatever the composed directory holds now.
      if (line === "claude plugin install cad@hardcore" || line === "claude plugin update cad@hardcore") {
        lists.claude = JSON.stringify([{ id: PLUGIN_ID, version: pluginHost.appVersion }]);
      }
      if (line === "codex plugin add cad@hardcore") {
        lists.codex = JSON.stringify({ installed: [{ pluginId: PLUGIN_ID, version: pluginHost.appVersion, installed: true }] });
      }
      return { stdout: "ok", stderr: "", code: 0 };
    },
  };
  return { host: pluginHost, commands, home, pluginDir, root };
}

describe("PluginManager.status", () => {
  it("reads Claude's and Codex's plugin lists", async () => {
    const h = host({
      installed: { "claude-code": "/bin/claude", codex: "/bin/codex" },
      lists: { claude: CLAUDE_LIST, codex: JSON.stringify({ installed: [{ pluginId: PLUGIN_ID, version: "0.4.0", installed: true }] }) },
    });
    const manager = new PluginManager(h.host);
    expect(await manager.status("claude-code")).toMatchObject({ state: "installed", installedVersion: "0.5.0", availableVersion: "0.5.0" });
    expect(await manager.status("codex")).toMatchObject({ state: "update-available", installedVersion: "0.4.0" });
    expect(h.commands).toEqual(["claude plugin list --json", "codex plugin list --json"]);
  });

  it("is not-installed, with a reason, when the agent's CLI is missing", async () => {
    const h = host({});
    const status = await new PluginManager(h.host).status("claude-code");
    expect(status.state).toBe("not-installed");
    expect(status.message).toContain("not installed on this machine");
    expect(h.commands).toEqual([]);
  });

  it("reads the marker for skills-directory agents and answers unsupported for the rest", async () => {
    const h = host({});
    const manager = new PluginManager(h.host);
    expect((await manager.status("gemini-cli")).state).toBe("not-installed");
    const marker = path.join(h.home, ".gemini", "skills", "hardcore", MANIFEST_FILE);
    fs.mkdirSync(path.dirname(marker), { recursive: true });
    fs.writeFileSync(marker, JSON.stringify({ version: "0.5.0" }));
    expect(await manager.status("gemini-cli")).toMatchObject({ state: "installed", installedVersion: "0.5.0" });
    expect((await manager.status("kiro")).state).toBe("unsupported");
  });
});

describe("PluginManager.install", () => {
  it("runs marketplace add, marketplace update and install for Claude, then records the version", async () => {
    const h = host({ installed: { "claude-code": "/bin/claude" } });
    const manager = new PluginManager(h.host);
    const status = await manager.install("claude-code");
    expect(status).toMatchObject({ state: "installed", installedVersion: "0.5.0" });
    expect(h.commands).toEqual([
      `claude plugin marketplace add ${h.pluginDir}`,
      "claude plugin marketplace update hardcore",
      "claude plugin install cad@hardcore",
      "claude plugin list --json",
    ]);
    expect(JSON.parse(fs.readFileSync(h.host.stateFile, "utf8"))).toEqual({ "claude-code": "0.5.0" });
  });

  it("falls through to plugin update when Claude says the plugin is already installed", async () => {
    const h = host({ installed: { "claude-code": "/bin/claude" }, lists: { claude: JSON.stringify([{ id: PLUGIN_ID, version: "0.4.0" }]) } });
    await new PluginManager(h.host).install("claude-code");
    expect(h.commands).toContain("claude plugin update cad@hardcore");
  });

  it("runs marketplace add and plugin add for Codex", async () => {
    const h = host({ installed: { codex: "/bin/codex" } });
    const status = await new PluginManager(h.host).install("codex");
    expect(status.state).toBe("installed");
    expect(h.commands).toEqual([`codex plugin marketplace add ${h.pluginDir}`, "codex plugin add cad@hardcore", "codex plugin list --json"]);
  });

  it("copies the skills under hardcore/ for an agent with only a skills directory, touching nothing else", async () => {
    const h = host({});
    const skills = path.join(h.home, ".gemini", "skills");
    fs.mkdirSync(path.join(skills, "mine"), { recursive: true });
    fs.writeFileSync(path.join(skills, "mine", "SKILL.md"), "theirs");
    const status = await new PluginManager(h.host).install("gemini-cli");
    expect(status).toMatchObject({ state: "installed", installedVersion: "0.5.0" });
    expect(fs.existsSync(path.join(skills, "hardcore", "cad", "SKILL.md"))).toBe(true);
    expect(fs.existsSync(path.join(skills, "hardcore", "hardcore-app-use", "SKILL.md"))).toBe(true);
    expect(fs.readFileSync(path.join(skills, "mine", "SKILL.md"), "utf8")).toBe("theirs");
    expect(h.commands).toEqual([]);
  });

  it("reports a failed CLI step and installs nothing", async () => {
    const h = host({ installed: { codex: "/bin/codex" }, failing: "codex plugin marketplace add" });
    const status = await new PluginManager(h.host).install("codex");
    expect(status.state).toBe("not-installed");
    expect(status.message).toContain("codex plugin marketplace add");
    expect(status.message).toContain("boom");
    expect(fs.existsSync(h.host.stateFile)).toBe(false);
  });

  it("says so when the plugin has not been composed", async () => {
    const h = host({ composed: false, installed: { codex: "/bin/codex" } });
    const status = await new PluginManager(h.host).install("codex");
    expect(status.message).toContain("npm run build");
    expect(h.commands).toEqual(["codex plugin list --json"]);
  });
});

describe("PluginManager.ensureInstalled", () => {
  it("installs into the agents on the machine once per app version, and skips the rest", async () => {
    const h = host({ installed: { "claude-code": "/bin/claude" } });
    const manager = new PluginManager(h.host);
    const first = await manager.ensureInstalled();
    expect(first.map((status) => status.agentId)).toContain("claude-code");
    expect(first.map((status) => status.agentId)).not.toContain("codex");
    // Skills-directory agents are always reachable: they need no CLI.
    expect(first.map((status) => status.agentId)).toContain("gemini-cli");
    const installs = h.commands.filter((line) => line.endsWith("install cad@hardcore")).length;

    // A second launch at the same version does nothing.
    expect(await manager.ensureInstalled()).toEqual([]);
    expect(h.commands.filter((line) => line.endsWith("install cad@hardcore")).length).toBe(installs);
  });

  it("re-installs after an app update", async () => {
    const h = host({ installed: { codex: "/bin/codex" } });
    const manager = new PluginManager(h.host);
    await manager.ensureInstalled();
    // The app updated: a new version, a newly composed plugin, the same record.
    h.host.appVersion = "0.6.0";
    composedPlugin(h.pluginDir, "0.6.0");
    const results = await manager.ensureInstalled();
    expect(results.find((status) => status.agentId === "codex")?.state).toBe("installed");
    expect(h.commands.filter((line) => line === "codex plugin add cad@hardcore")).toHaveLength(2);
  });

  it("is a no-op without a composed plugin", async () => {
    const h = host({ composed: false, installed: { codex: "/bin/codex" } });
    expect(await new PluginManager(h.host).ensureInstalled()).toEqual([]);
    expect(h.commands).toEqual([]);
  });
});

describe("the registry's plugin verbs", () => {
  it("name the update verbs for Claude, whose install refuses to move a version", () => {
    expect(agentProvider("claude-code")!.pluginInstall?.update).toEqual(["plugin", "update", "<plugin>"]);
    expect(agentProvider("codex")!.pluginInstall?.update).toBeUndefined();
  });
});
