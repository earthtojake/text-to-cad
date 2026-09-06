/**
 * The Hardcore plugin, per agent (plan §8): is `cad@hardcore` installed into
 * this agent, at this app's version, and how to make it so.
 *
 * The plugin itself is composed at build time by `scripts/build-plugin.mjs`
 * into `resources/plugin/` — the repo's skills minus `cad-viewer`, plus
 * `hardcore-app`, with manifests naming the plugin `cad`, the marketplace
 * `hardcore` and the version the app's. Three ways it lands:
 *
 *   - Claude Code: `claude plugin marketplace add <resources/plugin>` declares
 *     the directory as a marketplace in the user's settings; `claude plugin
 *     install cad@hardcore` copies it to `~/.claude/plugins/cache/hardcore/cad/
 *     <version>/`. A later version needs `marketplace update` (re-read the
 *     directory) and `plugin update` (install says "already installed"
 *     otherwise). `claude plugin list --json` is how the state is read back.
 *   - Codex: `codex plugin marketplace add <dir>` writes `[marketplaces.hardcore]`
 *     to `~/.codex/config.toml`; `codex plugin add cad@hardcore` copies to
 *     `~/.codex/plugins/cache/hardcore/cad/<version>/` and enables it, and is
 *     idempotent (re-adding refreshes). `codex plugin list --json` reads it back.
 *   - Agents with only a skills directory: the skills are copied to
 *     `<skillsDir>/hardcore/<skill>/` beside a `hardcore-plugin.json` that
 *     records the version.
 *
 * Nothing here touches another plugin, another marketplace, or a skill that
 * is not under `hardcore/`.
 */
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";

import type { AgentProvider } from "../../shared/agents";
import type { PluginState, PluginStatus } from "../../shared/ipc/plugins";

export const PLUGIN_NAME = "cad";
export const MARKETPLACE_NAME = "hardcore";
export const PLUGIN_ID = `${PLUGIN_NAME}@${MARKETPLACE_NAME}`;
/** Written by build-plugin.mjs into the composed directory, and into a skills-dir copy. */
export const MANIFEST_FILE = "hardcore-plugin.json";

export type ExecResult = { stdout: string; stderr: string; code: number | null };

export type PluginHost = {
  appVersion: string;
  /** The composed plugin: `resources/plugin` in a checkout, `Resources/plugin` packaged. */
  pluginDir: string;
  homeDir: string;
  /** Where the "installed at version" record lives (userData). */
  stateFile: string;
  providers: readonly AgentProvider[];
  /** Whether the agent's CLI is on the machine, and where. */
  agent: (agentId: string) => Promise<{ installed: boolean; binaryPath: string | null }>;
  env: () => Promise<Record<string, string>>;
  exec: (file: string, args: string[], env: Record<string, string>) => Promise<ExecResult>;
};

export type ComposedManifest = { name: string; marketplace: string; version: string; skills: string[] };

/* -------------------------------------------------------------------------- */
/* Pure parts                                                                  */
/* -------------------------------------------------------------------------- */

/** `claude plugin list --json`: an array of `{ id, version, … }`. */
export function parseClaudePluginList(json: string, id = PLUGIN_ID): { version: string } | null {
  const parsed = JSON.parse(json) as unknown;
  if (!Array.isArray(parsed)) {
    return null;
  }
  const row = parsed.find((entry) => entry && typeof entry === "object" && (entry as { id?: unknown }).id === id) as
    | { version?: unknown; enabled?: unknown }
    | undefined;
  if (!row) {
    return null;
  }
  return { version: typeof row.version === "string" ? row.version : "" };
}

/** `codex plugin list --json`: `{ installed: [{ pluginId, version, installed, … }], available: [...] }`. */
export function parseCodexPluginList(json: string, id = PLUGIN_ID): { version: string } | null {
  const parsed = JSON.parse(json) as { installed?: unknown };
  if (!parsed || !Array.isArray(parsed.installed)) {
    return null;
  }
  const row = parsed.installed.find(
    (entry) => entry && typeof entry === "object" && (entry as { pluginId?: unknown }).pluginId === id,
  ) as { version?: unknown; installed?: unknown } | undefined;
  if (!row || row.installed === false) {
    return null;
  }
  return { version: typeof row.version === "string" ? row.version : "" };
}

/** What an installed version means against the app's. */
export function pluginState(installed: string | null, available: string): PluginState {
  if (installed === null) {
    return "not-installed";
  }
  return installed === available ? "installed" : "update-available";
}

/** `<plugin>` / `<marketplace>` / `<path>` in a registry argv, substituted. */
export function substitute(argv: readonly string[], values: { path: string; plugin: string; marketplace: string }): string[] {
  return argv.map((arg) =>
    arg.replace("<path>", values.path).replace("<plugin>", values.plugin).replace("<marketplace>", values.marketplace),
  );
}

/**
 * How many MCP servers the agent has configured of its own — reported in the
 * drawer beside the plugin, read-only. Claude Code keeps them in
 * `~/.claude.json` under `mcpServers`; Codex in `config.toml` as
 * `[mcp_servers.<name>]` tables. Other agents: unknown, zero.
 */
export function countMcpServers(agentId: string, homeDir: string): number {
  try {
    if (agentId === "claude-code") {
      const parsed = JSON.parse(fs.readFileSync(path.join(homeDir, ".claude.json"), "utf8")) as { mcpServers?: unknown };
      return parsed.mcpServers && typeof parsed.mcpServers === "object" ? Object.keys(parsed.mcpServers).length : 0;
    }
    if (agentId === "codex") {
      const toml = fs.readFileSync(path.join(homeDir, ".codex", "config.toml"), "utf8");
      return toml.split("\n").filter((line) => /^\s*\[mcp_servers\.[^\]]+\]\s*$/.test(line)).length;
    }
  } catch {
    /* no file, no servers */
  }
  return 0;
}

function expandHome(target: string, homeDir: string): string {
  return target.startsWith("~/") ? path.join(homeDir, target.slice(2)) : target;
}

/* -------------------------------------------------------------------------- */
/* The manager                                                                 */
/* -------------------------------------------------------------------------- */

export class PluginManager {
  constructor(private readonly host: PluginHost) {}

  /** The composed plugin's record, or null when the build has not run. */
  composed(): ComposedManifest | null {
    try {
      return JSON.parse(fs.readFileSync(path.join(this.host.pluginDir, MANIFEST_FILE), "utf8")) as ComposedManifest;
    } catch {
      return null;
    }
  }

  private provider(agentId: string): AgentProvider {
    const provider = this.host.providers.find((candidate) => candidate.id === agentId);
    if (!provider) {
      throw new Error(`unknown agent: ${agentId}`);
    }
    return provider;
  }

  /** Every agent the plugin can land in. */
  targets(): AgentProvider[] {
    return this.host.providers.filter((provider) => provider.pluginInstall || provider.skillsDir);
  }

  async status(agentId: string): Promise<PluginStatus> {
    const provider = this.provider(agentId);
    const base: PluginStatus = {
      agentId,
      state: "unsupported",
      installedVersion: null,
      availableVersion: this.host.appVersion,
      mcpServers: countMcpServers(agentId, this.host.homeDir),
    };
    if (!provider.pluginInstall && !provider.skillsDir) {
      return base;
    }
    try {
      const installed = await this.installedVersion(provider);
      return {
        ...base,
        state: pluginState(installed.version, this.host.appVersion),
        installedVersion: installed.version,
        message: installed.message,
      };
    } catch (error) {
      return { ...base, state: "not-installed", message: error instanceof Error ? error.message : String(error) };
    }
  }

  async statusAll(): Promise<PluginStatus[]> {
    return Promise.all(this.host.providers.map((provider) => this.status(provider.id)));
  }

  private async installedVersion(provider: AgentProvider): Promise<{ version: string | null; message?: string }> {
    if (provider.pluginInstall) {
      const agent = await this.host.agent(provider.id);
      if (!agent.installed || !agent.binaryPath) {
        return { version: null, message: `${provider.name} is not installed on this machine.` };
      }
      const result = await this.host.exec(agent.binaryPath, ["plugin", "list", "--json"], await this.host.env());
      if (result.code !== 0) {
        throw new Error(`${provider.name} could not list its plugins: ${lastLine(result.stderr) || `exit ${result.code}`}`);
      }
      const json = jsonPart(result.stdout);
      const row = provider.id === "codex" ? parseCodexPluginList(json) : parseClaudePluginList(json);
      return { version: row?.version ?? null };
    }
    // Skills directory only.
    const marker = path.join(expandHome(provider.skillsDir!, this.host.homeDir), MARKETPLACE_NAME, MANIFEST_FILE);
    try {
      const manifest = JSON.parse(await fsp.readFile(marker, "utf8")) as { version?: unknown };
      return { version: typeof manifest.version === "string" ? manifest.version : "" };
    } catch {
      return { version: null };
    }
  }

  /** Install or update into one agent, then answer with the state as it now is. */
  async install(agentId: string): Promise<PluginStatus> {
    const provider = this.provider(agentId);
    const composed = this.composed();
    if (!composed) {
      return {
        ...(await this.status(agentId)),
        message: "The bundled plugin is not composed; run `npm run build` in apps/desktop.",
      };
    }
    try {
      if (provider.pluginInstall) {
        await this.installThroughCli(provider);
      } else if (provider.skillsDir) {
        await this.installIntoSkillsDir(provider);
      } else {
        return this.status(agentId);
      }
    } catch (error) {
      return { ...(await this.status(agentId)), message: error instanceof Error ? error.message : String(error) };
    }
    const status = await this.status(agentId);
    if (status.state === "installed") {
      await this.record(agentId, this.host.appVersion);
      return status;
    }
    return {
      ...status,
      message:
        status.message ??
        `Installed, but ${provider.name} reports ${status.installedVersion ?? "nothing"} rather than ${this.host.appVersion}.`,
    };
  }

  private async installThroughCli(provider: AgentProvider): Promise<void> {
    const commands = provider.pluginInstall!;
    const agent = await this.host.agent(provider.id);
    if (!agent.installed || !agent.binaryPath) {
      throw new Error(`${provider.name} is not installed on this machine.`);
    }
    const env = await this.host.env();
    const values = { path: this.host.pluginDir, plugin: PLUGIN_ID, marketplace: MARKETPLACE_NAME };
    const run = async (argv: readonly string[]) => {
      const args = substitute(argv, values);
      const result = await this.host.exec(agent.binaryPath!, args, env);
      if (result.code !== 0) {
        throw new Error(`${path.basename(agent.binaryPath!)} ${args.join(" ")} failed: ${lastLine(result.stderr) || lastLine(result.stdout) || `exit ${result.code}`}`);
      }
      return result;
    };
    await run(commands.marketplaceAdd);
    // A marketplace already declared keeps the snapshot it took: refresh it,
    // so a rebuilt plugin at a new version is what install sees.
    if (commands.marketplaceUpdate) {
      await run(commands.marketplaceUpdate);
    }
    const installed = await run(commands.install);
    // Claude answers "already installed" with exit 0 and leaves the old
    // version in place; its update verb is what moves it.
    if (commands.update && /already installed/i.test(`${installed.stdout}\n${installed.stderr}`)) {
      await run(commands.update);
    }
  }

  private async installIntoSkillsDir(provider: AgentProvider): Promise<void> {
    const composed = this.composed()!;
    const skillsDir = expandHome(provider.skillsDir!, this.host.homeDir);
    const target = path.join(skillsDir, MARKETPLACE_NAME);
    // Only ever our own subfolder: the user's skills beside it are not touched.
    await fsp.rm(target, { recursive: true, force: true });
    await fsp.mkdir(target, { recursive: true });
    for (const skill of composed.skills) {
      await fsp.cp(path.join(this.host.pluginDir, "skills", skill), path.join(target, skill), {
        recursive: true,
        dereference: true,
      });
    }
    await fsp.writeFile(path.join(target, MANIFEST_FILE), `${JSON.stringify(composed, null, 2)}\n`);
  }

  /* ------------------------------------------------------------------------ */
  /* First launch and updates                                                  */
  /* ------------------------------------------------------------------------ */

  private async readState(): Promise<Record<string, string>> {
    try {
      return JSON.parse(await fsp.readFile(this.host.stateFile, "utf8")) as Record<string, string>;
    } catch {
      return {};
    }
  }

  private async record(agentId: string, version: string): Promise<void> {
    const state = await this.readState();
    state[agentId] = version;
    await fsp.mkdir(path.dirname(this.host.stateFile), { recursive: true });
    await fsp.writeFile(this.host.stateFile, `${JSON.stringify(state, null, 2)}\n`);
  }

  /**
   * On launch: install into every agent that is on the machine and has not
   * been given this version yet. The record is per agent, so an agent
   * installed after the app still gets the plugin on the next launch, and an
   * app update (a new version) re-installs into all of them once.
   */
  async ensureInstalled(): Promise<PluginStatus[]> {
    if (!this.composed()) {
      return [];
    }
    const state = await this.readState();
    const results: PluginStatus[] = [];
    for (const provider of this.targets()) {
      if (state[provider.id] === this.host.appVersion) {
        continue;
      }
      const agent = await this.host.agent(provider.id);
      if (provider.pluginInstall && !agent.installed) {
        continue;
      }
      results.push(await this.install(provider.id));
    }
    return results;
  }
}

function lastLine(text: string): string {
  return text.trim().split("\n").filter(Boolean).at(-1) ?? "";
}

/** The JSON in a CLI's stdout, skipping any narration before it. */
function jsonPart(stdout: string): string {
  const start = stdout.search(/[[{]/);
  return start >= 0 ? stdout.slice(start) : stdout;
}
