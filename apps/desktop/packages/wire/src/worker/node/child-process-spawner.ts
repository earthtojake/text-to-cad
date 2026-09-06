import { fork, type ChildProcess } from 'node:child_process';
import type { Unsubscribe } from '@emdash/shared';
import type { Scope } from '@emdash/shared/concurrency';
import { recordSpawn } from '@emdash/shared/perf';
import { listen, type EventEmitterLike } from '../events';
import type { ProcessExit, WorkerProcess, WorkerProcessSpawner, WorkerProcessSpec } from '../types';

export function childProcessSpawner(): WorkerProcessSpawner {
  return {
    async spawn(spec: WorkerProcessSpec, _scope: Scope): Promise<WorkerProcess> {
      return spawnChildProcess(spec);
    },
  };
}

function spawnChildProcess(spec: WorkerProcessSpec): WorkerProcess {
  recordSpawn('worker', spec.entry);
  const child = fork(spec.entry, [...(spec.args ?? [])], {
    cwd: spec.cwd,
    env: { ...process.env, ...spec.env },
    stdio: ['ignore', 'pipe', 'pipe', 'ipc'],
    // Structured-clone (V8) serialization preserves `undefined` values, typed
    // arrays, and Dates across the IPC channel, matching Wire payload semantics.
    serialization: 'advanced',
  });

  return {
    get pid() {
      return child.pid;
    },
    send(message) {
      child.send(message as Parameters<ChildProcess['send']>[0]);
    },
    onMessage(cb): Unsubscribe {
      return listen(child as unknown as EventEmitterLike, 'message', (message) => cb(message));
    },
    onExit(cb): Unsubscribe {
      return listen(child as unknown as EventEmitterLike, 'exit', (code, signal) =>
        cb(toProcessExit(code, signal))
      );
    },
    onStdio(cb): Unsubscribe {
      return listenToStdio(child, cb);
    },
    kill(): void {
      child.kill('SIGKILL');
    },
  };
}

function listenToStdio(
  child: ChildProcess,
  cb: (stream: 'stdout' | 'stderr', chunk: string) => void
): Unsubscribe {
  const unsubscribeStdout = listen(
    child.stdout as unknown as EventEmitterLike | undefined,
    'data',
    (chunk) => cb('stdout', stringifyChunk(chunk))
  );
  const unsubscribeStderr = listen(
    child.stderr as unknown as EventEmitterLike | undefined,
    'data',
    (chunk) => cb('stderr', stringifyChunk(chunk))
  );
  return () => {
    unsubscribeStdout();
    unsubscribeStderr();
  };
}

function toProcessExit(code: unknown, signal: unknown): ProcessExit {
  return {
    code: typeof code === 'number' ? code : null,
    signal: typeof signal === 'string' ? signal : null,
  };
}

function stringifyChunk(chunk: unknown): string {
  if (typeof chunk === 'string') return chunk;
  if (Buffer.isBuffer(chunk)) return chunk.toString('utf8');
  return String(chunk);
}
