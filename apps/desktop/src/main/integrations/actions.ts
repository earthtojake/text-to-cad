/**
 * What the MCP bridge's methods do in the app (plan §8).
 *
 * `attach_snapshot` reads a file here in main and returns its bytes.
 * Other calls are explorer actions — open a tab, reveal a path, list what is
 * open — and the
 * explorer's state lives in the renderer's stores, so those are relayed:
 * main pushes a `integrations.command` carrying a request id, the renderer's bridge
 * (`src/renderer/state/bridge.ts`) performs it against the stores and answers
 * on `integrations.reply`. A command nobody answers times out rather than hanging the
 * agent's tool call: after `REPLY_TIMEOUT_MS`, `VIEWER_REPLY_TIMEOUT_MS` for the
 * live viewer commands (the viewer's own ten-second bound must be able to answer first), or
 * `SLOW_REPLY_TIMEOUT_MS` for `document-save`, `capture-view`, `drawing-capture` and `pdf-capture`. Both
 * the timeout and an abort after the send reject with a message that says the
 * command may have been applied ("may still complete", "may already have been
 * applied"): the window has the command by then, so the agent is told to
 * check before retrying. A handler that finished before an abort is reported
 * by the bridge as applied (`mcp-bridge.ts`).
 *
 * Paths are resolved against the session's root — its worktree when it has
 * one (plan §9), else the project directory — and refused outside it, with
 * the same `resolveInRoot` the explorer's own reads use: an agent can only
 * show what the explorer could show anyway, and the command it produces
 * names the root so the explorer opens the file where it is.
 */
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";


import { integrations, toolByName } from "./registry.mjs";

import type { IntegrationCommand, IntegrationCommandKind, IntegrationReply } from "../../shared/ipc/integrations";
import { MAX_IMAGE_BYTES } from "../../shared/image-cap";
import { climbsOut, resolveInRoot, toRelative } from "../explorer/fs";
import type { BridgeActions, BridgeSession } from "./mcp-bridge";

const REPLY_TIMEOUT_MS = 10_000;
// The viewer's live commands (`liveBinding.ts`) wait up to ten seconds for their effect to be on
// screen and then answer "The viewer did not finish applying this command.". This clock starts
// before the IPC send, so at the same ten seconds it would always fire first and the agent would
// read "did not answer" (is a window open?) for a window that DID answer; the margin lets the
// binding's own sentence arrive. Keep it strictly above the binding's bound.
const VIEWER_REPLY_TIMEOUT_MS = 12_000;
const VIEWER_KINDS: ReadonlySet<IntegrationCommandKind> = new Set(["select-reference", "cad-clear-selection", "cad-camera", "cad-reset-camera", "cad-render-mode"]);
// A save waits on the disk and a capture on a frame and a PNG encode; a
// timeout there reports failure for work that then finishes, and the retry
// finds it already done (or conflicts with it).
const SLOW_REPLY_TIMEOUT_MS = 30_000;
const SLOW_KINDS: ReadonlySet<IntegrationCommandKind> = new Set(["document-save", "capture-view", "drawing-capture", "pdf-capture"]);
const OVER_SNAPSHOT_CAP = "is over the model's 5 MB image limit, which counts the encoded size (about 3.75 MB of file); snapshots that large are not attached";

const IMAGE_TYPES: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
};

/** Whether `head` opens like the image type the extension claims. */
const SIGNATURES: Record<string, (head: Buffer) => boolean> = {
  "image/png": (head) => head.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])),
  "image/jpeg": (head) => head.subarray(0, 3).equals(Buffer.from([0xff, 0xd8, 0xff])),
  "image/gif": (head) => head.subarray(0, 4).toString("latin1") === "GIF8",
  "image/webp": (head) => head.subarray(0, 4).toString("latin1") === "RIFF" && head.subarray(8, 12).toString("latin1") === "WEBP",
};
const IMAGE_NAMES: Record<string, string> = { "image/png": "PNG", "image/jpeg": "JPEG", "image/gif": "GIF", "image/webp": "WebP" };

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
  send: (command: IntegrationCommand) => void;
  cancel?: (requestId: string) => void;
  newId: () => string;
  timeoutMs?: number;
};

/**
 * The relay. `reply` is what the `integrations.reply` IPC handler calls; `request`
 * is what the actions await.
 */
export class RendererCommands {
  private readonly pending = new Map<
    string,
    { resolve: (value: unknown) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> }
  >();

  constructor(private readonly deps: ActionDeps) {}

  request(command: Omit<IntegrationCommand, "requestId">, signal?: AbortSignal): Promise<unknown> {
    signal?.throwIfAborted();
    const requestId = this.deps.newId();
    const timeoutMs = this.deps.timeoutMs ?? (SLOW_KINDS.has(command.kind) ? SLOW_REPLY_TIMEOUT_MS : VIEWER_KINDS.has(command.kind) ? VIEWER_REPLY_TIMEOUT_MS : REPLY_TIMEOUT_MS);
    return new Promise<unknown>((resolve, reject) => {
      const timer = setTimeout(() => {
        cleanup();
        this.cancel(requestId);
        this.pending.delete(requestId);
        reject(new Error(`the text-to-cad window did not answer within ${timeoutMs / 1000} s (is one open?); the command may still complete, so check before retrying`));
      }, timeoutMs);
      // `send` runs before anything can abort (an abort already raised threw
      // above), so by here the window has the command and may have applied it:
      // the bare reason ("revoked") would read as if nothing had happened.
      const abort = () => {
        cleanup(); this.cancel(requestId); this.pending.delete(requestId); clearTimeout(timer);
        const why = signal?.reason instanceof Error ? signal.reason.message : "cancelled";
        reject(new Error(`${command.kind} was sent; it may already have been applied (${why}); check before retrying`));
      };
      const cleanup = () => signal?.removeEventListener("abort", abort);
      signal?.addEventListener("abort", abort, { once: true });
      this.pending.set(requestId, { resolve: value => { cleanup(); resolve(value); }, reject: error => { cleanup(); reject(error); }, timer });
      try { this.deps.send({ ...command, requestId }); }
      catch (error) { this.pending.delete(requestId); clearTimeout(timer); cleanup(); reject(error); }
    });
  }

  reply(reply: IntegrationReply): void {
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

  private cancel(requestId: string) { try { this.deps.cancel?.(requestId); } catch { /* window already closed */ } }

  /** On quit: nothing waits on a window that is closing. */
  dispose(): void {
    for (const [requestId, entry] of this.pending) {
      this.cancel(requestId);
      clearTimeout(entry.timer);
      entry.reject(new Error("text-to-cad is shutting down"));
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
    throw new Error("this session's project is no longer open in text-to-cad");
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

/**
 * A workspace directory as a command names it: its real path, plus the
 * spelling the session recorded when the two differ (see `rootAliases`).
 */
export async function workspaceDirectory(directory: string): Promise<{ rootDirectory: string; rootAliases?: string[] }> {
  const real = await fsp.realpath(directory);
  return real === directory ? { rootDirectory: real } : { rootDirectory: real, rootAliases: [directory] };
}

/**
 * A snapshot's bytes, from one handle. Opened non-blocking and checked with
 * `fstat` on that handle: a FIFO named `x.png` would otherwise hold a libuv
 * thread in `open` for good, and a file checked by path and then read by path
 * can be swapped or grown in between. The read stops one byte past the cap,
 * so a file that grew after the check is still refused rather than read whole.
 *
 * The path was resolved inside `directory` some awaits ago, and `open` follows
 * links: an agent that swaps `x.png` (or a folder above it) for a link to
 * `~/.ssh/id_rsa` in between would be read as the app. So once the handle is
 * open the path is resolved again and must still be inside `directory` and
 * name the very file the handle holds (device and inode).
 */
async function readSnapshot(directory: string, absolute: string, target: string, mimeType: string, signal?: AbortSignal): Promise<Buffer> {
  const handle = await fsp.open(absolute, fs.constants.O_RDONLY | (fs.constants.O_NONBLOCK ?? 0));
  try {
    const opened = await handle.stat();
    if (!opened.isFile()) throw new Error(`${target} is not a file`);
    const now = await fsp.realpath(absolute).catch(() => null);
    const there = now && await fsp.stat(now).catch(() => null);
    const relative = now ? path.relative(directory, now) : "";
    if (!there || climbsOut(relative) || there.dev !== opened.dev || there.ino !== opened.ino) {
      throw new Error(`${target} changed while it was being read; only files inside the workspace can be shown`);
    }
    if (opened.size > MAX_IMAGE_BYTES) throw new Error(`${target} ${OVER_SNAPSHOT_CAP}`);
    // Sized from the stat, plus the one byte that shows a file grown since.
    const buffer = Buffer.allocUnsafe(Math.min(opened.size, MAX_IMAGE_BYTES) + 1);
    let length = 0;
    while (length < buffer.length) {
      signal?.throwIfAborted();
      const { bytesRead } = await handle.read(buffer, length, buffer.length - length, length);
      if (bytesRead === 0) break;
      length += bytesRead;
    }
    if (length > MAX_IMAGE_BYTES) throw new Error(`${target} ${OVER_SNAPSHOT_CAP}`);
    // More bytes than the stat promised: the file grew during the read, and what
    // is in the buffer is a cut of it, not the image.
    if (length > opened.size) throw new Error(`${target} changed while it was being read`);
    // The extension is the agent's word for it; the bytes are what the model will decode.
    if (length === 0) throw new Error(`${target} is empty`);
    if (!SIGNATURES[mimeType]!(buffer.subarray(0, length))) throw new Error(`${target} is not a ${IMAGE_NAMES[mimeType]} image`);
    return buffer.subarray(0, length);
  } finally {
    await handle.close();
  }
}

/** Core file actions plus renderer operations declared by each integration. */
export function createActions(deps: ActionDeps, commands: RendererCommands): BridgeActions {
  const relay = async (kind: IntegrationCommandKind, session: BridgeSession, params: Record<string, unknown>, signal?: AbortSignal, extra: Partial<IntegrationCommand> = {}) => {
    const workspace = deps.sessionRoot(session);
    if (!workspace) throw new Error("this session's project is no longer open in text-to-cad");
    return commands.request({ kind, sessionId: session.sessionId, projectId: session.projectId, root: workspace.root,
      ...(await workspaceDirectory(workspace.directory)), params,
      ...(typeof params.tabId === "string" ? { tabId: params.tabId } : {}),
      ...(typeof params.title === "string" ? { title: params.title } : {}), ...extra }, signal);
  };
  const actions: BridgeActions = {};
  for (const integration of integrations) {
    for (const [method, kind] of Object.entries(integration.rendererCommands ?? {})) {
      actions[method] = (session, raw, signal) => {
        const params = toolByName(method)!.tool.inputSchema.parse(raw);
        return relay(kind as IntegrationCommandKind, session, params, signal);
      };
    }
  }
  for (const method of ["open_file", "reveal"] as const) {
    actions[method] = async (session, raw, signal) => {
      const { path: target } = toolByName(method)!.tool.inputSchema.parse(raw) as { path: string };
      const resolved = await resolveForSession(deps, session, target);
      const stat = await fsp.stat(resolved.absolute);
      if (method === "open_file" && stat.isDirectory()) throw new Error(`${target} is a directory; use reveal for folders`);
      return relay(method === "open_file" ? "open-file" : "reveal", session, {}, signal,
        { path: resolved.relative, root: resolved.root, directory: stat.isDirectory() });
    };
  }
  actions.attach_snapshot = async (session, raw, signal) => {
    const { path: target } = toolByName("attach_snapshot")!.tool.inputSchema.parse(raw) as { path: string };
    const resolved = await resolveForSession(deps, session, target);
    const mimeType = IMAGE_TYPES[path.extname(resolved.absolute).toLowerCase()];
    if (!mimeType) throw new Error(`${target} is not a PNG, JPEG, WebP or GIF`);
    return { path: resolved.relative, mimeType, base64: (await readSnapshot(resolved.directory, resolved.absolute, target, mimeType, signal)).toString("base64") };
  };
  return actions;
}
