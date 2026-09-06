import { parse as parseTOML, stringify as stringifyTOML } from 'smol-toml';
import type { PluginFs } from '#primitives/plugin-fs/api';
import type { McpServerRegistration } from '#services/agent-plugins/api/plugins/capabilities/mcp';

// ── Internal helpers ────────────────────────────────────────────────────────

function getNestedValue(obj: Record<string, unknown>, path: string): unknown {
  return path
    .split('.')
    .reduce<unknown>(
      (cur, key) =>
        cur != null && typeof cur === 'object' ? (cur as Record<string, unknown>)[key] : undefined,
      obj
    );
}

function setNestedValue(obj: Record<string, unknown>, path: string, value: unknown): void {
  const keys = path.split('.');
  const last = keys.pop()!;
  const target = keys.reduce<Record<string, unknown>>((cur, key) => {
    if (cur[key] == null || typeof cur[key] !== 'object') cur[key] = {};
    return cur[key] as Record<string, unknown>;
  }, obj);
  target[last] = value;
}

function deepClone<T>(obj: T): T {
  return structuredClone(obj);
}

const INJECTED_ACCEPT = 'application/json, text/event-stream';

function ensureHeader(headers: Record<string, string>, key: string, val: string): void {
  if (typeof headers[key] !== 'string') headers[key] = val;
}

function stripInjectedHeaders(entry: Record<string, unknown>): void {
  if (typeof entry.headers !== 'object' || entry.headers === null) return;
  const headers = entry.headers as Record<string, string>;
  if (headers.Accept === INJECTED_ACCEPT) {
    delete headers.Accept;
    if (!Object.keys(headers).length) delete entry.headers;
  }
}

// ── McpConfigShape ──────────────────────────────────────────────────────────

type McpConfigShape = {
  /** Primary config path: the only file written to. */
  configPath: string;
  /** Extra paths read for migration only — never written. */
  legacyReadPaths?: string[];
  /** Optional server key used only by legacyReadPaths. */
  legacyServersKey?: string;
  /** Treat legacyServersKey as a literal key instead of a dot-delimited object path. */
  legacyServersKeyIsLiteral?: boolean;
  format: 'json' | 'toml';
  serversKey: string;
  /** Treat serversKey as a literal key instead of a dot-delimited object path. */
  serversKeyIsLiteral?: boolean;
  toNative(server: McpServerRegistration): Record<string, unknown>;
  fromNative(name: string, raw: Record<string, unknown>): McpServerRegistration;
};

function parseMcpFile(content: string, format: 'json' | 'toml'): Record<string, unknown> {
  return format === 'json'
    ? (JSON.parse(content) as Record<string, unknown>)
    : (parseTOML(content) as Record<string, unknown>);
}

export function createMcpAdapter(shape: McpConfigShape) {
  const getServers = (
    parsed: Record<string, unknown>,
    serversKey = shape.serversKey,
    serversKeyIsLiteral = shape.serversKeyIsLiteral
  ): unknown => (serversKeyIsLiteral ? parsed[serversKey] : getNestedValue(parsed, serversKey));

  const setServers = (
    parsed: Record<string, unknown>,
    servers: unknown,
    serversKey = shape.serversKey,
    serversKeyIsLiteral = shape.serversKeyIsLiteral
  ): void => {
    if (serversKeyIsLiteral) {
      parsed[serversKey] = servers;
      return;
    }
    setNestedValue(parsed, serversKey, servers);
  };

  const legacyServersKey = shape.legacyServersKey ?? shape.serversKey;
  const legacyServersKeyIsLiteral =
    shape.legacyServersKey === undefined
      ? shape.serversKeyIsLiteral
      : shape.legacyServersKeyIsLiteral;

  async function readFromPath(
    fs: PluginFs,
    filePath: string,
    serversKey = shape.serversKey,
    serversKeyIsLiteral = shape.serversKeyIsLiteral
  ): Promise<Map<string, McpServerRegistration>> {
    const content = await fs.read(filePath);
    if (!content) return new Map();
    try {
      const parsed = parseMcpFile(content, shape.format);
      const servers = getServers(parsed, serversKey, serversKeyIsLiteral) ?? {};
      return new Map(
        Object.entries(servers as Record<string, unknown>).map(([name, raw]) => [
          name,
          shape.fromNative(name, raw as Record<string, unknown>),
        ])
      );
    } catch {
      return new Map();
    }
  }

  async function removeFromPath(
    fs: PluginFs,
    filePath: string,
    name: string,
    serversKey = shape.serversKey,
    serversKeyIsLiteral = shape.serversKeyIsLiteral
  ): Promise<void> {
    const content = await fs.read(filePath);
    if (!content) return;
    try {
      const parsed = parseMcpFile(content, shape.format);
      const servers = getServers(parsed, serversKey, serversKeyIsLiteral) ?? {};
      if (!(name in (servers as Record<string, unknown>))) return;
      const filtered = Object.fromEntries(
        Object.entries(servers as Record<string, unknown>).filter(([k]) => k !== name)
      );
      setServers(parsed, filtered, serversKey, serversKeyIsLiteral);
      const output =
        shape.format === 'json' ? JSON.stringify(parsed, null, 2) + '\n' : stringifyTOML(parsed);
      await fs.write(filePath, output);
    } catch {
      // ignore parse errors in legacy files
    }
  }

  return {
    async readServers(fs: PluginFs): Promise<McpServerRegistration[]> {
      const serverMap = new Map<string, McpServerRegistration>();
      // Legacy paths first (lower priority — canonical wins on name conflict)
      for (const legacyPath of shape.legacyReadPaths ?? []) {
        for (const [name, reg] of await readFromPath(
          fs,
          legacyPath,
          legacyServersKey,
          legacyServersKeyIsLiteral
        )) {
          if (!serverMap.has(name)) serverMap.set(name, reg);
        }
      }
      // Canonical path — overwrites any legacy entry with the same name
      for (const [name, reg] of await readFromPath(fs, shape.configPath)) {
        serverMap.set(name, reg);
      }
      return Array.from(serverMap.values());
    },
    async writeServers(fs: PluginFs, servers: McpServerRegistration[]): Promise<void> {
      // Always write the canonical path only; legacy paths are read-only
      const content = await fs.read(shape.configPath);
      const parsed: Record<string, unknown> = content ? parseMcpFile(content, shape.format) : {};
      const native = Object.fromEntries(servers.map((s) => [s.name, shape.toNative(s)]));
      setServers(parsed, native);
      const output =
        shape.format === 'json' ? JSON.stringify(parsed, null, 2) + '\n' : stringifyTOML(parsed);
      await fs.write(shape.configPath, output);
    },
    async removeServer(fs: PluginFs, name: string): Promise<void> {
      // Remove from canonical path
      await removeFromPath(fs, shape.configPath, name);
      // Remove from all legacy paths so a stale copy cannot resurface on next read
      for (const legacyPath of shape.legacyReadPaths ?? []) {
        await removeFromPath(fs, legacyPath, name, legacyServersKey, legacyServersKeyIsLiteral);
      }
    },
  };
}

// ── Per-provider adapters ───────────────────────────────────────────────────

/** Passthrough adapter — agent uses canonical format (mcpServers JSON key). */
export function passthroughMcpAdapter(configPath: string, legacyReadPaths?: string[]) {
  return createMcpAdapter({
    configPath,
    legacyReadPaths,
    format: 'json',
    serversKey: 'mcpServers',
    toNative(s) {
      const { name: _n, ...rest } = s;
      return rest as Record<string, unknown>;
    },
    fromNative(name, raw) {
      return { name, ...raw } as McpServerRegistration;
    },
  });
}

/**
 * Cursor adapter — HTTP servers drop `type`, but `url` stays.
 * Config: ~/.cursor/mcp.json, key: mcpServers, JSON.
 */
export function cursorMcpAdapter(configPath = '.cursor/mcp.json') {
  return createMcpAdapter({
    configPath,
    format: 'json',
    serversKey: 'mcpServers',
    toNative(s) {
      const { name: _n, type: _t, ...rest } = s as McpServerRegistration & { type?: string };
      return rest as Record<string, unknown>;
    },
    fromNative(name, raw) {
      const entry = deepClone(raw);
      if ('url' in entry && !('command' in entry)) {
        (entry as Record<string, unknown>).type = 'http';
      }
      return { name, ...entry } as McpServerRegistration;
    },
  });
}

/**
 * Codex adapter — TOML file with stdio and streamable HTTP servers.
 * Config: ~/.codex/config.toml, key: mcp_servers.
 */
export function codexMcpAdapter(configPath = '.codex/config.toml') {
  return createMcpAdapter({
    configPath,
    format: 'toml',
    serversKey: 'mcp_servers',
    toNative(s) {
      const entry = deepClone(s) as Record<string, unknown>;
      const isHttp =
        entry.transport === 'http' ||
        entry.type === 'http' ||
        (typeof entry.url === 'string' && typeof entry.command !== 'string');

      delete entry.name;
      delete entry.transport;
      delete entry.type;

      if (isHttp && entry.headers && !entry.http_headers) {
        entry.http_headers = entry.headers;
        delete entry.headers;
      }

      return entry;
    },
    fromNative(name, raw) {
      const entry = deepClone(raw) as Record<string, unknown>;
      const isHttp = typeof entry.url === 'string' && typeof entry.command !== 'string';

      if (isHttp) {
        if (entry.http_headers && !entry.headers) {
          entry.headers = entry.http_headers;
        }
        delete entry.http_headers;
        entry.transport = 'http';
        entry.type = 'http';
      }

      return { name, ...entry } as McpServerRegistration;
    },
  });
}

/**
 * Grok adapter — TOML file with stdio and streamable HTTP servers.
 * Config: ~/.grok/config.toml, key: mcp_servers.
 *
 * Unlike Codex, Grok keeps HTTP `headers` under their canonical key (it does not
 * rename them to `http_headers`) and marks every server with `enabled = true` by
 * default, matching the `grok mcp add` CLI behavior. Transport is inferred from the
 * presence of `url` (HTTP) vs `command` (stdio); there is no `type`/`transport` field.
 */
export function grokMcpAdapter(configPath = '.grok/config.toml') {
  return createMcpAdapter({
    configPath,
    format: 'toml',
    serversKey: 'mcp_servers',
    toNative(s) {
      const { name: _name, transport: _transport, type: _type, ...entry } = s;
      if (typeof entry.enabled !== 'boolean') entry.enabled = true;
      return entry;
    },
    fromNative(name, raw) {
      const entry = deepClone(raw) as Record<string, unknown>;
      const isHttp = typeof entry.url === 'string' && typeof entry.command !== 'string';
      if (isHttp) {
        entry.transport = 'http';
        entry.type = 'http';
      }
      return { name, ...entry } as McpServerRegistration;
    },
  });
}

/**
 * Gemini adapter — HTTP servers use httpUrl instead of url; Accept header is injected.
 * Config: ~/.gemini/settings.json, key: mcpServers, JSON.
 */
export function geminiMcpAdapter(configPath = '.gemini/settings.json') {
  return createMcpAdapter({
    configPath,
    format: 'json',
    serversKey: 'mcpServers',
    toNative(s) {
      const entry = deepClone(s) as Record<string, unknown>;
      delete entry.name;
      if (entry.type === 'http') {
        const url = (entry.url as string) ?? '';
        const baseHeaders = (entry.headers as Record<string, string>) ?? {};
        const headers: Record<string, string> = { ...baseHeaders };
        ensureHeader(headers, 'Accept', INJECTED_ACCEPT);
        const result: Record<string, unknown> = { httpUrl: url, headers };
        if (entry.env) result.env = entry.env;
        return result;
      }
      delete entry.type;
      return entry;
    },
    fromNative(name, raw) {
      const entry = deepClone(raw) as Record<string, unknown>;
      if ('httpUrl' in entry) {
        const { httpUrl, ...rest } = entry;
        const result = { ...rest, type: 'http', url: httpUrl } as Record<string, unknown>;
        stripInjectedHeaders(result);
        return { name, ...result } as McpServerRegistration;
      }
      return { name, ...entry } as McpServerRegistration;
    },
  });
}

/**
 * Qwen adapter — same as Gemini (httpUrl ↔ url, Accept header).
 * Config: ~/.qwen/settings.json, key: mcpServers, JSON.
 */
export function qwenMcpAdapter(configPath = '.qwen/settings.json') {
  return geminiMcpAdapter(configPath);
}

/**
 * OpenCode adapter — type:'remote'/url for HTTP; type:'local'/command[] for stdio.
 * Write: ~/.config/opencode/opencode.json; legacy read: ~/.opencode/config.json.
 */
export function opencodeMcpAdapter(
  configPath = '.config/opencode/opencode.json',
  legacyReadPaths = ['.opencode/config.json']
) {
  return createMcpAdapter({
    configPath,
    legacyReadPaths,
    format: 'json',
    serversKey: 'mcp',
    toNative(s) {
      const entry = deepClone(s) as Record<string, unknown>;
      delete entry.name;
      const enabled = typeof entry.enabled === 'boolean' ? entry.enabled : true;
      if (entry.type === 'http') {
        const url = (entry.url as string) ?? '';
        const baseHeaders = (entry.headers as Record<string, string>) ?? {};
        const headers: Record<string, string> = { ...baseHeaders };
        ensureHeader(headers, 'Accept', INJECTED_ACCEPT);
        const result: Record<string, unknown> = {
          type: 'remote',
          url,
          headers,
          enabled,
        };
        if (entry.env) result.env = entry.env;
        if (entry.timeout !== undefined) result.timeout = entry.timeout;
        if (entry.oauth !== undefined) result.oauth = entry.oauth;
        return result;
      }
      // stdio
      const cmdVec: string[] = [];
      if (typeof entry.command === 'string' && entry.command) cmdVec.push(entry.command as string);
      if (Array.isArray(entry.args)) cmdVec.push(...(entry.args as string[]));
      if (!cmdVec.length && enabled === false) return { enabled: false };
      const result: Record<string, unknown> = { type: 'local', command: cmdVec, enabled };
      if (entry.env) result.environment = entry.env;
      if (entry.cwd !== undefined) result.cwd = entry.cwd;
      if (entry.timeout !== undefined) result.timeout = entry.timeout;
      return result;
    },
    fromNative(name, raw) {
      const entry = deepClone(raw) as Record<string, unknown>;
      if (entry.type === 'remote') {
        const { type: _t, ...rest } = entry;
        const result = { ...rest, type: 'http' } as Record<string, unknown>;
        stripInjectedHeaders(result);
        return { name, ...result } as McpServerRegistration;
      }
      if (entry.type === 'local' && Array.isArray(entry.command)) {
        const cmdArr = entry.command as string[];
        const [command, ...args] = cmdArr;
        const result: Record<string, unknown> = {};
        if (command) result.command = command;
        if (args.length) result.args = args;
        if (entry.environment) result.env = entry.environment;
        else if (entry.env) result.env = entry.env;
        if (typeof entry.enabled === 'boolean') result.enabled = entry.enabled;
        if (typeof entry.cwd === 'string') result.cwd = entry.cwd;
        if (typeof entry.timeout === 'number') result.timeout = entry.timeout;
        return { name, ...result } as McpServerRegistration;
      }
      return { name, ...entry } as McpServerRegistration;
    },
  });
}

/**
 * MiMo Code adapter — OpenCode fork sharing the same MCP config schema
 * (type:'remote'/url for HTTP; type:'local'/command[] for stdio).
 * Write: ~/.config/mimocode/mimocode.json; read lower-priority config.json and
 * project-local .mimocode/mimocode.json for existing installs.
 */
export function mimocodeMcpAdapter(
  configPath = '.config/mimocode/mimocode.json',
  legacyReadPaths = ['.config/mimocode/config.json', '.mimocode/mimocode.json']
) {
  return opencodeMcpAdapter(configPath, legacyReadPaths);
}

/**
 * Copilot adapter — injects `tools: ['*']` on write; strips it on read.
 * Write: ~/.copilot/mcp-config.json; legacy read: ~/.config/github-copilot/mcp.json.
 */
export function copilotMcpAdapter(
  configPath = '.copilot/mcp-config.json',
  legacyReadPaths = ['.config/github-copilot/mcp.json']
) {
  return createMcpAdapter({
    configPath,
    legacyReadPaths,
    format: 'json',
    serversKey: 'mcpServers',
    toNative(s) {
      const { name: _n, ...rest } = s;
      const entry = deepClone(rest) as Record<string, unknown>;
      if (!('tools' in entry)) entry.tools = ['*'];
      return entry;
    },
    fromNative(name, raw) {
      const entry = deepClone(raw) as Record<string, unknown>;
      if (Array.isArray(entry.tools) && entry.tools.length === 1 && entry.tools[0] === '*') {
        delete entry.tools;
      }
      return { name, ...entry } as McpServerRegistration;
    },
  });
}

/**
 * Droid (Factory AI) adapter — passthrough, uses mcpServers JSON key.
 * Write: ~/.factory/mcp.json; legacy read: old Droid/Factory config paths.
 */
export function droidMcpAdapter(
  configPath = '.factory/mcp.json',
  legacyReadPaths = ['.droid/settings.json', '.factory/config.json']
) {
  return passthroughMcpAdapter(configPath, legacyReadPaths);
}

/**
 * Amp adapter — passthrough, uses the literal `amp.mcpServers` JSON key.
 * Write: ~/.config/amp/settings.json; legacy read: ~/.amp/config.json.
 */
export function ampMcpAdapter(
  configPath = '.config/amp/settings.json',
  legacyReadPaths = ['.amp/config.json']
) {
  return createMcpAdapter({
    configPath,
    legacyReadPaths,
    legacyServersKey: 'mcpServers',
    format: 'json',
    serversKey: 'amp.mcpServers',
    serversKeyIsLiteral: true,
    toNative(s) {
      const { name: _n, ...rest } = s;
      return rest as Record<string, unknown>;
    },
    fromNative(name, raw) {
      return { name, ...raw } as McpServerRegistration;
    },
  });
}

/**
 * Crush adapter — passthrough, uses the `mcp` JSON key.
 * Write: ~/.config/crush/crush.json.
 */
export function crushMcpAdapter(configPath = '.config/crush/crush.json') {
  return createMcpAdapter({
    configPath,
    format: 'json',
    serversKey: 'mcp',
    toNative(s) {
      const { name: _n, transport: _transport, ...rest } = s;
      const entry = rest as Record<string, unknown>;
      if (!('type' in entry) && _transport) {
        entry.type = _transport;
      }
      return entry;
    },
    fromNative(name, raw) {
      return { name, ...raw } as McpServerRegistration;
    },
  });
}
