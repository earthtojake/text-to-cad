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


import { integrations, toolByName } from "./registry.mjs";

import type { IntegrationCommand, IntegrationCommandKind, IntegrationReply } from "../../shared/ipc/integrations";
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
    return new Promise<unknown>((resolve, reject) => {
      const timer = setTimeout(() => {
        cleanup();
        this.cancel(requestId);
        this.pending.delete(requestId);
        reject(new Error("the explorer did not answer; is a Hardcore window open?"));
      }, this.deps.timeoutMs ?? REPLY_TIMEOUT_MS);
      const abort = () => { cleanup(); this.cancel(requestId); this.pending.delete(requestId); clearTimeout(timer); reject(signal?.reason ?? new Error("cancelled")); };
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

/** Core file actions plus renderer operations declared by each integration. */
export function createActions(deps: ActionDeps, commands: RendererCommands): BridgeActions {
  const relay = async (kind: IntegrationCommandKind, session: BridgeSession, params: Record<string, unknown>, signal?: AbortSignal, extra: Partial<IntegrationCommand> = {}) => {
    const workspace = deps.sessionRoot(session);
    if (!workspace) throw new Error("this session's project is no longer open in Hardcore");
    return commands.request({ kind, sessionId: session.sessionId, projectId: session.projectId, root: workspace.root,
      rootDirectory: await fsp.realpath(workspace.directory), params,
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
    const stat = await fsp.stat(resolved.absolute);
    if (stat.size > MAX_SNAPSHOT_BYTES) throw new Error("snapshots over 8 MB are not attached");
    const bytes = await fsp.readFile(resolved.absolute, { signal });
    return { path: resolved.relative, mimeType, base64: bytes.toString("base64") };
  };
  return actions;
}
