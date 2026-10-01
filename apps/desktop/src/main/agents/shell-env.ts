/**
 * The user's login-shell environment (plan §5).
 *
 * An app launched from the Dock inherits launchd's PATH, which knows nothing
 * of Homebrew, nvm, pnpm or `~/.local/bin` — where every agent CLI lives. So
 * the environment agents and probes run in is the one an interactive login
 * shell would have: `$SHELL -ilc 'env -0'`, captured once, refreshed on
 * demand. Any failure (no shell, a hung rc file) falls back to `process.env`
 * — logged, because agents then look "not installed" — so a broken dotfile
 * never keeps the app from starting.
 *
 * An interactive shell's rc files may print (a banner, `fortune`, a
 * "last login" line, often with no trailing newline), and a logout file may
 * print after. The command therefore brackets `env` between two sentinel
 * lines and only what lies between them is parsed; otherwise the noise is
 * glued onto the first record — usually PATH — and that variable is lost.
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
 * a user's own `ANTHROPIC_BASE_URL` (a proxy) is left alone otherwise. The
 * login shell starts from `stripHostSession(processEnv())` and nothing is
 * stripped from what it prints, so the person's own rc exports survive.
 */
const HOST_SESSION_MARKER = "CLAUDECODE";
// `CLAUDE_TMPDIR` and `CLAUDE_PLUGIN_DATA` are the host's scratch and plugin
// directories (seen 2026-09-29); `CLAUDE_CONFIG_DIR` is the person's own
// choice of config and stays.
const HOST_SESSION_PATTERN =
  /^(CLAUDECODE|CLAUDE_CODE_|CLAUDE_PID$|CLAUDE_EFFORT$|CLAUDE_TMPDIR$|CLAUDE_PLUGIN_DATA$|CLAUDE_AGENT_SDK_|CLAUDE_PREVIEW_)/;
const HOST_SESSION_EXTRA = new Set(["ANTHROPIC_BASE_URL"]);

/**
 * Drop the variables a host Claude Code session injected. Exported for the
 * tests. A no-op unless `CLAUDECODE` marks the environment as a host's.
 *
 * It cannot tell a host's `CLAUDE_CODE_OAUTH_TOKEN` from the same one exported
 * in the person's rc file — the host terminal inherited it from that rc, so
 * the values match. The login shell is therefore started from an environment
 * already stripped (`captureLoginEnv`): whatever it prints afterwards was set
 * by the rc itself and stays.
 */
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

/**
 * Generous: a login shell that runs nvm, pyenv and conda init can take
 * several seconds, and giving up means every agent CLI looks missing. A
 * capture slower than `SLOW_MS` is logged so the cause can be found.
 */
const DEFAULT_TIMEOUT_MS = 20_000;
const SLOW_MS = 4_000;

/** The lines the capture prints around `env`; exported for the tests. */
export const ENV_BEGIN = "__TEXT_TO_CAD_ENV_BEGIN__";
export const ENV_END = "__TEXT_TO_CAD_ENV_END__";
const CAPTURE_COMMAND = [
  `printf '\\n%s\\n' ${ENV_BEGIN}`,
  // `command env -0` sidesteps any alias; plain `env` where -0 is unsupported.
  "{ command env -0 2>/dev/null || command env; }",
  `printf '\\n%s\\n' ${ENV_END}`,
].join("; ");

let cached: Promise<Env> | null = null;

/**
 * Resolve the login environment. Cached after the first call; `force`
 * re-runs the shell (Settings › Agents › Refresh).
 */
export function loginEnv(options: { force?: boolean; timeoutMs?: number; shell?: string } = {}): Promise<Env> {
  if (!cached || options.force) {
    cached = captureLoginEnv(options.timeoutMs ?? DEFAULT_TIMEOUT_MS, options.shell)
      .catch((error: unknown) => {
        const reason = error instanceof Error ? error.message : String(error);
        console.warn(
          `[shell-env] could not read the login shell's environment (${reason}); using the process environment, so agents on the shell's PATH may look not installed`,
        );
        return stripHostSession(processEnv());
      });
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

/** Run `$SHELL -ilc` and read its environment. Exported for the tests. */
export async function captureLoginEnv(timeoutMs: number, shell = process.env.SHELL || "/bin/sh"): Promise<Env> {
  // The shell starts from the process environment minus a host session's
  // variables, so the rc can only add back what it exports itself.
  const base = stripHostSession(processEnv());
  if (process.platform === "win32") {
    return base;
  }
  const started = Date.now();
  const output = await new Promise<string>((resolve, reject) => {
    // `-i` because zsh users put their PATH in .zshrc, `-l` because bash
    // users put it in .bash_profile.
    trackChild(execFile(
      shell,
      ["-ilc", CAPTURE_COMMAND],
      { timeout: timeoutMs, maxBuffer: 4 * 1024 * 1024, env: base, encoding: "utf8" },
      (error, stdout) => {
        if (error) {
          reject(error.killed ? new Error(`${shell} -ilc took longer than ${timeoutMs} ms`) : error);
        } else {
          resolve(stdout);
        }
      },
    ), "probe");
  });
  const elapsed = Date.now() - started;
  if (elapsed > SLOW_MS) {
    console.warn(`[shell-env] ${shell} -ilc took ${elapsed} ms; agents wait for it at launch`);
  }
  const parsed = parseLoginOutput(output);
  if (!parsed.PATH) {
    throw new Error("login shell printed no PATH");
  }
  return { ...base, ...parsed };
}

/**
 * The environment between the capture's sentinels. Output without them (a
 * shell that never ran the command's printf) is parsed whole, as before.
 * Exported for the tests.
 */
export function parseLoginOutput(output: string): Env {
  const begin = output.indexOf(`${ENV_BEGIN}\n`);
  if (begin < 0) {
    return parseEnv(output);
  }
  const from = begin + ENV_BEGIN.length + 1;
  const end = output.indexOf(`\n${ENV_END}`, from);
  return parseEnv(output.slice(from, end < 0 ? undefined : end));
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
