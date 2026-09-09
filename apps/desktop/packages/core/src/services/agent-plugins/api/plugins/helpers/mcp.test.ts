import { parse as parseTOML } from 'smol-toml';
import { describe, expect, it } from 'vitest';
import type { PluginFs } from '#primitives/plugin-fs/api';
import {
  ampMcpAdapter,
  codexMcpAdapter,
  createMcpAdapter,
  crushMcpAdapter,
  droidMcpAdapter,
  grokMcpAdapter,
  mimocodeMcpAdapter,
  opencodeMcpAdapter,
  passthroughMcpAdapter,
} from './mcp';

// ── In-memory PluginFs ───────────────────────────────────────────────────────

function createMemoryFs(initial: Record<string, string> = {}): PluginFs {
  const store = new Map<string, string>(Object.entries(initial));
  return {
    async read(path) {
      return store.get(path) ?? null;
    },
    async write(path, content) {
      store.set(path, content);
    },
    async delete(path) {
      store.delete(path);
    },
    async exists(path) {
      return store.has(path);
    },
    async list() {
      return [];
    },
  };
}

function jsonFile(data: unknown): string {
  return JSON.stringify(data, null, 2) + '\n';
}

// ── createMcpAdapter (single path) ──────────────────────────────────────────

describe('createMcpAdapter (single path)', () => {
  const adapter = passthroughMcpAdapter('.test/mcp.json');

  it('readServers returns [] when file does not exist', async () => {
    const fs = createMemoryFs();
    expect(await adapter.readServers(fs)).toEqual([]);
  });

  it('readServers parses existing servers', async () => {
    const fs = createMemoryFs({
      '.test/mcp.json': jsonFile({ mcpServers: { s1: { command: 'npx' } } }),
    });
    const result = await adapter.readServers(fs);
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('s1');
    expect(result[0].command).toBe('npx');
  });

  it('writeServers preserves unrelated top-level keys', async () => {
    const fs = createMemoryFs({
      '.test/mcp.json': jsonFile({ mcpServers: {}, otherKey: 'preserved' }),
    });
    await adapter.writeServers(fs, [{ name: 'new', command: 'x' }]);
    const raw = await fs.read('.test/mcp.json');
    const parsed = JSON.parse(raw!) as Record<string, unknown>;
    expect(parsed.otherKey).toBe('preserved');
    expect((parsed.mcpServers as Record<string, unknown>).new).toBeDefined();
  });

  it('removeServer removes only the named server', async () => {
    const fs = createMemoryFs({
      '.test/mcp.json': jsonFile({
        mcpServers: { keep: { command: 'x' }, gone: { command: 'y' } },
      }),
    });
    await adapter.removeServer(fs, 'gone');
    const result = await adapter.readServers(fs);
    expect(result.map((r) => r.name)).toEqual(['keep']);
  });
});

// ── legacyReadPaths: merge semantics ────────────────────────────────────────

describe('createMcpAdapter with legacyReadPaths', () => {
  const adapter = passthroughMcpAdapter('.canonical/mcp.json', ['.legacy/mcp.json']);

  it('readServers returns servers from both paths', async () => {
    const fs = createMemoryFs({
      '.canonical/mcp.json': jsonFile({ mcpServers: { canonical: { command: 'c' } } }),
      '.legacy/mcp.json': jsonFile({ mcpServers: { legacy: { command: 'l' } } }),
    });
    const result = await adapter.readServers(fs);
    const names = result.map((r) => r.name).sort();
    expect(names).toEqual(['canonical', 'legacy']);
  });

  it('canonical path wins when name conflicts with legacy', async () => {
    const fs = createMemoryFs({
      '.canonical/mcp.json': jsonFile({ mcpServers: { shared: { command: 'canonical-cmd' } } }),
      '.legacy/mcp.json': jsonFile({ mcpServers: { shared: { command: 'legacy-cmd' } } }),
    });
    const result = await adapter.readServers(fs);
    expect(result).toHaveLength(1);
    expect(result[0].command).toBe('canonical-cmd');
  });

  it('writeServers writes only the canonical path', async () => {
    const fs = createMemoryFs({
      '.legacy/mcp.json': jsonFile({ mcpServers: { old: { command: 'l' } } }),
    });
    await adapter.writeServers(fs, [{ name: 'new', command: 'c' }]);
    expect(await fs.read('.canonical/mcp.json')).not.toBeNull();
    // Legacy file unchanged
    const legacy = JSON.parse((await fs.read('.legacy/mcp.json'))!) as Record<string, unknown>;
    expect((legacy.mcpServers as Record<string, unknown>).old).toBeDefined();
  });

  it('removeServer removes from canonical and all legacy paths', async () => {
    const fs = createMemoryFs({
      '.canonical/mcp.json': jsonFile({
        mcpServers: { gone: { command: 'c' }, keep: { command: 'k' } },
      }),
      '.legacy/mcp.json': jsonFile({ mcpServers: { gone: { command: 'l' } } }),
    });
    await adapter.removeServer(fs, 'gone');
    const canonical = await adapter.readServers(fs);
    expect(canonical.map((r) => r.name)).toEqual(['keep']);
    const legacyContent = await fs.read('.legacy/mcp.json');
    const legacyParsed = JSON.parse(legacyContent!) as Record<string, unknown>;
    expect((legacyParsed.mcpServers as Record<string, unknown>).gone).toBeUndefined();
  });

  it('removeServer is a no-op if server does not exist in either path', async () => {
    const fs = createMemoryFs({
      '.canonical/mcp.json': jsonFile({ mcpServers: { keep: { command: 'k' } } }),
    });
    await expect(adapter.removeServer(fs, 'missing')).resolves.not.toThrow();
    const result = await adapter.readServers(fs);
    expect(result).toHaveLength(1);
  });

  it('handles missing canonical file gracefully on read', async () => {
    const fs = createMemoryFs({
      '.legacy/mcp.json': jsonFile({ mcpServers: { s: { command: 'x' } } }),
    });
    const result = await adapter.readServers(fs);
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('s');
  });

  it('handles malformed legacy file gracefully (ignores it)', async () => {
    const fs = createMemoryFs({
      '.canonical/mcp.json': jsonFile({ mcpServers: { good: { command: 'c' } } }),
      '.legacy/mcp.json': 'not valid json { }{{',
    });
    const result = await adapter.readServers(fs);
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('good');
  });
});

// ── Multi-legacy paths ───────────────────────────────────────────────────────

describe('createMcpAdapter with multiple legacyReadPaths', () => {
  const adapter = createMcpAdapter({
    configPath: '.canon/mcp.json',
    legacyReadPaths: ['.legacy1/mcp.json', '.legacy2/mcp.json'],
    format: 'json',
    serversKey: 'mcpServers',
    toNative(s) {
      const { name: _n, ...r } = s;
      return r as Record<string, unknown>;
    },
    fromNative(name, raw) {
      return { name, ...raw };
    },
  });

  it('reads servers from all three paths', async () => {
    const fs = createMemoryFs({
      '.canon/mcp.json': jsonFile({ mcpServers: { a: { command: 'a' } } }),
      '.legacy1/mcp.json': jsonFile({ mcpServers: { b: { command: 'b' } } }),
      '.legacy2/mcp.json': jsonFile({ mcpServers: { c: { command: 'c' } } }),
    });
    const result = await adapter.readServers(fs);
    expect(result.map((r) => r.name).sort()).toEqual(['a', 'b', 'c']);
  });

  it('removes from all paths', async () => {
    const fs = createMemoryFs({
      '.canon/mcp.json': jsonFile({ mcpServers: { gone: { command: 'a' } } }),
      '.legacy1/mcp.json': jsonFile({ mcpServers: { gone: { command: 'b' } } }),
      '.legacy2/mcp.json': jsonFile({ mcpServers: { gone: { command: 'c' } } }),
    });
    await adapter.removeServer(fs, 'gone');
    for (const path of ['.canon/mcp.json', '.legacy1/mcp.json', '.legacy2/mcp.json']) {
      const content = await fs.read(path);
      if (!content) continue;
      const parsed = JSON.parse(content) as Record<string, unknown>;
      expect((parsed.mcpServers as Record<string, unknown>).gone).toBeUndefined();
    }
  });
});

// ── Droid adapter ───────────────────────────────────────────────────────────

describe('droidMcpAdapter', () => {
  const adapter = droidMcpAdapter();

  it('writes Factory MCP config to the documented path', async () => {
    const fs = createMemoryFs();

    await adapter.writeServers(fs, [{ name: 'filesystem', command: 'npx' }]);

    const raw = await fs.read('.factory/mcp.json');
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!) as Record<string, unknown>;
    expect(parsed.mcpServers).toEqual({ filesystem: { command: 'npx' } });
    expect(await fs.read('.droid/settings.json')).toBeNull();
  });

  it('reads legacy Droid and Factory config paths', async () => {
    const fs = createMemoryFs({
      '.droid/settings.json': jsonFile({ mcpServers: { droidLegacy: { command: 'd' } } }),
      '.factory/config.json': jsonFile({ mcpServers: { factoryLegacy: { command: 'f' } } }),
    });

    const result = await adapter.readServers(fs);

    expect(result.map((server) => server.name).sort()).toEqual(['droidLegacy', 'factoryLegacy']);
  });
});

// ── Amp adapter ─────────────────────────────────────────────────────────────

describe('ampMcpAdapter', () => {
  const adapter = ampMcpAdapter();

  it('writes MCP servers to the literal amp.mcpServers key and preserves user settings', async () => {
    const fs = createMemoryFs({
      '.config/amp/settings.json': jsonFile({
        'amp.commands.allowlist': ['pnpm'],
        'amp.tools.disable': ['web_search'],
        'amp.mcpServers': { existing: { command: 'existing-server' } },
      }),
    });

    await adapter.writeServers(fs, [
      { name: 'filesystem', command: 'npx', args: ['-y', '@mcp/server'] },
    ]);

    const raw = await fs.read('.config/amp/settings.json');
    const parsed = JSON.parse(raw!) as Record<string, unknown>;

    expect(parsed['amp.commands.allowlist']).toEqual(['pnpm']);
    expect(parsed['amp.tools.disable']).toEqual(['web_search']);
    expect(parsed.amp).toBeUndefined();
    expect(parsed['amp.mcpServers']).toEqual({
      filesystem: { command: 'npx', args: ['-y', '@mcp/server'] },
    });
  });

  it('reads MCP servers from the literal amp.mcpServers key', async () => {
    const fs = createMemoryFs({
      '.config/amp/settings.json': jsonFile({
        'amp.mcpServers': { docs: { url: 'https://example.com/mcp', type: 'http' } },
      }),
    });

    await expect(adapter.readServers(fs)).resolves.toEqual([
      { name: 'docs', url: 'https://example.com/mcp', type: 'http' },
    ]);
  });

  it('reads MCP servers from the legacy mcpServers key', async () => {
    const fs = createMemoryFs({
      '.amp/config.json': jsonFile({
        mcpServers: { legacy: { command: 'legacy-server' } },
      }),
    });

    await expect(adapter.readServers(fs)).resolves.toEqual([
      { name: 'legacy', command: 'legacy-server' },
    ]);
  });

  it('removes MCP servers from canonical and legacy keys', async () => {
    const fs = createMemoryFs({
      '.config/amp/settings.json': jsonFile({
        'amp.mcpServers': { gone: { command: 'canonical-server' } },
      }),
      '.amp/config.json': jsonFile({
        mcpServers: { gone: { command: 'legacy-server' } },
      }),
    });

    await adapter.removeServer(fs, 'gone');

    const canonical = JSON.parse((await fs.read('.config/amp/settings.json'))!) as Record<
      string,
      unknown
    >;
    const legacy = JSON.parse((await fs.read('.amp/config.json'))!) as Record<string, unknown>;
    expect(canonical['amp.mcpServers']).toEqual({});
    expect(legacy.mcpServers).toEqual({});
  });
});

// ── Codex TOML adapter ──────────────────────────────────────────────────────

describe('codexMcpAdapter', () => {
  const adapter = codexMcpAdapter('.codex/config.toml');

  it('maps HTTP headers to Codex http_headers on write', async () => {
    const fs = createMemoryFs({
      '.codex/config.toml': 'model = "gpt-5"\n',
    });

    await adapter.writeServers(fs, [
      {
        name: 'docs',
        transport: 'http',
        type: 'http',
        url: 'https://example.com/mcp',
        headers: { Authorization: 'Bearer token' },
      },
    ]);

    const raw = await fs.read('.codex/config.toml');
    const parsed = parseTOML(raw!) as Record<string, unknown>;
    const servers = parsed.mcp_servers as Record<string, Record<string, unknown>>;

    expect(parsed.model).toBe('gpt-5');
    expect(servers.docs.url).toBe('https://example.com/mcp');
    expect(servers.docs.type).toBeUndefined();
    expect(servers.docs.transport).toBeUndefined();
    expect(servers.docs.headers).toBeUndefined();
    expect(servers.docs.http_headers).toEqual({ Authorization: 'Bearer token' });
  });

  it('reads Codex HTTP headers into the canonical headers field', async () => {
    const fs = createMemoryFs({
      '.codex/config.toml': [
        '[mcp_servers.docs]',
        'url = "https://example.com/mcp"',
        '',
        '[mcp_servers.docs.http_headers]',
        'Authorization = "Bearer token"',
      ].join('\n'),
    });

    const result = await adapter.readServers(fs);

    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      name: 'docs',
      transport: 'http',
      type: 'http',
      url: 'https://example.com/mcp',
      headers: { Authorization: 'Bearer token' },
    });
    expect(result[0].http_headers).toBeUndefined();
  });
});

// ── Grok TOML adapter ───────────────────────────────────────────────────────

describe('grokMcpAdapter', () => {
  const adapter = grokMcpAdapter('.grok/config.toml');

  it('writes stdio servers with command/args/env and enabled=true, preserving config', async () => {
    const fs = createMemoryFs({
      '.grok/config.toml': '[models]\ndefault = "grok-build"\n',
    });

    await adapter.writeServers(fs, [
      {
        name: 'postgres',
        command: 'npx',
        args: ['-y', '@modelcontextprotocol/server-postgres'],
        env: { DATABASE_URL: 'postgres://localhost/mydb' },
      },
    ]);

    const raw = await fs.read('.grok/config.toml');
    const parsed = parseTOML(raw!) as Record<string, unknown>;
    const servers = parsed.mcp_servers as Record<string, Record<string, unknown>>;

    expect((parsed.models as Record<string, unknown>).default).toBe('grok-build');
    expect(servers.postgres).toEqual({
      command: 'npx',
      args: ['-y', '@modelcontextprotocol/server-postgres'],
      env: { DATABASE_URL: 'postgres://localhost/mydb' },
      enabled: true,
    });
  });

  it('writes HTTP servers with url/headers, keeping the canonical headers key', async () => {
    const fs = createMemoryFs();

    await adapter.writeServers(fs, [
      {
        name: 'sentry',
        transport: 'http',
        type: 'http',
        url: 'https://mcp.sentry.dev/mcp',
        headers: { Authorization: 'Bearer tok' },
      },
    ]);

    const raw = await fs.read('.grok/config.toml');
    const parsed = parseTOML(raw!) as Record<string, unknown>;
    const servers = parsed.mcp_servers as Record<string, Record<string, unknown>>;

    expect(servers.sentry).toEqual({
      url: 'https://mcp.sentry.dev/mcp',
      headers: { Authorization: 'Bearer tok' },
      enabled: true,
    });
    expect(servers.sentry.type).toBeUndefined();
    expect(servers.sentry.transport).toBeUndefined();
    expect(servers.sentry.http_headers).toBeUndefined();
  });

  it('preserves an explicit enabled=false', async () => {
    const fs = createMemoryFs();

    await adapter.writeServers(fs, [{ name: 'off', command: 'node', enabled: false }]);

    const parsed = parseTOML((await fs.read('.grok/config.toml'))!) as Record<string, unknown>;
    const servers = parsed.mcp_servers as Record<string, Record<string, unknown>>;
    expect(servers.off.enabled).toBe(false);
  });

  it('reads stdio and http servers, inferring transport from url presence', async () => {
    const fs = createMemoryFs({
      '.grok/config.toml': [
        '[mcp_servers.postgres]',
        'command = "npx"',
        'args = ["-y", "@modelcontextprotocol/server-postgres"]',
        'enabled = true',
        '',
        '[mcp_servers.postgres.env]',
        'DATABASE_URL = "postgres://localhost/mydb"',
        '',
        '[mcp_servers.sentry]',
        'url = "https://mcp.sentry.dev/mcp"',
        'enabled = true',
        '',
        '[mcp_servers.sentry.headers]',
        'Authorization = "Bearer tok"',
      ].join('\n'),
    });

    const result = await adapter.readServers(fs);

    expect(result).toContainEqual({
      name: 'postgres',
      command: 'npx',
      args: ['-y', '@modelcontextprotocol/server-postgres'],
      enabled: true,
      env: { DATABASE_URL: 'postgres://localhost/mydb' },
    });
    expect(result).toContainEqual({
      name: 'sentry',
      transport: 'http',
      type: 'http',
      url: 'https://mcp.sentry.dev/mcp',
      enabled: true,
      headers: { Authorization: 'Bearer tok' },
    });
  });

  it('round-trips a server read then written back', async () => {
    const fs = createMemoryFs({
      '.grok/config.toml': [
        '[mcp_servers.docs]',
        'url = "https://example.com/mcp"',
        'enabled = true',
      ].join('\n'),
    });

    const servers = await adapter.readServers(fs);
    await adapter.writeServers(fs, servers);

    const parsed = parseTOML((await fs.read('.grok/config.toml'))!) as Record<string, unknown>;
    const written = parsed.mcp_servers as Record<string, Record<string, unknown>>;
    expect(written.docs).toEqual({
      url: 'https://example.com/mcp',
      enabled: true,
    });
  });

  it('removes only the named server', async () => {
    const fs = createMemoryFs({
      '.grok/config.toml': [
        '[mcp_servers.keep]',
        'command = "k"',
        'enabled = true',
        '',
        '[mcp_servers.gone]',
        'command = "g"',
        'enabled = true',
      ].join('\n'),
    });

    await adapter.removeServer(fs, 'gone');

    const result = await adapter.readServers(fs);
    expect(result.map((r) => r.name)).toEqual(['keep']);
  });
});

// ── OpenCode adapter ────────────────────────────────────────────────────────

describe('opencodeMcpAdapter', () => {
  const adapter = opencodeMcpAdapter('.config/opencode/opencode.json');

  it('writes local servers using OpenCode environment and enabled fields', async () => {
    const fs = createMemoryFs();

    await adapter.writeServers(fs, [
      {
        name: 'playwright',
        command: 'npx',
        args: ['-y', '@playwright/mcp'],
        env: { BROWSER: 'chromium' },
        enabled: false,
        cwd: './tools',
        timeout: 10_000,
      },
    ]);

    const raw = await fs.read('.config/opencode/opencode.json');
    const parsed = JSON.parse(raw!) as {
      mcp: Record<string, Record<string, unknown>>;
    };

    expect(parsed.mcp.playwright).toEqual({
      type: 'local',
      command: ['npx', '-y', '@playwright/mcp'],
      enabled: false,
      environment: { BROWSER: 'chromium' },
      cwd: './tools',
      timeout: 10_000,
    });
  });

  it('reads current OpenCode server fields', async () => {
    const fs = createMemoryFs({
      '.config/opencode/opencode.json': jsonFile({
        mcp: {
          local: {
            type: 'local',
            command: ['npx', '-y', '@local/mcp'],
            enabled: false,
            environment: { LOCAL: '1' },
            cwd: './mcp',
            timeout: 20_000,
          },
          remote: {
            type: 'remote',
            url: 'https://example.com/mcp',
            enabled: false,
            headers: { Authorization: 'Bearer token' },
            oauth: false,
            timeout: 30_000,
          },
          inherited: { enabled: false },
        },
      }),
    });

    const result = await adapter.readServers(fs);

    expect(result).toContainEqual({
      name: 'local',
      command: 'npx',
      args: ['-y', '@local/mcp'],
      enabled: false,
      env: { LOCAL: '1' },
      cwd: './mcp',
      timeout: 20_000,
    });
    expect(result).toContainEqual({
      name: 'remote',
      type: 'http',
      url: 'https://example.com/mcp',
      enabled: false,
      headers: { Authorization: 'Bearer token' },
      oauth: false,
      timeout: 30_000,
    });
    expect(result).toContainEqual({ name: 'inherited', enabled: false });

    await adapter.writeServers(fs, result);

    const raw = await fs.read('.config/opencode/opencode.json');
    const parsed = JSON.parse(raw!) as {
      mcp: Record<string, Record<string, unknown>>;
    };
    expect(parsed.mcp.inherited).toEqual({ enabled: false });
  });

  it('prefers canonical environment when reading local OpenCode servers', async () => {
    const fs = createMemoryFs({
      '.config/opencode/opencode.json': jsonFile({
        mcp: {
          local: {
            type: 'local',
            command: ['npx', '-y', '@local/mcp'],
            env: { LEGACY: '1' },
            environment: { CANONICAL: '1' },
          },
        },
      }),
    });

    const result = await adapter.readServers(fs);

    expect(result).toContainEqual({
      name: 'local',
      command: 'npx',
      args: ['-y', '@local/mcp'],
      env: { CANONICAL: '1' },
    });
  });
});

// ── MiMo Code adapter ───────────────────────────────────────────────────────

describe('mimocodeMcpAdapter', () => {
  const adapter = mimocodeMcpAdapter();

  it('writes global MiMo Code MCP config using the OpenCode-compatible schema', async () => {
    const fs = createMemoryFs();

    await adapter.writeServers(fs, [
      {
        name: 'playwright',
        command: 'npx',
        args: ['-y', '@playwright/mcp'],
        env: { BROWSER: 'chromium' },
        enabled: false,
      },
      {
        name: 'docs',
        transport: 'http',
        type: 'http',
        url: 'https://example.com/mcp',
        headers: { Authorization: 'Bearer token' },
        timeout: 30_000,
      },
    ]);

    const raw = await fs.read('.config/mimocode/mimocode.json');
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!) as { mcp: Record<string, Record<string, unknown>> };

    expect(parsed.mcp.playwright).toEqual({
      type: 'local',
      command: ['npx', '-y', '@playwright/mcp'],
      enabled: false,
      environment: { BROWSER: 'chromium' },
    });
    expect(parsed.mcp.docs).toEqual({
      type: 'remote',
      url: 'https://example.com/mcp',
      enabled: true,
      headers: {
        Authorization: 'Bearer token',
        Accept: 'application/json, text/event-stream',
      },
      timeout: 30_000,
    });
  });

  it('reads lower-priority MiMo Code config paths', async () => {
    const fs = createMemoryFs({
      '.config/mimocode/config.json': jsonFile({
        mcp: {
          globalLegacy: {
            type: 'local',
            command: ['node', 'server.js'],
          },
        },
      }),
      '.mimocode/mimocode.json': jsonFile({
        mcp: {
          local: {
            type: 'local',
            command: ['npx', '-y', '@local/mcp'],
            environment: { LOCAL: '1' },
          },
        },
      }),
    });

    await expect(adapter.readServers(fs)).resolves.toEqual([
      {
        name: 'globalLegacy',
        command: 'node',
        args: ['server.js'],
      },
      {
        name: 'local',
        command: 'npx',
        args: ['-y', '@local/mcp'],
        env: { LOCAL: '1' },
      },
    ]);
  });
});

// ── Crush adapter ───────────────────────────────────────────────────────────

describe('crushMcpAdapter', () => {
  const adapter = crushMcpAdapter('.config/crush/crush.json');

  it('writes servers under the mcp key and preserves unrelated config', async () => {
    const fs = createMemoryFs({
      '.config/crush/crush.json': jsonFile({ options: { debug: true } }),
    });

    await adapter.writeServers(fs, [
      {
        name: 'docs',
        transport: 'http',
        type: 'http',
        url: 'https://example.com/mcp',
        headers: { Authorization: 'Bearer $TOKEN' },
      },
    ]);

    const raw = await fs.read('.config/crush/crush.json');
    const parsed = JSON.parse(raw!) as Record<string, unknown>;
    const servers = parsed.mcp as Record<string, Record<string, unknown>>;

    expect(parsed.options).toEqual({ debug: true });
    expect(servers.docs).toEqual({
      type: 'http',
      url: 'https://example.com/mcp',
      headers: { Authorization: 'Bearer $TOKEN' },
    });
  });

  it('maps transport to type when writing servers without a type', async () => {
    const fs = createMemoryFs({});

    await adapter.writeServers(fs, [
      {
        name: 'docs',
        transport: 'http',
        url: 'https://example.com/mcp',
      },
    ]);

    const raw = await fs.read('.config/crush/crush.json');
    const parsed = JSON.parse(raw!) as Record<string, unknown>;
    const servers = parsed.mcp as Record<string, Record<string, unknown>>;

    expect(servers.docs).toEqual({
      type: 'http',
      url: 'https://example.com/mcp',
    });
  });

  it('reads stdio and http servers from the mcp key', async () => {
    const fs = createMemoryFs({
      '.config/crush/crush.json': jsonFile({
        mcp: {
          local: { type: 'stdio', command: 'node', args: ['server.js'] },
          remote: { type: 'http', url: 'https://example.com/mcp' },
        },
      }),
    });

    await expect(adapter.readServers(fs)).resolves.toEqual([
      { name: 'local', type: 'stdio', command: 'node', args: ['server.js'] },
      { name: 'remote', type: 'http', url: 'https://example.com/mcp' },
    ]);
  });
});
