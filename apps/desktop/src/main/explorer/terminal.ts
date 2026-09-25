/**
 * The ptys behind the explorer's terminal tabs.
 *
 * Two things here are not obvious and are the reason this file exists rather
 * than a `spawn` at the call site.
 *
 * **The scrollback lives in main.** A tab that is switched away from unmounts
 * its xterm instance; the pty keeps running and keeps producing output. When
 * the tab comes back it replays what it missed from the buffer kept here. Left
 * to the renderer, switching tabs would silently eat a build's output.
 *
 * **The shell is the login shell, with the login shell's environment.** A pty
 * spawned from Electron's own environment has the PATH the Finder gave the app
 * — no `nvm`, no `brew`, none of what the user's shell sets up — so the first
 * command a person types fails in a way that has nothing to do with them.
 */
import os from "node:os";
import path from "node:path";

import type * as pty from "node-pty";

/* -------------------------------------------------------------------------- */
/* Sessions                                                                    */
/* -------------------------------------------------------------------------- */

export type TerminalOptions = {
  /** Working directory. The project root, or a session's worktree. */
  cwd: string;
  /** Override the login shell — tests use this to run something predictable. */
  shell?: string;
  args?: string[];
  cols?: number;
  rows?: number;
  env?: Record<string, string>;
};

export type TerminalInfo = {
  id: string;
  cwd: string;
  shell: string;
  cols: number;
  rows: number;
  /** Set once the process is gone; a dead tab says so instead of hanging. */
  exitCode: number | null;
};

export type TerminalEvent =
  /**
   * `seq` is the chunk's index in this pty's output, counting from 1.
   *
   * It exists because a tab attaching to a running shell has two sources for
   * the same bytes: the scrollback `attach` hands back, and the live stream it
   * subscribed to. Those cross — `attach` is a request/response and the events
   * are pushes, so nothing orders them — and without a sequence the tab
   * happily writes the shell's startup twice. The renderer keeps the sequence
   * the snapshot ended at and drops anything at or below it.
   */
  | { id: string; type: "data"; data: string; seq: number }
  | { id: string; type: "exit"; exitCode: number; signal?: number };

/**
 * How much output one terminal keeps for replay.
 *
 * Bytes, not lines, because the cost being bounded is memory and a line of
 * ANSI-heavy output is not a fixed size. 512 KB is a few thousand lines of
 * ordinary output — more than a person scrolls back through, far less than a
 * runaway process can produce in a minute.
 */
export const SCROLLBACK_BYTES = 512 * 1024;

const DEFAULT_COLS = 80;
const DEFAULT_ROWS = 24;

class Session {
  /** Kept as chunks so trimming is a shift, not a substring of a huge string. */
  private buffer: string[] = [];
  private bufferBytes = 0;
  /** Chunks written so far. See the note on `TerminalEvent`. */
  private emitted = 0;
  exitCode: number | null = null;

  constructor(
    readonly id: string,
    readonly process: pty.IPty,
    readonly cwd: string,
    readonly shell: string,
    public cols: number,
    public rows: number,
  ) {}

  /** Record a chunk and answer with its sequence number. */
  append(chunk: string): number {
    this.emitted += 1;
    this.buffer.push(chunk);
    this.bufferBytes += chunk.length;
    while (this.bufferBytes > SCROLLBACK_BYTES && this.buffer.length > 1) {
      this.bufferBytes -= (this.buffer.shift() ?? "").length;
    }
    return this.emitted;
  }

  /** The sequence the scrollback currently ends at. */
  get sequence(): number {
    return this.emitted;
  }

  /** Everything the tab missed, as one string to write into a fresh xterm. */
  scrollback(): string {
    return this.buffer.join("");
  }

  info(): TerminalInfo {
    return {
      id: this.id,
      cwd: this.cwd,
      shell: this.shell,
      cols: this.cols,
      rows: this.rows,
      exitCode: this.exitCode,
    };
  }
}

/* -------------------------------------------------------------------------- */
/* The shell and its environment                                               */
/* -------------------------------------------------------------------------- */

/** The user's login shell, or the platform's default. */
export function loginShell(env: NodeJS.ProcessEnv = process.env): string {
  if (process.platform === "win32") {
    return env.COMSPEC ?? "powershell.exe";
  }
  return env.SHELL ?? "/bin/zsh";
}

/**
 * The arguments that make it a *login, interactive* shell.
 *
 * `-l` is what reads `.zprofile` / `.bash_profile`, which is where PATH is set
 * on macOS. Without it the terminal has Electron's PATH and `node` is missing.
 */
export function shellArgs(shell: string): string[] {
  if (process.platform === "win32") {
    return [];
  }
  const name = path.basename(shell);
  return name === "fish" ? ["-l", "-i"] : ["-l"];
}

/**
 * The environment a pty gets.
 *
 * Electron's own variables are stripped: a shell that inherits
 * `ELECTRON_RUN_AS_NODE` runs `node` when the user types `electron`, and
 * `NODE_OPTIONS` from the app's own launch leaks into everything spawned.
 */
export function terminalEnv(
  base: NodeJS.ProcessEnv = process.env,
  extra: Record<string, string> = {},
): Record<string, string> {
  const env: Record<string, string> = {};
  for (const [key, value] of Object.entries(base)) {
    if (value === undefined) {
      continue;
    }
    if (key.startsWith("ELECTRON_") || key === "NODE_OPTIONS") {
      continue;
    }
    env[key] = value;
  }
  env.TERM = "xterm-256color";
  env.COLORTERM = "truecolor";
  // Tools that ask "am I in a terminal a person is watching?" — this one is.
  env.TERM_PROGRAM = "Hardcore";
  return { ...env, ...extra };
}

/* -------------------------------------------------------------------------- */
/* The manager                                                                 */
/* -------------------------------------------------------------------------- */

let sequence = 0;

/**
 * Every live pty, keyed by the id the renderer holds.
 *
 * `node-pty` is imported lazily, for the same reason `better-sqlite3` is: it is
 * a native module built against Electron's ABI, and a plain Node process (a
 * vitest run, say) cannot load it. Importing it at module scope would make
 * this file untestable and would move a load failure from "the terminal tab is
 * broken" to "the app will not start".
 */
export class Terminals {
  private readonly sessions = new Map<string, Session>();
  private module: typeof pty | null = null;

  constructor(private readonly emit: (event: TerminalEvent) => void) {}

  private async pty(): Promise<typeof pty> {
    this.module ??= await import("node-pty");
    return this.module;
  }

  async create(options: TerminalOptions): Promise<TerminalInfo> {
    const nodePty = await this.pty();
    const shell = options.shell ?? loginShell();
    const cols = options.cols ?? DEFAULT_COLS;
    const rows = options.rows ?? DEFAULT_ROWS;
    const id = `pty-${++sequence}-${Date.now().toString(36)}`;

    const child = nodePty.spawn(shell, options.args ?? shellArgs(shell), {
      name: "xterm-256color",
      cwd: options.cwd || os.homedir(),
      cols,
      rows,
      env: terminalEnv(process.env, options.env ?? {}),
    });

    const session = new Session(id, child, options.cwd, shell, cols, rows);
    this.sessions.set(id, session);

    child.onData((data) => {
      const seq = session.append(data);
      this.emit({ id, type: "data", data, seq });
    });
    child.onExit(({ exitCode, signal }) => {
      session.exitCode = exitCode;
      this.emit({ id, type: "exit", exitCode, signal });
    });

    return session.info();
  }

  write(id: string, data: string): void {
    const session = this.sessions.get(id);
    if (!session || session.exitCode !== null) {
      return;
    }
    session.process.write(data);
  }

  resize(id: string, cols: number, rows: number): void {
    const session = this.sessions.get(id);
    if (!session || session.exitCode !== null) {
      return;
    }
    // A zero-sized pty makes ncurses programs draw nothing and never recover.
    session.cols = Math.max(1, Math.floor(cols));
    session.rows = Math.max(1, Math.floor(rows));
    session.process.resize(session.cols, session.rows);
  }

  /**
   * Everything a reattaching tab missed, plus whether the shell is still up
   * and the sequence the snapshot ends at.
   */
  attach(id: string): { info: TerminalInfo; scrollback: string; seq: number } | null {
    const session = this.sessions.get(id);
    return session
      ? { info: session.info(), scrollback: session.scrollback(), seq: session.sequence }
      : null;
  }

  kill(id: string): void {
    const session = this.sessions.get(id);
    if (!session) {
      return;
    }
    this.sessions.delete(id);
    if (session.exitCode === null) {
      try {
        session.process.kill();
      } catch {
        // Already gone between the check and the kill. Nothing to do.
      }
    }
  }

  list(): TerminalInfo[] {
    return [...this.sessions.values()].map((session) => session.info());
  }

  /** On quit. A pty outliving the app is a shell nobody can see or stop. */
  killAll(): void {
    for (const id of [...this.sessions.keys()]) {
      this.kill(id);
    }
  }
}
