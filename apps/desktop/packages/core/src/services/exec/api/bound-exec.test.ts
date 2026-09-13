import { once } from 'node:events';
import { chmod, mkdtemp, readFile, realpath, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { createBoundExec, ExecError } from './index';

describe('BoundExec', () => {
  it('runs a configured executable from a fixed cwd', async () => {
    const cwd = await mkdtemp(path.join(tmpdir(), 'emdash-shared-exec-'));
    const result = await createBoundExec({ file: process.execPath, cwd }).exec([
      '-e',
      'console.log(process.cwd())',
    ]);

    await expect(realpath(result.stdout.trim())).resolves.toBe(await realpath(cwd));
    expect(result.stderr).toBe('');
  });

  it('streams stdout and lets the consumer stop early', async () => {
    const cwd = await mkdtemp(path.join(tmpdir(), 'emdash-shared-exec-stream-'));
    const chunks: string[] = [];

    await createBoundExec({ file: process.execPath, cwd }).execStreaming(
      ['-e', "console.log('one'); console.log('two');"],
      (chunk) => {
        chunks.push(chunk);
        return false;
      }
    );

    expect(chunks.join('')).toContain('one');
  });

  it('opens a piped child with the bound cwd and environment', async () => {
    const cwd = await mkdtemp(path.join(tmpdir(), 'emdash-shared-exec-spawn-'));
    const child = await createBoundExec({
      file: process.execPath,
      cwd,
      env: { ...process.env, EMDASH_EXEC_TEST: 'configured' },
    }).spawn([
      '-e',
      [
        "process.stdin.setEncoding('utf8');",
        "let input = '';",
        "process.stdin.on('data', (chunk) => { input += chunk; });",
        "process.stdin.on('end', () => console.log(JSON.stringify({ cwd: process.cwd(), env: process.env.EMDASH_EXEC_TEST, input })));",
      ].join(' '),
    ]);
    let stdout = '';
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk: string) => {
      stdout += chunk;
    });
    child.stdin.end('payload');

    const [exitCode] = await once(child, 'close');
    expect(exitCode).toBe(0);
    expect(JSON.parse(stdout)).toEqual({
      cwd: await realpath(cwd),
      env: 'configured',
      input: 'payload',
    });
  });

  it('throws ExecError with serializable process details on non-zero exit', async () => {
    const cwd = await mkdtemp(path.join(tmpdir(), 'emdash-shared-exec-error-'));
    await expect(
      createBoundExec({ file: 'git', cwd }).exec(['rev-parse', '--not-a-real-flag'])
    ).rejects.toMatchObject({
      exitCode: 128,
      file: 'git',
      args: ['rev-parse', '--not-a-real-flag'],
    });
  });

  it('uses the configured executable path', async () => {
    const dir = await mkdtemp(path.join(tmpdir(), 'emdash-shared-exec-bin-'));
    const executable = path.join(dir, 'tool.sh');
    const logPath = path.join(dir, 'calls.log');
    await writeFile(
      executable,
      ['#!/bin/sh', `printf '%s\\n' "$1" >> ${JSON.stringify(logPath)}`, 'exit 7', ''].join('\n'),
      'utf8'
    );
    await chmod(executable, 0o755);

    await expect(
      createBoundExec({ file: executable, cwd: dir }).exec(['hello'])
    ).rejects.toBeInstanceOf(ExecError);
    await expect(readFile(logPath, 'utf8')).resolves.toBe('hello\n');
  });

  it('rejects timed-out processes with an ExecError', async () => {
    const cwd = await mkdtemp(path.join(tmpdir(), 'emdash-shared-exec-timeout-'));

    await expect(
      createBoundExec({ file: process.execPath, cwd }).exec(
        ['-e', 'setTimeout(() => {}, 10_000);'],
        { timeoutMs: 50 }
      )
    ).rejects.toMatchObject({
      file: process.execPath,
      args: ['-e', 'setTimeout(() => {}, 10_000);'],
      stderr: 'Timed out after 50ms',
    });
  });

  it('escalates timed-out processes that ignore SIGTERM', async () => {
    const cwd = await mkdtemp(path.join(tmpdir(), 'emdash-shared-exec-timeout-kill-'));
    const pidPath = path.join(cwd, 'child.pid');

    await expect(
      createBoundExec({ file: process.execPath, cwd }).exec(
        [
          '-e',
          [
            "const fs = require('node:fs');",
            `fs.writeFileSync(${JSON.stringify(pidPath)}, String(process.pid));`,
            "process.on('SIGTERM', () => {});",
            'setInterval(() => {}, 10_000);',
          ].join(' '),
        ],
        { timeoutMs: 250 }
      )
    ).rejects.toBeInstanceOf(ExecError);

    const pid = Number.parseInt(await readFile(pidPath, 'utf8'), 10);
    await new Promise((resolve) => setTimeout(resolve, 1_500));
    expect(isProcessAlive(pid)).toBe(false);
  });

  it('awaits process-group termination when cancelled', async () => {
    const cwd = await mkdtemp(path.join(tmpdir(), 'emdash-shared-exec-cancel-'));
    const pidPath = path.join(cwd, 'child.pid');
    const controller = new AbortController();
    const execution = createBoundExec({ file: process.execPath, cwd }).exec(
      [
        '-e',
        [
          "const { spawn } = require('node:child_process');",
          "const fs = require('node:fs');",
          `const child = spawn(process.execPath, ['-e', "process.on('SIGTERM', () => {}); setInterval(() => {}, 10000)"], { stdio: 'ignore' });`,
          `fs.writeFileSync(${JSON.stringify(pidPath)}, String(child.pid));`,
          'setInterval(() => {}, 10_000);',
        ].join(' '),
      ],
      { signal: controller.signal }
    );
    const pid = Number.parseInt(await waitForFile(pidPath), 10);

    controller.abort();

    await expect(execution).rejects.toMatchObject({ name: 'AbortError' });
    expect(isProcessAlive(pid)).toBe(false);
  });
});

function isProcessAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function waitForFile(filePath: string): Promise<string> {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      return await readFile(filePath, 'utf8');
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
  }
  throw new Error(`Timed out waiting for ${filePath}`);
}
