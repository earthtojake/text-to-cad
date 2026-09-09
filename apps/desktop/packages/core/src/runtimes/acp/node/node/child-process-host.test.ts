import { describe, expect, it } from 'vitest';
import { ChildAcpProcessHost } from './child-process-host';

describe.skipIf(process.platform === 'win32')('ChildAcpProcessHost process trees', () => {
  it('terminates descendant commands with their ACP terminal process', async () => {
    const host = new ChildAcpProcessHost();
    const terminal = await host.spawnTerminal({
      command: process.execPath,
      args: [
        '-e',
        [
          "const { spawn } = require('node:child_process');",
          "const child = spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], { stdio: 'ignore' });",
          "process.stdout.write(String(child.pid) + '\\n');",
          'setInterval(() => {}, 1000);',
        ].join(''),
      ],
      env: process.env as Record<string, string>,
      cwd: process.cwd(),
    });
    const descendantPid = await new Promise<number>((resolve) => {
      terminal.stdout.once('data', (chunk) => resolve(Number(String(chunk).trim())));
    });
    const exited = new Promise<void>((resolve) => terminal.onExit(() => resolve()));

    terminal.kill('SIGTERM');
    await exited;
    await expectProcessGone(descendantPid);
  });
});

async function expectProcessGone(pid: number): Promise<void> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    try {
      process.kill(pid, 0);
    } catch {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  expect.fail(`Descendant process ${pid} survived process-tree termination.`);
}
