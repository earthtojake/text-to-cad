/**
 * What the MCP bridge's methods do in the app (plan §8).
 *
 * `attach_snapshot` reads a file here in main and returns its bytes.
 * Drawing loads and explicit saves also use main's guarded filesystem access.
 * Other calls are explorer actions — open a tab, reveal a path, list what is
 * open — and the
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
import { randomUUID } from "node:crypto";

import { MAX_DRAWING_BYTES, parseDrawingScene } from "@hardcore/core/drawing";

import type { CadCommand, CadCommandKind, CadReply } from "../../shared/ipc/cad";
import { resolveInRoot, revisionOf, toRelative, writeTextFile } from "../explorer/fs";
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
  requireExists = true,
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
  if (requireExists) {
    try {
      await fsp.access(absolute);
    } catch {
      throw new Error(`${target} does not exist (looked at ${absolute})`);
    }
  }
  const realDirectory = await fsp.realpath(directory).catch(() => directory);
  return { directory: realDirectory, root, absolute, relative: toRelative(realDirectory, absolute) };
}

function drawingPath(target: unknown): asserts target is string {
  if (typeof target !== "string" || !target || path.extname(target).toLowerCase() !== ".excalidraw") {
    throw new Error("drawing paths must name a .excalidraw JSON file");
  }
}

function normalizedDrawing(serialized: unknown): string {
  if (typeof serialized !== "string" || Buffer.byteLength(serialized, "utf8") > MAX_DRAWING_BYTES) {
    throw new Error("drawing scenes must be JSON no larger than 20 MiB");
  }
  const normalized = JSON.stringify(parseDrawingScene(serialized));
  if (Buffer.byteLength(normalized, "utf8") > MAX_DRAWING_BYTES) {
    throw new Error("drawing scenes must be JSON no larger than 20 MiB");
  }
  return normalized;
}

/** Atomic creation with no replacement: link commits fully written bytes only if the destination is free. */
async function createDrawingFile(directory: string, absolute: string, scene: string): Promise<void> {
  if (await resolveInRoot(directory, path.dirname(absolute)) !== path.dirname(absolute)) {
    throw new Error("the drawing's location changed while saving");
  }
  const temporary = path.join(path.dirname(absolute), `.${path.basename(absolute)}.hardcore-${randomUUID()}.tmp`);
  const handle = await fsp.open(temporary, "wx");
  try {
    try { await handle.writeFile(scene, "utf8"); await handle.sync(); }
    finally { await handle.close(); }
    if (await resolveInRoot(directory, path.dirname(absolute)) !== path.dirname(absolute)) {
      throw new Error("the drawing's location changed while saving");
    }
    await fsp.link(temporary, absolute).catch((error: NodeJS.ErrnoException) => {
      if (error.code === "EEXIST") throw new Error("that drawing file already exists; set overwrite:true to replace it explicitly");
      throw error;
    });
  } finally { await fsp.unlink(temporary).catch(() => {}); }
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

    open_drawing: async (session, { path: target, title }) => {
      if (title !== undefined && (typeof title !== "string" || !title.trim() || title.length > 200)) {
        throw new Error("a drawing title must be between 1 and 200 characters");
      }
      const workspace = deps.sessionRoot(session);
      if (!workspace) throw new Error("this session's project is no longer open in Hardcore");
      if (target === undefined) return relay("open-drawing", session, { root: workspace.root, title });
      drawingPath(target);
      const resolved = await resolveForSession(deps, session, target);
      const stat = await fsp.stat(resolved.absolute);
      if (!stat.isFile()) throw new Error("the drawing path must name a file");
      if (stat.size > MAX_DRAWING_BYTES) throw new Error("drawing scenes must be JSON no larger than 20 MiB");
      const scene = normalizedDrawing(await fsp.readFile(resolved.absolute, "utf8"));
      return relay("open-drawing", session, {
        root: resolved.root, path: resolved.relative, scene, title: title ?? path.parse(resolved.relative).name.slice(0, 200),
      });
    },

    save_drawing: async (session, { tabId, path: target, overwrite }) => {
      if (typeof tabId !== "string" || !tabId) throw new Error("save_drawing needs a drawing tabId");
      if (overwrite !== undefined && typeof overwrite !== "boolean") throw new Error("overwrite must be a boolean");
      drawingPath(target);
      const resolved = await resolveForSession(deps, session, target, false);
      // A missing leaf has no realpath. Resolve its existing parent separately,
      // catching a new file beneath a symlink that points outside the workspace.
      const parent = await resolveInRoot(resolved.directory, path.dirname(resolved.absolute));
      if (!(await fsp.stat(parent)).isDirectory()) throw new Error("the drawing's parent must be a directory");
      const absolute = path.join(parent, path.basename(resolved.absolute));
      const relative = toRelative(resolved.directory, absolute);
      const answer = await relay("drawing-scene", session, { tabId, root: resolved.root });
      const scene = normalizedDrawing((answer as { scene?: unknown } | null)?.scene);
      if (await resolveInRoot(resolved.directory, parent) !== parent) {
        throw new Error("the drawing's location changed while saving");
      }
      const existing = await fsp.lstat(absolute).catch((error: NodeJS.ErrnoException) => {
        if (error.code === "ENOENT") return null;
        throw error;
      });
      if (existing) {
        if (!overwrite) throw new Error("that drawing file already exists; set overwrite:true to replace it explicitly");
        if (!existing.isFile()) throw new Error("the drawing path must name a regular file");
        if (existing.size > MAX_DRAWING_BYTES) throw new Error("existing drawing files over 20 MiB cannot be replaced");
        const revision = revisionOf(await fsp.readFile(absolute));
        await writeTextFile(resolved.directory, relative, scene, revision);
      } else {
        await createDrawingFile(resolved.directory, absolute, scene);
      }
      return { saved: relative, root: resolved.root, tabId, ephemeral: true };
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
