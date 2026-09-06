/**
 * A `SpawnTerminal` over `child_process`. No pty: stdout and stderr are
 * merged in arrival order and there is no terminal emulation, which is
 * enough for the tests and the CLI harness (and for a headless build where
 * node-pty is missing). Main uses `pty-backend.ts`.
 */
import { spawn } from "node:child_process";

import type { SpawnTerminal, TerminalExit, TerminalProcess } from "./terminals";

export const spawnProcessTerminal: SpawnTerminal = ({ command, args, cwd, env }) => {
  const child = spawn(command, args, { cwd, env, stdio: ["pipe", "pipe", "pipe"] });
  const dataListeners: ((data: string) => void)[] = [];
  const exitListeners: ((exit: TerminalExit) => void)[] = [];
  let pendingExit: TerminalExit | null = null;

  const emitData = (chunk: Buffer) => {
    const text = chunk.toString("utf8");
    for (const listener of dataListeners) {
      listener(text);
    }
  };
  child.stdout.on("data", emitData);
  child.stderr.on("data", emitData);
  child.on("error", (error) => {
    emitData(Buffer.from(`${error.message}\n`));
  });
  child.on("close", (code, signal) => {
    const exit: TerminalExit = { exitCode: code, signal: signal ?? null };
    pendingExit = exit;
    for (const listener of exitListeners) {
      listener(exit);
    }
  });

  const process: TerminalProcess = {
    pid: child.pid ?? -1,
    onData: (listener) => {
      dataListeners.push(listener);
    },
    onExit: (listener) => {
      if (pendingExit) {
        listener(pendingExit);
      } else {
        exitListeners.push(listener);
      }
    },
    write: (data) => {
      child.stdin.write(data);
    },
    kill: (signal) => {
      child.kill(signal ?? "SIGTERM");
    },
  };
  return process;
};
