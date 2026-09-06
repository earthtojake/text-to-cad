import { mkdir, mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  findSshConfigHostByHostName,
  parseSshConfigContent,
  parseSshConfigFileAt,
} from './sshConfigParser';

describe('parseSshConfigContent', () => {
  it('lists concrete SSH config aliases with proxy and forwarding preview fields', () => {
    const hosts = parseSshConfigContent(`
Host *.internal
  ProxyJump ignored

Host corp-dev corp-dev-alt
  HostName dev.internal
  User alice
  Port 2222
  IdentityFile ~/.ssh/dev_ed25519
  IdentityAgent "~/.1password/agent.sock"
  ProxyCommand cloudflared access ssh --hostname %h
  ForwardAgent $SSH_AUTH_SOCK

Host plain
  HostName plain.example.com
  ProxyJump bastion.example.com
  ForwardAgent no
`);

    expect(hosts).toEqual([
      {
        host: 'corp-dev',
        hostname: 'dev.internal',
        user: 'alice',
        port: 2222,
        identityFile: expect.stringContaining('/.ssh/dev_ed25519'),
        identityAgent: expect.stringContaining('/.1password/agent.sock'),
        proxyCommand: 'cloudflared access ssh --hostname %h',
        forwardAgent: true,
        forwardAgentValue: '$SSH_AUTH_SOCK',
      },
      {
        host: 'corp-dev-alt',
        hostname: 'dev.internal',
        user: 'alice',
        port: 2222,
        identityFile: expect.stringContaining('/.ssh/dev_ed25519'),
        identityAgent: expect.stringContaining('/.1password/agent.sock'),
        proxyCommand: 'cloudflared access ssh --hostname %h',
        forwardAgent: true,
        forwardAgentValue: '$SSH_AUTH_SOCK',
      },
      {
        host: 'plain',
        hostname: 'plain.example.com',
        proxyJump: 'bastion.example.com',
        forwardAgent: false,
      },
    ]);
  });

  it('keeps aliases without an explicit user so ssh -G can resolve them later', () => {
    const hosts = parseSshConfigContent(`
Host corp-dev
  HostName dev.internal
  ProxyJump bastion
`);

    expect(hosts).toEqual([
      {
        host: 'corp-dev',
        hostname: 'dev.internal',
        proxyJump: 'bastion',
      },
    ]);
  });

  it('matches HostName previews case-insensitively for legacy fallback', () => {
    expect(
      findSshConfigHostByHostName(
        [
          {
            host: 'corp-dev',
            hostname: 'dev.internal',
          },
        ],
        'DEV.INTERNAL'
      )
    ).toEqual({
      host: 'corp-dev',
      hostname: 'dev.internal',
    });
  });

  it('lists aliases from included SSH config files', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'emdash-ssh-config-'));
    await mkdir(join(dir, 'conf.d'));
    await writeFile(
      join(dir, 'config'),
      `
Host root-alias
  HostName root.internal

Include conf.d/*.conf
`,
      'utf-8'
    );
    await writeFile(
      join(dir, 'conf.d', 'team.conf'),
      `
Host included-alias
  HostName included.internal
  User alice
`,
      'utf-8'
    );

    expect(await parseSshConfigFileAt(join(dir, 'config'))).toEqual([
      {
        host: 'root-alias',
        hostname: 'root.internal',
      },
      {
        host: 'included-alias',
        hostname: 'included.internal',
        user: 'alice',
      },
    ]);
  });

  it('applies the same included snippet at each Include occurrence', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'emdash-ssh-config-repeat-'));
    await writeFile(
      join(dir, 'shared.conf'),
      `
  User shared
  IdentityAgent ~/.ssh/shared-agent.sock
`,
      'utf-8'
    );
    await writeFile(
      join(dir, 'config'),
      `
Host first
  HostName first.internal
  Include shared.conf

Host second
  HostName second.internal
  Include shared.conf
`,
      'utf-8'
    );

    expect(await parseSshConfigFileAt(join(dir, 'config'))).toEqual([
      {
        host: 'first',
        hostname: 'first.internal',
        user: 'shared',
        identityAgent: expect.stringContaining('/.ssh/shared-agent.sock'),
      },
      {
        host: 'second',
        hostname: 'second.internal',
        user: 'shared',
        identityAgent: expect.stringContaining('/.ssh/shared-agent.sock'),
      },
    ]);
  });
});
