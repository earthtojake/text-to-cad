import { EventEmitter, once } from 'node:events';
import { chmod, mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { PassThrough } from 'node:stream';
import { describe, expect, it } from 'vitest';
import {
  buildProxyJumpArgs,
  childToDuplex,
  expandProxyCommandTokens,
  spawnProxyJump,
  spawnProxyCommand,
  spawnProxyCommandWithShell,
  terminateProxyChild,
} from './transports';

type FakeChild = Parameters<typeof childToDuplex>[0] & {
  stdin: PassThrough;
  stdout: PassThrough;
  stderr: PassThrough;
  exitCode: number | null;
  signalCode: NodeJS.Signals | null;
  killSignals: NodeJS.Signals[];
  kill: (signal: NodeJS.Signals) => boolean;
};

describe('buildProxyJumpArgs', () => {
  it.each([
    [
      'bastion',
      [
        '-o',
        'BatchMode=yes',
        '-o',
        'ControlMaster=no',
        '-o',
        'ControlPath=none',
        '-W',
        'dest.internal:22',
        'bastion',
      ],
    ],
    [
      'admin@bastion:2222',
      [
        '-o',
        'BatchMode=yes',
        '-o',
        'ControlMaster=no',
        '-o',
        'ControlPath=none',
        '-p',
        '2222',
        '-W',
        'dest.internal:22',
        'admin@bastion',
      ],
    ],
    [
      'user@A:2201,B,bob@[::1]:2203',
      [
        '-o',
        'BatchMode=yes',
        '-o',
        'ControlMaster=no',
        '-o',
        'ControlPath=none',
        '-J',
        'user@A:2201,B',
        '-p',
        '2203',
        '-W',
        'dest.internal:22',
        'bob@[::1]',
      ],
    ],
    [
      'ops@team/bastion+prod%blue:2201',
      [
        '-o',
        'BatchMode=yes',
        '-o',
        'ControlMaster=no',
        '-o',
        'ControlPath=none',
        '-p',
        '2201',
        '-W',
        'dest.internal:22',
        'ops@team/bastion+prod%blue',
      ],
    ],
  ])('builds ssh -W args for %s', (jumpSpec, expectedArgs) => {
    expect(buildProxyJumpArgs(jumpSpec, 'dest.internal', 22)).toEqual(expectedArgs);
  });

  it.each(['-oProxyCommand=evil', 'alice@-bad-host', 'good,-bad', 'bastion:-22'])(
    'rejects option-like or invalid jump specs: %s',
    (jumpSpec) => {
      expect(() => buildProxyJumpArgs(jumpSpec, 'dest.internal', 22)).toThrow('Invalid ProxyJump');
    }
  );
});

describe('spawnProxyJump', () => {
  it('spawns system ssh with built jump args and returns a cleanup handle', () => {
    const calls: Array<{ command: string; args: string[] }> = [];
    const child = fakeChild();

    const transport = spawnProxyJump('bastion', 'dest.internal', 22, (command, args) => {
      calls.push({ command, args });
      return child;
    });

    expect(calls).toEqual([
      {
        command: 'ssh',
        args: buildProxyJumpArgs('bastion', 'dest.internal', 22),
      },
    ]);
    transport.cleanup();
    expect(child.killSignals).toContain('SIGTERM');
  });
});

describe('expandProxyCommandTokens', () => {
  it('expands OpenSSH proxy tokens and rejects unsafe token values', () => {
    expect(
      expandProxyCommandTokens('ssh bastion -W %h:%p -l %r %n %%', {
        host: 'dest.internal',
        port: 2222,
        username: 'alice',
        originalHost: 'corp-dev',
      })
    ).toBe('ssh bastion -W dest.internal:2222 -l alice corp-dev %');

    expect(
      expandProxyCommandTokens('ssh bastion -W %h:%p %n', {
        host: 'dest.internal',
        port: 2222,
        username: 'alice',
        originalHost: 'team/foo%bar@corp',
      })
    ).toBe('ssh bastion -W dest.internal:2222 team/foo%bar@corp');

    expect(
      expandProxyCommandTokens('ssh unsupported=%C%d%i%k%L%l%T%u -W %h:%p %n %%', {
        host: 'dest.internal',
        port: 2222,
        username: 'alice',
        originalHost: 'team/foo%bar@corp',
      })
    ).toBe('ssh unsupported= -W dest.internal:2222 team/foo%bar@corp %');

    expect(() =>
      expandProxyCommandTokens('ssh -W %h:%p bastion', {
        host: 'bad;rm -rf /',
        port: 22,
        username: 'alice',
        originalHost: 'corp-dev',
      })
    ).toThrow('Resolved hostname contains unsafe characters');
  });
});

describe('childToDuplex', () => {
  it('propagates process and stream failures to the duplex', async () => {
    const child = fakeChild();
    const duplex = childToDuplex(child);
    const errorPromise = once(duplex, 'error');

    child.emit('close', 255, null);

    await expect(errorPromise).resolves.toEqual([
      expect.objectContaining({ message: 'Proxy process exited with code 255' }),
    ]);
  });

  it('ignores stdin EPIPE but destroys on other stdin errors', async () => {
    const epipeChild = fakeChild();
    const epipeDuplex = childToDuplex(epipeChild);
    epipeChild.stdin.emit('error', Object.assign(new Error('pipe closed'), { code: 'EPIPE' }));
    expect(epipeDuplex.destroyed).toBe(false);

    const child = fakeChild();
    const duplex = childToDuplex(child);
    const errorPromise = once(duplex, 'error');
    child.stdin.emit('error', Object.assign(new Error('boom'), { code: 'ECONNRESET' }));

    await expect(errorPromise).resolves.toEqual([expect.objectContaining({ message: 'boom' })]);
  });
});

describe('spawnProxyCommand', () => {
  it('uses the platform shell instead of hardcoding a Unix shell path', () => {
    const calls: Array<{ command: string; args: string[]; shell?: boolean }> = [];
    const child = {
      stdin: new PassThrough(),
      stdout: new PassThrough(),
      stderr: new PassThrough(),
      once() {
        return this;
      },
    };

    spawnProxyCommandWithShell(
      'ssh bastion -W %h:%p',
      {
        host: 'dest.internal',
        port: 22,
        username: 'alice',
      },
      (command, args, options) => {
        calls.push({ command, args, shell: options.shell });
        return child as never;
      }
    );

    expect(calls).toEqual([
      {
        command: 'ssh bastion -W dest.internal:22',
        args: [],
        shell: true,
      },
    ]);
  });
  it('provides a duplex socket and cleanup for a real child process', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'emdash-proxy-command-'));
    const script = join(dir, 'proxy.js');
    await writeFile(
      script,
      `
process.stderr.write('proxy ready\\n');
process.stdin.on('data', (chunk) => {
  process.stdout.write(Buffer.from(chunk.toString().toUpperCase()));
});
`
    );
    await chmod(script, 0o755);

    const transport = spawnProxyCommand(`"${process.execPath}" "${script}"`, {
      host: 'dest.internal',
      port: 22,
      username: 'alice',
    });

    const dataPromise = once(transport.sock, 'data');
    transport.sock.write('hello');
    const [chunk] = (await dataPromise) as [Buffer];
    expect(chunk.toString()).toBe('HELLO');
    expect(transport.debugLogs.join('\n')).toContain('proxy ready');

    transport.cleanup();
    expect(transport.process.killed || transport.process.exitCode !== null).toBe(true);
  });
});

describe('terminateProxyChild', () => {
  it('escalates to SIGKILL when the process has not exited after grace period', () => {
    const signals: string[] = [];
    let exitCode: number | null = null;
    const child = {
      get exitCode() {
        return exitCode;
      },
      get signalCode() {
        return null;
      },
      kill(signal: string) {
        signals.push(signal);
        return true;
      },
    };
    const timers: Array<() => void> = [];

    terminateProxyChild(child, {
      setTimeout: (callback) => {
        timers.push(callback);
        return { unref() {} };
      },
    });
    timers[0]?.();

    expect(signals).toEqual(['SIGTERM', 'SIGKILL']);

    exitCode = 0;
    terminateProxyChild(child, {
      setTimeout: (callback) => {
        timers.push(callback);
        return { unref() {} };
      },
    });
    expect(signals).toEqual(['SIGTERM', 'SIGKILL']);
  });
});

describe('bounded proxy debug logs', () => {
  it('keeps only the newest stderr lines', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'emdash-proxy-logs-'));
    const script = join(dir, 'proxy.js');
    await writeFile(
      script,
      `
for (let i = 0; i < 80; i += 1) process.stderr.write('line-' + i + '\\n');
setTimeout(() => {}, 1000);
`
    );

    const transport = spawnProxyCommand(`"${process.execPath}" "${script}"`, {
      host: 'dest.internal',
      port: 22,
      username: 'alice',
      originalHost: 'corp-dev',
    });

    await waitFor(() => transport.debugLogs.at(-1) === 'line-79');
    expect(transport.debugLogs.length).toBeLessThanOrEqual(64);
    expect(transport.debugLogs.at(-1)).toBe('line-79');
    expect(transport.debugLogs).not.toContain('line-0');
    transport.cleanup();
  });
});

async function waitFor(predicate: () => boolean): Promise<void> {
  const deadline = Date.now() + 1_000;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error('Timed out waiting for condition');
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}

function fakeChild(): FakeChild {
  const child = new EventEmitter() as EventEmitter & {
    stdin: PassThrough;
    stdout: PassThrough;
    stderr: PassThrough;
    exitCode: number | null;
    signalCode: NodeJS.Signals | null;
    killSignals: NodeJS.Signals[];
    kill: (signal: NodeJS.Signals) => boolean;
  };
  child.stdin = new PassThrough();
  child.stdout = new PassThrough();
  child.stderr = new PassThrough();
  child.exitCode = null;
  child.signalCode = null;
  child.killSignals = [];
  child.kill = (signal) => {
    child.killSignals.push(signal);
    return true;
  };
  return child as unknown as FakeChild;
}
