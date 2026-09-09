import { readFile } from 'node:fs/promises';
import type { Secret } from '@emdash/shared';
import ssh2, { type BaseAgent, type ConnectConfig } from 'ssh2';
import type { SshConfig } from '@core/primitives/ssh/api';
import { sshConfigFromRow } from '@core/primitives/ssh/api';
import type { SshConnectionRow } from '@core/services/app-db/node/schema';
import {
  resolveSshConfig as defaultResolveSshConfig,
  type ResolvedSshConfig,
} from '../config/resolve-ssh-config';
import { findSshConfigHostByHostName, parseSshConfigFile } from '../config/sshConfigParser';
import {
  spawnProxyCommand as defaultSpawnProxyCommand,
  spawnProxyJump as defaultSpawnProxyJump,
  type ProxyTokens,
  type TransportResult,
} from '../transport/transports';
import { buildAuthConfig, resolveManualAgentSshConfig } from './ssh-connect-auth';
import { applyForwardAgent } from './ssh-connect-forward-agent';

const { createAgent } = ssh2;

export interface SshConnectResult {
  config: ConnectConfig;
  cleanup: () => void;
  debugLogs: string[];
}

export type PersistedConnectInput = { kind: 'persisted'; row: SshConnectionRow };
export type TransientConnectInput = {
  kind: 'transient';
  config: SshConfig & { password?: string; passphrase?: string };
};
export type SshConnectInput = PersistedConnectInput | TransientConnectInput;

export interface SshConnectDeps {
  readFile: (path: string, encoding: BufferEncoding) => Promise<string>;
  getPassword: (connectionId: string) => Promise<Secret<string> | null>;
  getPassphrase: (connectionId: string) => Promise<Secret<string> | null>;
  resolveSshConfig: (alias: string) => Promise<ResolvedSshConfig>;
  findSshConfigByHostName: (hostname: string) => Promise<ResolvedSshConfig | undefined>;
  spawnProxyCommand: (command: string, tokens: ProxyTokens) => Omit<TransportResult, 'process'>;
  spawnProxyJump: (
    jumpSpec: string,
    destHost: string,
    destPort: number
  ) => Omit<TransportResult, 'process'>;
  createAgent: (socketPath: string) => BaseAgent;
  env: Record<string, string | undefined>;
}

function defaultDeps(): SshConnectDeps {
  return {
    readFile,
    getPassword: async () => {
      throw new Error('Password lookup dependency was not provided');
    },
    getPassphrase: async () => {
      throw new Error('Passphrase lookup dependency was not provided');
    },
    resolveSshConfig: (alias) => defaultResolveSshConfig(alias),
    findSshConfigByHostName: async (hostname) => {
      const hosts = await parseSshConfigFile();
      const match = findSshConfigHostByHostName(hosts, hostname);
      return match ? await defaultResolveSshConfig(match.host).catch(() => undefined) : undefined;
    },
    spawnProxyCommand: (command, tokens) => defaultSpawnProxyCommand(command, tokens),
    spawnProxyJump: (jumpSpec, destHost, destPort) =>
      defaultSpawnProxyJump(jumpSpec, destHost, destPort),
    createAgent,
    env: process.env,
  };
}

function baseConfigForInput(input: SshConnectInput): SshConfig {
  return input.kind === 'persisted' ? sshConfigFromRow(input.row) : input.config;
}

export async function resolveSshConnectConfig(
  input: SshConnectInput,
  depsOverride: Partial<SshConnectDeps> = {}
): Promise<SshConnectResult> {
  const deps = { ...defaultDeps(), ...depsOverride };
  const base = baseConfigForInput(input);
  const alias = base.sshConfigAlias;
  const resolved = alias ? await deps.resolveSshConfig(alias) : undefined;
  const shouldResolveHostForAgent = !alias && base.authType === 'agent';
  const agentResolved = shouldResolveHostForAgent
    ? await resolveManualAgentSshConfig(base.host, deps)
    : resolved;

  const host = resolved?.hostname || base.host;
  const port = resolved?.port ?? base.port;
  const username = resolved?.user || base.username;
  const authResult = await buildAuthConfig(input, base, agentResolved, deps);

  const config: ConnectConfig = {
    host,
    port,
    username,
    readyTimeout:
      resolved?.connectTimeout !== undefined
        ? resolved.connectTimeout * 1000
        : input.kind === 'transient'
          ? 10_000
          : 20_000,
    keepaliveInterval: resolved?.serverAliveInterval ? resolved.serverAliveInterval * 1000 : 60_000,
    keepaliveCountMax: resolved?.serverAliveCountMax ?? 3,
    ...authResult.config,
  };

  const forwardAgent = resolved?.forwardAgent ?? base.forwardAgent === true;
  applyForwardAgent(config, forwardAgent, agentResolved, authResult, deps);

  let debugLogs: string[] = [];
  let cleanup = () => {};
  const tokens: ProxyTokens = { host, port, username, originalHost: alias ?? base.host };
  const proxyCommand = alias ? resolved?.proxyCommand : undefined;
  const proxyJump = resolved?.proxyJump ?? (!alias ? base.proxyJump : undefined);

  let transport: Omit<TransportResult, 'process'> | undefined;
  if (proxyCommand) {
    transport = deps.spawnProxyCommand(proxyCommand, tokens);
  } else if (proxyJump) {
    transport = deps.spawnProxyJump(proxyJump, host, port);
  }

  if (transport) {
    config.sock = transport.sock;
    cleanup = transport.cleanup;
    debugLogs = transport.debugLogs;
  }

  return { config, cleanup, debugLogs };
}

export function createSshConnectConfigResolver(deps: SshConnectDeps) {
  return async (input: SshConnectInput): Promise<SshConnectResult> =>
    await resolveSshConnectConfig(input, deps);
}
