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
 * Paths are resolved against the session's project root and refused outside
 * it, with the same `resolveInRoot` the explorer's own reads use: an agent
 * can only show what the explorer could show anyway.
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
  /** The project's root directory, or null when it is gone. */
  projectRoot: (projectId: string) => string | null;
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

/** Resolve an agent-supplied path to the project-relative path the explorer uses. */
export async function resolveForSession(
  deps: Pick<ActionDeps, "projectRoot">,
  session: BridgeSession,
  target: string,
): Promise<{ root: string; absolute: string; relative: string }> {
  const root = deps.projectRoot(session.projectId);
  if (!root) {
    throw new Error("this session's project is no longer open in Hardcore");
  }
  // The cwd is realpath'd first so a path that does not exist yet is judged
  // against the same real root the explorer uses (`/var` vs `/private/var`).
  const cwd = await fsp.realpath(session.cwd).catch(() => session.cwd);
  const candidate = path.isAbsolute(target) ? target : path.resolve(cwd, target);
  let absolute: string;
  try {
    absolute = await resolveInRoot(root, candidate);
  } catch {
    throw new Error(`${target} is outside the project (${root}); only files inside it can be shown`);
  }
  try {
    await fsp.access(absolute);
  } catch {
    throw new Error(`${target} does not exist (looked at ${absolute})`);
  }
  const realRoot = await fsp.realpath(root).catch(() => root);
  return { root: realRoot, absolute, relative: toRelative(realRoot, absolute) };
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
      return relay("open-file", session, { path: resolved.relative });
    },

    reveal: async (session, { path: target }) => {
      const resolved = await resolveForSession(deps, session, target);
      const stat = await fsp.stat(resolved.absolute);
      return relay("reveal", session, { path: resolved.relative, directory: stat.isDirectory() });
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
