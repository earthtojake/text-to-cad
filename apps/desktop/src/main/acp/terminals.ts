/**
 * The client side of ACP's `terminal/*` methods (plan §5).
 *
 * An agent asks for a terminal, polls its output, waits for it to exit,
 * kills it, and finally releases it. Output is buffered per terminal up to a
 * byte limit — the agent's `outputByteLimit`, or a default — and truncated
 * from the front on a character boundary, as the protocol asks. Every chunk
 * is also handed to `onOutput` so the explorer's terminal tab can mirror it.
 *
 * The process factory is injected. Main uses node-pty (`pty-backend.ts`);
 * the tests and the CLI harness use `child_process` (`process-backend.ts`),
 * because node-pty is built against Electron's ABI and will not load in a
 * plain Node process.
 */
import { randomUUID } from "node:crypto";

export type TerminalExit = { exitCode: number | null; signal: string | null };

/** The slice of a process a terminal needs — satisfied by node-pty and by `child_process`. */
export interface TerminalProcess {
  readonly pid: number;
  onData(listener: (data: string) => void): void;
  onExit(listener: (exit: TerminalExit) => void): void;
  write(data: string): void;
  kill(signal?: NodeJS.Signals): void;
}

export type SpawnTerminal = (options: {
  command: string;
  args: string[];
  cwd: string;
  env: Record<string, string>;
}) => TerminalProcess;

export type TerminalOutputListener = (terminalId: string, data: string, exit: TerminalExit | null) => void;

type Terminal = {
  id: string;
  process: TerminalProcess;
  buffer: Buffer;
  truncated: boolean;
  limit: number;
  exit: TerminalExit | null;
  exited: Promise<TerminalExit>;
};

/** 1 MiB, the default when the agent gives no `outputByteLimit`. */
export const DEFAULT_OUTPUT_BYTE_LIMIT = 1024 * 1024;

export class TerminalManager {
  private readonly terminals = new Map<string, Terminal>();

  constructor(
    private readonly spawn: SpawnTerminal,
    private readonly onOutput: TerminalOutputListener = () => {},
  ) {}

  create(options: {
    command: string;
    args?: string[];
    env?: { name: string; value: string }[];
    cwd: string;
    outputByteLimit?: number | null;
    baseEnv: Record<string, string>;
  }): string {
    const id = randomUUID();
    const env = { ...options.baseEnv };
    for (const { name, value } of options.env ?? []) {
      env[name] = value;
    }
    const process = this.spawn({
      command: options.command,
      args: options.args ?? [],
      cwd: options.cwd,
      env,
    });
    let resolveExit: (exit: TerminalExit) => void = () => {};
    const exited = new Promise<TerminalExit>((resolve) => {
      resolveExit = resolve;
    });
    const terminal: Terminal = {
      id,
      process,
      buffer: Buffer.alloc(0),
      truncated: false,
      limit: options.outputByteLimit ?? DEFAULT_OUTPUT_BYTE_LIMIT,
      exit: null,
      exited,
    };
    this.terminals.set(id, terminal);
    process.onData((data) => {
      this.append(terminal, data);
      this.onOutput(id, data, null);
    });
    process.onExit((exit) => {
      terminal.exit = exit;
      resolveExit(exit);
      this.onOutput(id, "", exit);
    });
    return id;
  }

  private append(terminal: Terminal, data: string) {
    const chunk = Buffer.from(data, "utf8");
    let next = Buffer.concat([terminal.buffer, chunk]);
    if (next.length > terminal.limit) {
      terminal.truncated = true;
      next = next.subarray(next.length - terminal.limit);
      // Do not start mid-character: skip UTF-8 continuation bytes.
      let start = 0;
      while (start < next.length && (next[start]! & 0b1100_0000) === 0b1000_0000) {
        start += 1;
      }
      next = next.subarray(start);
    }
    terminal.buffer = next;
  }

  output(id: string): { output: string; truncated: boolean; exitStatus: TerminalExit | null } {
    const terminal = this.get(id);
    return {
      output: terminal.buffer.toString("utf8"),
      truncated: terminal.truncated,
      exitStatus: terminal.exit,
    };
  }

  waitForExit(id: string): Promise<TerminalExit> {
    return this.get(id).exited;
  }

  kill(id: string): void {
    const terminal = this.get(id);
    if (!terminal.exit) {
      terminal.process.kill("SIGTERM");
    }
  }

  /** Kill if running, then forget. A released id is unknown afterwards. */
  release(id: string): void {
    const terminal = this.terminals.get(id);
    if (!terminal) {
      return;
    }
    if (!terminal.exit) {
      terminal.process.kill("SIGTERM");
    }
    this.terminals.delete(id);
  }

  releaseAll(): void {
    for (const id of [...this.terminals.keys()]) {
      this.release(id);
    }
  }

  has(id: string): boolean {
    return this.terminals.has(id);
  }

  private get(id: string): Terminal {
    const terminal = this.terminals.get(id);
    if (!terminal) {
      throw new Error(`unknown terminal ${id}`);
    }
    return terminal;
  }
}
