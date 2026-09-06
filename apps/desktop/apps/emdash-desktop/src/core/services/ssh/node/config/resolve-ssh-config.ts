// Canonical OpenSSH resolution via `ssh -G`. Source of truth at connect time.
import { execFile } from 'node:child_process';

export interface SshConfigRunnerResult {
  stdout: string;
  stderr: string;
}

export type SshConfigRunner = (alias: string) => Promise<SshConfigRunnerResult>;

export type ResolvedAgentSocket =
  | { kind: 'socket'; path: string }
  | { kind: 'disabled' }
  | { kind: 'unset' };

export interface ResolvedSshConfig {
  hostname: string;
  user: string;
  port: number;
  identityFile: string[];
  identityAgent?: string;
  identityAgentDisabled: boolean;
  identitiesOnly: boolean;
  proxyJump?: string;
  proxyCommand?: string;
  forwardAgent: boolean;
  forwardAgentValue?: string;
  connectTimeout?: number;
  serverAliveInterval?: number;
  serverAliveCountMax?: number;
}

export interface ResolveSshConfigOptions {
  sshPath?: string;
  runner?: SshConfigRunner;
  env?: Record<string, string | undefined>;
  timeoutMs?: number;
  maxBuffer?: number;
}

const SSH_ALIAS_PATTERN = /^[A-Za-z0-9._@%+:/[\]-]+$/;
const DEFAULT_SSH_G_TIMEOUT_MS = 10_000;
const DEFAULT_SSH_G_MAX_BUFFER = 256 * 1024;

function parseInteger(value: string): number | undefined {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function optionalString(value: string): string | undefined {
  const trimmed = value.trim();
  return trimmed && trimmed.toLowerCase() !== 'none' ? trimmed : undefined;
}

export function parseSshGOutput(output: string): ResolvedSshConfig {
  const values = new Map<string, string[]>();

  for (const rawLine of output.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) continue;

    const separator = line.search(/\s/);
    if (separator === -1) continue;

    const key = line.slice(0, separator).toLowerCase();
    const value = line.slice(separator).trim();
    if (!value) continue;

    const list = values.get(key) ?? [];
    list.push(value);
    values.set(key, list);
  }

  const latest = (key: string): string | undefined => values.get(key)?.at(-1);
  const latestOptional = (key: string): string | undefined => {
    const value = latest(key);
    return value === undefined ? undefined : optionalString(value);
  };
  const latestInt = (key: string): number | undefined => {
    const value = latest(key);
    return value === undefined ? undefined : parseInteger(value);
  };

  const identityAgent = latest('identityagent');
  const forwardAgentValue = latest('forwardagent')?.trim();
  const normalizedForwardAgent = forwardAgentValue?.toLowerCase();
  const forwardAgent = forwardAgentValue ? normalizedForwardAgent !== 'no' : false;

  return {
    hostname: latestOptional('hostname') ?? '',
    user: latestOptional('user') ?? '',
    port: latestInt('port') ?? 22,
    identityFile: values.get('identityfile') ?? [],
    identityAgent: identityAgent === undefined ? undefined : optionalString(identityAgent),
    identityAgentDisabled: identityAgent?.trim().toLowerCase() === 'none',
    identitiesOnly: latest('identitiesonly')?.toLowerCase() === 'yes',
    proxyJump: latestOptional('proxyjump'),
    proxyCommand: latestOptional('proxycommand'),
    forwardAgent,
    forwardAgentValue:
      forwardAgentValue && normalizedForwardAgent !== 'yes' && normalizedForwardAgent !== 'no'
        ? forwardAgentValue
        : undefined,
    connectTimeout: latestInt('connecttimeout'),
    serverAliveInterval: latestInt('serveraliveinterval'),
    serverAliveCountMax: latestInt('serveralivecountmax'),
  };
}

export function createExecFileSshConfigRunner(
  options: {
    sshPath?: string;
    extraArgs?: string[];
    timeoutMs?: number;
    maxBuffer?: number;
  } = {}
): SshConfigRunner {
  const sshPath = options.sshPath ?? 'ssh';
  const extraArgs = options.extraArgs ?? [];
  const timeoutMs = options.timeoutMs ?? DEFAULT_SSH_G_TIMEOUT_MS;
  const maxBuffer = options.maxBuffer ?? DEFAULT_SSH_G_MAX_BUFFER;

  return async (alias: string) =>
    await new Promise<SshConfigRunnerResult>((resolve, reject) => {
      execFile(
        sshPath,
        [...extraArgs, '-G', alias],
        { timeout: timeoutMs, killSignal: 'SIGKILL', maxBuffer },
        (error, stdout, stderr) => {
          if (error) {
            const execError = error as Error & { killed?: boolean; signal?: string | null };
            if (execError.killed && execError.signal === 'SIGKILL') {
              reject(new Error(`ssh -G timed out after ${timeoutMs}ms`));
              return;
            }
            const message = stderr.trim() || error.message;
            reject(new Error(message));
            return;
          }
          resolve({ stdout, stderr });
        }
      );
    });
}

function assertValidAlias(alias: string): string {
  const trimmedAlias = alias.trim();
  if (!trimmedAlias || trimmedAlias.startsWith('-') || !SSH_ALIAS_PATTERN.test(trimmedAlias)) {
    throw new Error(`Invalid SSH config alias: ${alias}`);
  }
  return trimmedAlias;
}

export async function resolveSshConfig(
  alias: string,
  options: ResolveSshConfigOptions = {}
): Promise<ResolvedSshConfig> {
  const trimmedAlias = assertValidAlias(alias);
  const runner =
    options.runner ??
    createExecFileSshConfigRunner({
      sshPath: options.sshPath,
      timeoutMs: options.timeoutMs,
      maxBuffer: options.maxBuffer,
    });
  const { stdout } = await runner(trimmedAlias);

  return parseSshGOutput(stdout);
}

export async function resolveIdentityAgentFromSshConfig(
  alias: string,
  options: ResolveSshConfigOptions = {}
): Promise<string | undefined> {
  const resolved = await resolveSshConfig(alias, options);
  return resolved.identityAgent;
}

export async function resolveIdentityAgentByAlias(
  alias: string,
  options: ResolveSshConfigOptions = {}
): Promise<string | undefined> {
  return await resolveIdentityAgentFromSshConfig(alias, options).catch(() => undefined);
}

function expandIdentityAgentPath(
  value: string,
  env: Record<string, string | undefined>
): string | undefined {
  if (value === 'SSH_AUTH_SOCK') return env.SSH_AUTH_SOCK;

  const variableOnly = value.match(/^\$([A-Za-z_][A-Za-z0-9_]*)$/);
  if (variableOnly) return env[variableOnly[1]];

  const bracedVariableOnly = value.match(/^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$/);
  if (bracedVariableOnly) return env[bracedVariableOnly[1]];

  return value;
}

export async function resolveAgentSocketFromSshConfig(
  alias: string,
  options: ResolveSshConfigOptions = {}
): Promise<ResolvedAgentSocket> {
  const resolved = await resolveSshConfig(alias, options);
  return resolveAgentSocketFromResolved(resolved, options.env ?? process.env);
}

export function resolveAgentSocketFromResolved(
  resolved: ResolvedSshConfig,
  env: Record<string, string | undefined>
): ResolvedAgentSocket {
  if (resolved.identityAgentDisabled) return { kind: 'disabled' };
  if (!resolved.identityAgent) return { kind: 'unset' };

  const path = expandIdentityAgentPath(resolved.identityAgent, env);
  return path ? { kind: 'socket', path } : { kind: 'unset' };
}
