import { Readable, Writable } from 'node:stream';
import type { Agent } from '@agentclientprotocol/sdk';
import type { AcpClientFactory } from '@emdash/core/services/agent-plugins/api/plugins';
import { describe, expect, it, vi } from 'vitest';
import { pluginRegistry } from '../../registry';

describe('codex acp capability', () => {
  it('declares acp: { kind: supported }', () => {
    const codex = pluginRegistry.get('codex');
    expect(codex).toBeDefined();
    expect(codex!.capabilities.acp.kind).toBe('supported');
  });
});

describe('codex acp behavior', () => {
  const codex = () => pluginRegistry.get('codex')!;
  const acpBehavior = () => codex().behavior.acp!;

  it('behavior.acp is defined', () => {
    expect(acpBehavior()).toBeDefined();
  });

  it('registers Codex transcript enrichment', () => {
    expect(typeof acpBehavior().enrich).toBe('function');
  });

  describe('buildSpawn', () => {
    const spawnCtx = { cwd: '/home/user/worktrees/task-1', env: {}, cli: '/usr/local/bin/codex' };

    it('passes CODEX_PATH from ctx.cli', () => {
      const result = acpBehavior().buildSpawn(spawnCtx);
      expect(result.env?.CODEX_PATH).toBe('/usr/local/bin/codex');
    });

    it('sets ELECTRON_RUN_AS_NODE=1', () => {
      const result = acpBehavior().buildSpawn({ ...spawnCtx, cli: '/x/codex' });
      expect(result.env?.ELECTRON_RUN_AS_NODE).toBe('1');
    });

    it('uses process.execPath as command', () => {
      const result = acpBehavior().buildSpawn(spawnCtx);
      expect(result.command).toBe(process.execPath);
    });

    it('provides a non-empty args array pointing at the adapter entry', () => {
      const result = acpBehavior().buildSpawn(spawnCtx);
      expect(result.args.length).toBeGreaterThan(0);
      expect(result.args[0]).toContain('codex-acp');
    });
  });

  describe('connect', () => {
    it('returns an object with prompt and newSession methods', () => {
      const stdin = new Writable({ write: (_c, _e, cb) => cb() });
      const stdout = new Readable({ read: () => {} });

      const toClient: AcpClientFactory = () => ({
        requestPermission: vi.fn(),
        sessionUpdate: vi.fn(),
      });

      const agentApi = acpBehavior().connect({ stdin, stdout }, toClient);
      expect(typeof (agentApi as Agent).prompt).toBe('function');
      expect(typeof (agentApi as Agent).newSession).toBe('function');
      expect(typeof (agentApi as Agent).initialize).toBe('function');
    });
  });
});
