import { chmod, mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  createExecFileSshConfigRunner,
  parseSshGOutput,
  resolveAgentSocketFromSshConfig,
  resolveIdentityAgentFromSshConfig,
  resolveSshConfig,
} from './resolve-ssh-config';

describe('parseSshGOutput', () => {
  it('parses effective OpenSSH config output including repeated and none values', () => {
    const config = parseSshGOutput(`
hostname 10.0.0.5
user deploy
port 2222
identityfile ~/.ssh/id_ed25519
identityfile ~/.ssh/id_rsa
identityagent none
identitiesonly yes
proxycommand none
proxyjump bastion.example.com
forwardagent yes
forwardagent /tmp/agent.sock
connecttimeout 17
serveraliveinterval 60
serveralivecountmax 2
`);

    expect(config).toEqual({
      hostname: '10.0.0.5',
      user: 'deploy',
      port: 2222,
      identityFile: ['~/.ssh/id_ed25519', '~/.ssh/id_rsa'],
      identityAgent: undefined,
      identityAgentDisabled: true,
      identitiesOnly: true,
      proxyCommand: undefined,
      proxyJump: 'bastion.example.com',
      forwardAgent: true,
      forwardAgentValue: '/tmp/agent.sock',
      connectTimeout: 17,
      serverAliveInterval: 60,
      serverAliveCountMax: 2,
    });
  });
});

describe('resolveSshConfig', () => {
  it('rejects aliases that could be interpreted as ssh options', async () => {
    await expect(resolveSshConfig('-F/tmp/config')).rejects.toThrow('Invalid SSH config alias');
    await expect(resolveSshConfig('--')).rejects.toThrow('Invalid SSH config alias');
  });

  it('executes ssh -G for the selected alias and throws stderr on failure', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'emdash-ssh-g-'));
    const sshPath = join(dir, 'ssh');
    await writeFile(
      sshPath,
      `#!/bin/sh
if [ "$1" = "-G" ] && [ "$2" = "corp-dev" ]; then
  printf '%s\\n' 'hostname dev.internal' 'user alice' 'port 22'
  exit 0
fi
printf '%s\\n' 'missing alias' >&2
exit 255
`
    );
    await chmod(sshPath, 0o755);

    await expect(resolveSshConfig('corp-dev', { sshPath })).resolves.toMatchObject({
      hostname: 'dev.internal',
      user: 'alice',
      port: 22,
    });
    await expect(resolveSshConfig('unknown', { sshPath })).rejects.toThrow('missing alias');
  });

  it('times out ssh -G so Match exec cannot hang callers indefinitely', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'emdash-ssh-g-timeout-'));
    const sshPath = join(dir, 'ssh');
    await writeFile(
      sshPath,
      `#!/bin/sh
sleep 2
`
    );
    await chmod(sshPath, 0o755);

    await expect(resolveSshConfig('corp-dev', { sshPath, timeoutMs: 50 })).rejects.toThrow(
      'ssh -G timed out after 50ms'
    );
  });

  it('bounds ssh -G output with maxBuffer', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'emdash-ssh-g-max-buffer-'));
    const sshPath = join(dir, 'ssh');
    await writeFile(
      sshPath,
      `#!/bin/sh
printf '%0600d\\n' 0
`
    );
    await chmod(sshPath, 0o755);

    await expect(resolveSshConfig('corp-dev', { sshPath, maxBuffer: 128 })).rejects.toThrow(
      /maxBuffer|stdout maxBuffer length exceeded/
    );
  });

  it('can resolve a real OpenSSH config file through an injected runner', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'emdash-ssh-config-'));
    const configPath = join(dir, 'config');
    await writeFile(
      configPath,
      `
Host corp-*
  User inherited
  ForwardAgent yes

Host corp-dev
  HostName dev.internal
  Port 2201
  IdentityAgent none
  ProxyJump bastion
`
    );

    const runner = createExecFileSshConfigRunner({ extraArgs: ['-F', configPath] });
    await expect(resolveSshConfig('corp-dev', { runner })).resolves.toMatchObject({
      hostname: 'dev.internal',
      user: 'inherited',
      port: 2201,
      identityAgent: undefined,
      identityAgentDisabled: true,
      proxyJump: 'bastion',
      forwardAgent: true,
    });
    await expect(
      resolveIdentityAgentFromSshConfig('corp-dev', { runner })
    ).resolves.toBeUndefined();
    await expect(resolveAgentSocketFromSshConfig('corp-dev', { runner })).resolves.toEqual({
      kind: 'disabled',
    });
  });

  it('expands IdentityAgent environment variable values when resolving agent sockets', async () => {
    await expect(
      resolveAgentSocketFromSshConfig('corp-dev', {
        env: { WORK_AGENT: '/tmp/work-agent.sock' },
        runner: async () => ({
          stdout: `
hostname dev.internal
user alice
port 22
identityagent $WORK_AGENT
`,
          stderr: '',
        }),
      })
    ).resolves.toEqual({ kind: 'socket', path: '/tmp/work-agent.sock' });

    await expect(
      resolveAgentSocketFromSshConfig('corp-dev', {
        env: { SSH_AUTH_SOCK: '/tmp/default-agent.sock' },
        runner: async () => ({
          stdout: `
hostname dev.internal
user alice
port 22
identityagent SSH_AUTH_SOCK
`,
          stderr: '',
        }),
      })
    ).resolves.toEqual({ kind: 'socket', path: '/tmp/default-agent.sock' });

    await expect(
      resolveAgentSocketFromSshConfig('corp-dev', {
        env: {},
        runner: async () => ({
          stdout: `
hostname dev.internal
user alice
port 22
identityagent \${MISSING_AGENT}
`,
          stderr: '',
        }),
      })
    ).resolves.toEqual({ kind: 'unset' });
  });
});
