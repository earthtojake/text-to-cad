import { spawn } from 'node:child_process';
import {
  normalizeSignal,
  type PtyExitInfo,
  type PtyProcess,
  type PtySpawner,
  type PtySpawnSpec,
} from '#services/pty/api';

/**
 * Test-only spawner: executes the spec through plain child processes instead of a
 * native PTY, so contract tests can run real shell scripts without node-pty. Output
 * is stdout+stderr interleaved; resize is a no-op.
 */
export class ChildProcessPtySpawner implements PtySpawner {
  spawn(spec: PtySpawnSpec): PtyProcess {
    const child = spawn(spec.command, spec.args, {
      cwd: spec.cwd,
      env: spec.env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    const dataHandlers: Array<(data: string) => void> = [];
    const exitHandlers: Array<(info: PtyExitInfo) => void> = [];
    const emit = (chunk: Buffer) => {
      const text = chunk.toString('utf8');
      for (const handler of dataHandlers) handler(text);
    };
    child.stdout.on('data', emit);
    child.stderr.on('data', emit);
    child.on('exit', (code, signal) => {
      for (const handler of exitHandlers) {
        handler({ exitCode: code, signal: normalizeSignal(signal) ?? null });
      }
    });
    child.on('error', () => {
      for (const handler of exitHandlers) handler({ exitCode: 1, signal: null });
    });
    return {
      write: () => undefined,
      resize: () => undefined,
      kill: () => {
        try {
          child.kill('SIGTERM');
        } catch {}
      },
      onData: (handler) => dataHandlers.push(handler),
      onExit: (handler) => exitHandlers.push(handler),
      getPid: () => child.pid ?? -1,
    };
  }
}
