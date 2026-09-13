// Auth assembly: password, key, and agent selection with IdentitiesOnly filtering.
import ssh2, {
  type BaseAgent,
  type ConnectConfig,
  type IdentityCallback,
  type ParsedKey,
  type PublicKeyEntry,
  type SignCallback,
  type SigningRequestOptions,
} from 'ssh2';
import type { SshConfig } from '@core/primitives/ssh/api';
import {
  resolveAgentSocketFromResolved,
  type ResolvedSshConfig,
} from '../config/resolve-ssh-config';
import type { SshConnectDeps, SshConnectInput } from './resolve-ssh-connect-config';

const { utils } = ssh2;

export interface AuthResult {
  config: Partial<ConnectConfig>;
  agentSocketPath?: string;
}

function expandTilde(filePath: string): string {
  if (filePath === '~') return process.env.HOME ?? filePath;
  if (filePath.startsWith('~/')) return `${process.env.HOME ?? ''}${filePath.slice(1)}`;
  return filePath;
}

type AgentPublicKey = ParsedKey | Buffer | string | PublicKeyEntry;

function comparablePublicKey(key: AgentPublicKey): ParsedKey | Buffer | string {
  if (typeof key === 'object' && 'pubKey' in key) {
    const pubKey = key.pubKey;
    if (typeof pubKey === 'object' && 'pubKey' in pubKey) {
      return pubKey.pubKey;
    }
    return pubKey;
  }
  return key;
}

class IdentityFilteredAgent implements BaseAgent {
  readonly kind = 'identity-filtered-agent';
  declare getStream?: BaseAgent['getStream'];

  constructor(
    readonly socketPath: string,
    private readonly agent: BaseAgent,
    private readonly allowedKeys: ParsedKey[]
  ) {
    if (agent.getStream) {
      this.getStream = agent.getStream.bind(agent);
    }
  }

  getIdentities(callback: IdentityCallback): void {
    this.agent.getIdentities((error, keys) => {
      if (error) {
        callback(error);
        return;
      }
      callback(
        undefined,
        keys?.filter((key) =>
          this.allowedKeys.some((allowedKey) => allowedKey.equals(comparablePublicKey(key)))
        ) ?? []
      );
    });
  }

  sign(
    pubKey: string | Buffer | ParsedKey,
    data: Buffer,
    optionsOrCallback?: SigningRequestOptions | SignCallback,
    callback?: SignCallback
  ): void {
    if (typeof optionsOrCallback === 'function') {
      this.agent.sign(pubKey, data, optionsOrCallback);
      return;
    }
    this.agent.sign(pubKey, data, optionsOrCallback ?? {}, callback);
  }
}

async function readIdentityKey(path: string, deps: SshConnectDeps): Promise<ParsedKey | undefined> {
  const data = await deps.readFile(expandTilde(path), 'utf-8').catch(() => undefined);
  if (!data) return undefined;
  const parsed = utils.parseKey(data);
  return parsed instanceof Error ? undefined : parsed;
}

async function readIdentityKeys(paths: string[], deps: SshConnectDeps): Promise<ParsedKey[]> {
  const keys: ParsedKey[] = [];
  for (const path of paths) {
    const publicKey = await readIdentityKey(`${path}.pub`, deps);
    const key = publicKey ?? (await readIdentityKey(path, deps));
    if (key) keys.push(key);
  }
  return keys;
}

export async function resolveManualAgentSshConfig(
  host: string,
  deps: SshConnectDeps
): Promise<ResolvedSshConfig | undefined> {
  const direct = await deps.resolveSshConfig(host).catch(() => undefined);
  if (direct) {
    const agentSocket = resolveAgentSocketFromResolved(direct, deps.env);
    if (agentSocket.kind !== 'unset') return direct;
  }

  return (await deps.findSshConfigByHostName(host).catch(() => undefined)) ?? direct;
}

export async function buildAuthConfig(
  input: SshConnectInput,
  base: SshConfig,
  resolved: ResolvedSshConfig | undefined,
  deps: SshConnectDeps
): Promise<AuthResult> {
  switch (base.authType) {
    case 'password': {
      // Boundary disclosure: stored credentials leave Secret via .expose()
      // only here, where the ssh2 connect config is assembled. Transient
      // credentials arrive as plain strings straight off the wire.
      const password =
        input.kind === 'transient'
          ? input.config.password
          : (await deps.getPassword(input.row.id))?.expose();
      if (!password) throw new Error(`No password found for SSH connection '${base.name}'`);
      return { config: { password } };
    }

    case 'key': {
      const keyPath = base.privateKeyPath?.trim() || resolved?.identityFile[0];
      if (!keyPath)
        throw new Error(`Private key path is required for SSH connection '${base.name}'`);
      const privateKey = await deps.readFile(expandTilde(keyPath), 'utf-8');
      // Boundary disclosure: same contract as the password case above.
      const passphrase =
        input.kind === 'transient'
          ? input.config.passphrase
          : (await deps.getPassphrase(input.row.id))?.expose();
      return { config: { privateKey, ...(passphrase ? { passphrase } : {}) } };
    }

    case 'agent': {
      const agentSocket = resolved
        ? resolveAgentSocketFromResolved(resolved, deps.env)
        : { kind: 'unset' as const };
      const agent =
        agentSocket.kind === 'socket'
          ? agentSocket.path
          : agentSocket.kind === 'disabled'
            ? undefined
            : deps.env.SSH_AUTH_SOCK;
      if (agentSocket.kind === 'disabled') {
        throw new Error(`SSH agent is disabled by SSH config for connection '${base.name}'`);
      }
      if (!agent) throw new Error(`SSH agent socket not found for connection '${base.name}'`);
      if (resolved?.identitiesOnly && resolved.identityFile.length > 0) {
        const identityKeys = await readIdentityKeys(resolved.identityFile, deps);
        if (identityKeys.length === 0) {
          throw new Error(
            `IdentitiesOnly is enabled, but no IdentityFile public keys could be loaded for SSH connection '${base.name}'`
          );
        }
        return {
          config: {
            agent: new IdentityFilteredAgent(agent, deps.createAgent(agent), identityKeys),
          },
          agentSocketPath: agent,
        };
      }
      return { config: { agent }, agentSocketPath: agent };
    }
  }
}
