import { readFile } from 'node:fs/promises';
import ssh2 from 'ssh2';
import { resolveSshConfig } from '../config/resolve-ssh-config';
import { findSshConfigHostByHostName, parseSshConfigFile } from '../config/sshConfigParser';
import type { SshCredentialService } from '../credentials/ssh-credential-service';
import { spawnProxyCommand, spawnProxyJump } from '../transport/transports';
import {
  createSshConnectConfigResolver,
  type SshConnectInput,
  type SshConnectResult,
} from './resolve-ssh-connect-config';

const { createAgent } = ssh2;

type ConnectCredentials = Pick<SshCredentialService, 'getPassword' | 'getPassphrase'>;

async function findSshConfigByHostName(hostname: string) {
  const hosts = await parseSshConfigFile();
  const match = findSshConfigHostByHostName(hosts, hostname);
  return match ? await resolveSshConfig(match.host).catch(() => undefined) : undefined;
}

export function createProductionSshConnectConfigResolver(credentials: ConnectCredentials) {
  return createSshConnectConfigResolver({
    readFile,
    getPassword: (connectionId) => credentials.getPassword(connectionId),
    getPassphrase: (connectionId) => credentials.getPassphrase(connectionId),
    resolveSshConfig,
    findSshConfigByHostName,
    spawnProxyCommand,
    spawnProxyJump,
    createAgent,
    env: process.env,
  });
}

export async function resolveProductionSshConnectConfig(
  input: SshConnectInput,
  credentials: ConnectCredentials
): Promise<SshConnectResult> {
  return await createProductionSshConnectConfigResolver(credentials)(input);
}

export type { SshConnectInput, SshConnectResult };
