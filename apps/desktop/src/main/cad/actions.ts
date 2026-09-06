/**
 * What the MCP bridge's methods do in the app (plan §8).
 *
 * Two kinds. `attach_snapshot` is answered here in main: it reads a file
 * under the project root and returns its bytes. Everything else is an
 * explorer action — open a tab, reveal a path, list what is open — and the
 * explorer's state lives in the renderer's stores, so those are relayed:
 * main pushes a `cad.command` carrying a request id, the renderer's bridge
 * (`src/renderer/state/bridge.ts`) performs it against the stores and answers
 * on `cad.reply`. A command nobody answers times out rather than hanging the
 * agent's tool call.
 *
 * Paths are resolved against the session's root — its worktree when it has
 * one (plan §9), else the project directory — and refused outside it, with
 * the same `resolveInRoot` the explorer's own reads use: an agent can only
 * show what the explorer could show anyway, and the command it produces
 * names the root so the explorer opens the file where it is.
 */
import fsp from "node:fs/promises";
import path from "node:path";

import type { CadCommand, CadCommandKind, CadReply } from "../../shared/ipc/cad";
import { resolveInRoot, toRelative } from "../explorer/fs";
import type { BridgeActions, BridgeSession } from "./mcp-bridge";

const REPLY_TIMEOUT_MS = 10_000;
const MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024;

const IMAGE_TYPES: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
};

export type ActionDeps = {
  /**
   * The directory a session's paths resolve against, or null when its
   * project is gone. A session in a worktree (plan §9) gets that worktree —
   * the files it writes live there, and that is what the explorer must show
   * — and `root` is what the explorer calls it: null for the project
   * directory, the absolute path for a worktree.
   */
  sessionRoot: (session: BridgeSession) => { directory: string; root: string | null } | null;
  /** Push a command to every window. */
  send: (command: CadCommand) => void;
  newId: () => string;
  timeoutMs?: number;
};

/**
 * The relay. `reply` is what the `cad.reply` IPC handler calls; `request`
 * is what the actions await.
 */
export class RendererCommands {
  private readonly pending = new Map<
    string,
    { resolve: (value: unknown) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> }
  >();

  constructor(private readonly deps: ActionDeps) {}

  request(command: Omit<CadCommand, "requestId">): Promise<unknown> {
    const requestId = this.deps.newId();
    return new Promise<unknown>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(requestId);
        reject(new Error("the explorer did not answer; is a Hardcore window open?"));
      }, this.deps.timeoutMs ?? REPLY_TIMEOUT_MS);
      this.pending.set(requestId, { resolve, reject, timer });
      this.deps.send({ ...command, requestId });
    });
  }

  reply(reply: CadReply): void {
    const entry = this.pending.get(reply.requestId);
    if (!entry) {
      return;
    }
    this.pending.delete(reply.requestId);
    clearTimeout(entry.timer);
    if (reply.ok) {
      entry.resolve(reply.result);
    } else {
      entry.reject(new Error(reply.error ?? "the explorer refused"));
    }
  }

  /** On quit: nothing waits on a window that is closing. */
  dispose(): void {
    for (const entry of this.pending.values()) {
      clearTimeout(entry.timer);
      entry.reject(new Error("Hardcore is shutting down"));
    }
    this.pending.clear();
  }
}

/**
 * Resolve an agent-supplied path to the root-relative path the explorer
 * uses, and say which root: the session's worktree when it has one, else the
 * project directory.
 */
export async function resolveForSession(
  deps: Pick<ActionDeps, "sessionRoot">,
  session: BridgeSession,
  target: string,
): Promise<{ directory: string; root: string | null; absolute: string; relative: string }> {
  const resolved = deps.sessionRoot(session);
  if (!resolved) {
    throw new Error("this session's project is no longer open in Hardcore");
  }
  const { directory, root } = resolved;
  // The cwd is realpath'd first so a path that does not exist yet is judged
  // against the same real root the explorer uses (`/var` vs `/private/var`).
  const cwd = await fsp.realpath(session.cwd).catch(() => session.cwd);
  const candidate = path.isAbsolute(target) ? target : path.resolve(cwd, target);
  let absolute: string;
  try {
    absolute = await resolveInRoot(directory, candidate);
  } catch {
    const where = root ? "this session's worktree" : "the project";
    throw new Error(`${target} is outside ${where} (${directory}); only files inside it can be shown`);
  }
  try {
    await fsp.access(absolute);
  } catch {
    throw new Error(`${target} does not exist (looked at ${absolute})`);
  }
  const realDirectory = await fsp.realpath(directory).catch(() => directory);
  return { directory: realDirectory, root, absolute, relative: toRelative(realDirectory, absolute) };
}

export function createActions(deps: ActionDeps, commands: RendererCommands): BridgeActions {
  const relay = (kind: CadCommandKind, session: BridgeSession, extra: Partial<CadCommand> = {}) =>
    commands.request({ kind, projectId: session.projectId, ...extra });

  return {
    open_file: async (session, { path: target }) => {
      const resolved = await resolveForSession(deps, session, target);
      const stat = await fsp.stat(resolved.absolute);
      if (stat.isDirectory()) {
        throw new Error(`${target} is a directory; use reveal for folders`);
      }
      return relay("open-file", session, { path: resolved.relative, root: resolved.root });
    },

    reveal: async (session, { path: target }) => {
      const resolved = await resolveForSession(deps, session, target);
      const stat = await fsp.stat(resolved.absolute);
      return relay("reveal", session, { path: resolved.relative, root: resolved.root, directory: stat.isDirectory() });
    },

    open_url: async (session, { url }) => {
      const { protocol } = new URL(url);
      if (protocol !== "http:" && protocol !== "https:") {
        throw new Error(`only http(s) URLs open in the explorer, not ${protocol}`);
      }
      return relay("open-url", session, { url });
    },

    list_open_tabs: (session) => relay("list-tabs", session),

    viewer_state: (session) => relay("viewer-state", session),

    attach_snapshot: async (session, { path: target }) => {
      const resolved = await resolveForSession(deps, session, target);
      const mimeType = IMAGE_TYPES[path.extname(resolved.absolute).toLowerCase()];
      if (!mimeType) {
        throw new Error(`${target} is not a PNG, JPEG, WebP or GIF`);
      }
      const stat = await fsp.stat(resolved.absolute);
      if (stat.size > MAX_SNAPSHOT_BYTES) {
        throw new Error(`${target} is ${(stat.size / 1024 / 1024).toFixed(1)} MB; snapshots over 8 MB are not attached`);
      }
      const bytes = await fsp.readFile(resolved.absolute);
      return { path: resolved.relative, mimeType, base64: bytes.toString("base64") };
    },
  };
}
