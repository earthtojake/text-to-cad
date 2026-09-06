// Best-effort listing of ~/.ssh/config aliases for UI import. Not canonical for connection behavior.
import { glob, readFile, stat } from 'node:fs/promises';
import { homedir } from 'node:os';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import type { SshConfigHost } from '@core/primitives/ssh/api';

/**
 * Strips surrounding quotes (single or double) from a value string.
 */
function stripQuotes(value: string): string {
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    return value.slice(1, -1);
  }
  return value;
}

/**
 * Expands a leading `~` or `~/` to the user's home directory.
 */
function expandTilde(filePath: string): string {
  if (filePath === '~') {
    return homedir();
  }
  if (filePath.startsWith('~/')) {
    return join(homedir(), filePath.slice(2));
  }
  return filePath;
}

/**
 * Parses ~/.ssh/config and returns an array of host entries.
 * Skips wildcard host patterns (containing * or ?).
 */
export async function parseSshConfigFile(): Promise<SshConfigHost[]> {
  const configPath = join(homedir(), '.ssh', 'config');
  return await parseSshConfigFileAt(configPath);
}

export async function parseSshConfigFileAt(configPath: string): Promise<SshConfigHost[]> {
  const content = await readSshConfigWithIncludes(configPath, new Set());
  return parseSshConfigContent(content);
}

async function readSshConfigWithIncludes(
  configPath: string,
  includeStack: Set<string>
): Promise<string> {
  const absoluteConfigPath = resolve(configPath);
  if (includeStack.has(absoluteConfigPath)) return '';

  const nextIncludeStack = new Set(includeStack);
  nextIncludeStack.add(absoluteConfigPath);

  const configDir = dirname(absoluteConfigPath);
  const content = await readFile(configPath, 'utf-8').catch(() => '');
  const expandedLines: string[] = [];

  for (const line of content.split('\n')) {
    const includeMatch = line.trim().match(/^Include\s+(.+)$/i);
    if (!includeMatch) {
      expandedLines.push(line);
      continue;
    }

    const includeFiles = await resolveIncludePaths(includeMatch[1], configDir);
    for (const includeFile of includeFiles) {
      expandedLines.push(await readSshConfigWithIncludes(includeFile, nextIncludeStack));
    }
  }

  return expandedLines.join('\n');
}

async function resolveIncludePaths(value: string, configDir: string): Promise<string[]> {
  const patterns = value.match(/"[^"]*"|'[^']*'|\S+/g) ?? [];
  const matches = await Promise.all(
    patterns.map(async (pattern) => {
      const expandedPattern = expandTilde(stripQuotes(pattern));
      const absolutePattern = isAbsolute(expandedPattern)
        ? expandedPattern
        : resolve(configDir, expandedPattern);
      const files: string[] = [];
      for await (const match of glob(absolutePattern)) {
        const matchStat = await stat(match).catch(() => null);
        if (matchStat?.isFile()) files.push(match);
      }
      return files;
    })
  );

  return matches.flat().sort();
}

/**
 * Parses OpenSSH config content for concrete Host aliases that can be shown in
 * import UI. This is intentionally best-effort; connection behavior is resolved
 * with `ssh -G`.
 */
export function parseSshConfigContent(content: string): SshConfigHost[] {
  const hosts: SshConfigHost[] = [];
  const lines = content.split('\n');
  let currentAliases: string[] = [];
  let currentConfig: Omit<SshConfigHost, 'host'> | null = null;

  const flushCurrentHost = () => {
    if (!currentConfig || currentAliases.length === 0) return;
    for (const host of currentAliases) {
      hosts.push({ host, ...currentConfig });
    }
  };

  for (const line of lines) {
    const trimmed = line.trim();

    // Skip empty lines and comments
    if (!trimmed || trimmed.startsWith('#')) continue;

    // Match Host directive
    const hostMatch = trimmed.match(/^Host\s+(.+)$/i);
    if (hostMatch) {
      flushCurrentHost();
      currentAliases = hostMatch[1]
        .trim()
        .split(/\s+/)
        .map(stripQuotes)
        .filter((host) => host && !host.includes('*') && !host.includes('?'));
      currentConfig = currentAliases.length > 0 ? {} : null;
      continue;
    }

    // Match HostName
    const hostnameMatch = trimmed.match(/^HostName\s+(.+)$/i);
    if (hostnameMatch && currentConfig) {
      currentConfig.hostname = stripQuotes(hostnameMatch[1].trim());
      continue;
    }

    // Match User
    const userMatch = trimmed.match(/^User\s+(.+)$/i);
    if (userMatch && currentConfig) {
      currentConfig.user = stripQuotes(userMatch[1].trim());
      continue;
    }

    // Match Port
    const portMatch = trimmed.match(/^Port\s+(\d+)$/i);
    if (portMatch && currentConfig) {
      currentConfig.port = parseInt(portMatch[1], 10);
      continue;
    }

    // Match IdentityFile
    const identityMatch = trimmed.match(/^IdentityFile\s+(.+)$/i);
    if (identityMatch && currentConfig) {
      const identityFile = expandTilde(stripQuotes(identityMatch[1].trim()));
      currentConfig.identityFile = identityFile;
      continue;
    }

    // Match IdentityAgent
    const identityAgentMatch = trimmed.match(/^IdentityAgent\s+(.+)$/i);
    if (identityAgentMatch && currentConfig) {
      const identityAgent = expandTilde(stripQuotes(identityAgentMatch[1].trim()));
      currentConfig.identityAgent = identityAgent;
      continue;
    }

    // Match ProxyJump
    const proxyJumpMatch = trimmed.match(/^ProxyJump\s+(.+)$/i);
    if (proxyJumpMatch && currentConfig) {
      const proxyJump = stripQuotes(proxyJumpMatch[1].trim());
      currentConfig.proxyJump = proxyJump.toLowerCase() === 'none' ? undefined : proxyJump;
      continue;
    }

    // Match ProxyCommand
    const proxyCommandMatch = trimmed.match(/^ProxyCommand\s+(.+)$/i);
    if (proxyCommandMatch && currentConfig) {
      const proxyCommand = proxyCommandMatch[1].trim();
      currentConfig.proxyCommand = proxyCommand.toLowerCase() === 'none' ? undefined : proxyCommand;
      continue;
    }

    // Match ForwardAgent
    const forwardAgentMatch = trimmed.match(/^ForwardAgent\s+(.+)$/i);
    if (forwardAgentMatch && currentConfig) {
      const value = stripQuotes(forwardAgentMatch[1].trim());
      const normalizedValue = value.toLowerCase();
      currentConfig.forwardAgent = normalizedValue !== 'no';
      if (currentConfig.forwardAgent) {
        currentConfig.forwardAgentValue = normalizedValue === 'yes' ? undefined : value;
      }
      continue;
    }
  }

  // Don't forget the last host
  flushCurrentHost();

  return hosts;
}

export function findSshConfigHostByHostName(
  hosts: SshConfigHost[],
  hostname: string
): SshConfigHost | undefined {
  const normalizedHostname = hostname.toLowerCase();
  return hosts.find((host) => host.hostname?.toLowerCase() === normalizedHostname);
}

/**
 * Resolves the IdentityAgent socket path for a given hostname.
 *
 * Parses ~/.ssh/config and finds a matching host entry by checking
 * both the Host alias and the HostName value. Returns the expanded
 * IdentityAgent path if found, or undefined.
 */
