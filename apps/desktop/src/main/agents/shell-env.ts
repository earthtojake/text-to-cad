/**
 * The user's login-shell environment (plan §5).
 *
 * An app launched from the Dock inherits launchd's PATH, which knows nothing
 * of Homebrew, nvm, pnpm or `~/.local/bin` — where every agent CLI lives. So
 * the environment agents and probes run in is the one an interactive login
 * shell would have: `$SHELL -ilc 'env -0'`, captured once, refreshed on
 * demand. Any failure (no shell, a hung rc file) falls back to `process.env`
 * so a broken dotfile never keeps the app from starting.
 */
import { execFile } from "node:child_process";

import { trackChild } from "../children";

export type Env = Record<string, string>;

/** Keys a shell sets for itself that should not leak into a child. */
const SHELL_ONLY = new Set(["_", "SHLVL", "PWD", "OLDPWD", "PS1", "PROMPT", "TERM_SESSION_ID"]);

/**
 * When the app (or the harness) is started from a terminal that is itself
 * inside a Claude Code session, that session's variables come along —
 * `CLAUDECODE`, `CLAUDE_CODE_*`, the host's `ANTHROPIC_BASE_URL` — and a
 * nested `claude` then reports itself logged out and the Claude adapter
 * answers every prompt with "Authentication required". Verified on this
 * machine 2026-09-06. Strip them whenever `CLAUDECODE` marks a host session;
 * a user's own `ANTHROPIC_BASE_URL` (a proxy) is left alone otherwise.
 */
const HOST_SESSION_MARKER = "CLAUDECODE";
const HOST_SESSION_PATTERN = /^(CLAUDECODE|CLAUDE_CODE_|CLAUDE_PID$|CLAUDE_EFFORT$|CLAUDE_AGENT_SDK_|CLAUDE_PREVIEW_)/;
const HOST_SESSION_EXTRA = new Set(["ANTHROPIC_BASE_URL"]);

/** Drop the variables a host Claude Code session injected. Exported for the tests. */
export function stripHostSession(env: Env): Env {
  if (!(HOST_SESSION_MARKER in env)) {
    return env;
  }
  const clean: Env = {};
  for (const [key, value] of Object.entries(env)) {
    if (!HOST_SESSION_PATTERN.test(key) && !HOST_SESSION_EXTRA.has(key)) {
      clean[key] = value;
    }
  }
  return clean;
}

const DEFAULT_TIMEOUT_MS = 8_000;

let cached: Promise<Env> | null = null;

/**
 * Resolve the login environment. Cached after the first call; `force`
 * re-runs the shell (Settings › Agents › Refresh).
 */
export function loginEnv(options: { force?: boolean; timeoutMs?: number } = {}): Promise<Env> {
  if (!cached || options.force) {
    cached = captureLoginEnv(options.timeoutMs ?? DEFAULT_TIMEOUT_MS)
      .catch(() => processEnv())
      .then(stripHostSession);
  }
  return cached;
}

/** `process.env` with the undefined values dropped. */
export function processEnv(): Env {
  const env: Env = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (typeof value === "string") {
      env[key] = value;
    }
  }
  return env;
}

async function captureLoginEnv(timeoutMs: number): Promise<Env> {
  if (process.platform === "win32") {
    return processEnv();
  }
  const shell = process.env.SHELL || "/bin/sh";
  const output = await new Promise<string>((resolve, reject) => {
    // `-i` because zsh users put their PATH in .zshrc, `-l` because bash
    // users put it in .bash_profile. `command env -0` sidesteps any alias.
    trackChild(execFile(
      shell,
      ["-ilc", "command env -0 2>/dev/null || command env"],
      { timeout: timeoutMs, maxBuffer: 4 * 1024 * 1024, env: process.env, encoding: "utf8" },
      (error, stdout) => (error ? reject(error) : resolve(stdout)),
    ), "probe");
  });
  const parsed = parseEnv(output);
  if (!parsed.PATH) {
    throw new Error("login shell printed no PATH");
  }
  return { ...processEnv(), ...parsed };
}

/** Parse `env -0` (or plain `env`) output. Exported for the tests. */
export function parseEnv(output: string): Env {
  const entries = output.includes("\0") ? output.split("\0") : output.split("\n");
  const env: Env = {};
  for (const entry of entries) {
    const eq = entry.indexOf("=");
    if (eq <= 0) {
      continue;
    }
    const key = entry.slice(0, eq);
    if (SHELL_ONLY.has(key) || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
      continue;
    }
    env[key] = entry.slice(eq + 1);
  }
  return env;
}
