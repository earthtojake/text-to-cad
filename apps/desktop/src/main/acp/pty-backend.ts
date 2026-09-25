/**
 * A `SpawnTerminal` over node-pty, and the `SpawnJobPty` the agent jobs use.
 * Only main imports this file: node-pty is built for Electron's ABI and
 * does not load anywhere else (README).
 */
import * as pty from "node-pty";

import type { SpawnJobPty } from "../agents/jobs";
import type { SpawnTerminal, TerminalProcess } from "./terminals";

export const spawnPtyTerminal: SpawnTerminal = ({ command, args, cwd, env }) => {
  const child = pty.spawn(command, args, {
    name: "xterm-256color",
    cols: 120,
    rows: 40,
    cwd,
    env,
  });
  const process: TerminalProcess = {
    pid: child.pid,
    onData: (listener) => {
      child.onData(listener);
    },
    onExit: (listener) => {
      child.onExit(({ exitCode, signal }) => {
        listener({ exitCode, signal: signal ? String(signal) : null });
      });
    },
    write: (data) => child.write(data),
    kill: (signal) => child.kill(signal),
  };
  return process;
};

export const spawnJobPty: SpawnJobPty = ({ file, args, cwd, env }) =>
  pty.spawn(file, args, { name: "xterm-256color", cols: 100, rows: 30, cwd, env });
