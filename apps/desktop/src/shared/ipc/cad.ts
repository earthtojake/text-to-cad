/**
 * The CAD runtime's half of the contract (plan §7, §8).
 *
 * `cad.viewerOrigin` is what the file tab asks: it renders `.step`, `.glb`,
 * `.dxf` and the rest through the CAD Viewer's `<CadFileView>`, which talks to
 * a `cadgen viewer --api-only` over HTTP and therefore needs that instance's
 * origin. P3 declared the channel and answered `origin: null`; P5 spawns the
 * viewer per project root and answers with a real one — the renderer handles
 * both.
 *
 * `cad.command` / `cad.reply` are the Hardcore MCP server's way into the
 * explorer. An agent's `open_file` reaches main over the bridge
 * (`src/main/cad/mcp-bridge.ts`); main cannot open a tab itself, because the
 * strip lives in the renderer's stores, so it pushes a command with a request
 * id and the renderer answers on `cad.reply`. The pair is generic on purpose:
 * every tool that needs the renderer's state rides the same two channels.
 */
import { z } from "zod";

import { invoke } from "./define";

/**
 * Why there is no origin. Each value is a different sentence in the UI, which
 * is the whole reason this is not a bare `null`.
 */
export const ViewerOriginReasonSchema = z.enum([
  /**
   * No interpreter can run cadgen: the bundled runtime is missing or broken
   * (`runtime.status` has the words). A failure, not a first-run state —
   * the runtime ships inside the app.
   */
  "runtime-not-ready",
  /** The runtime is there; the viewer process failed to come up. */
  "viewer-failed",
  /** Nothing to serve — the request named a project that no longer exists. */
  "no-project",
]);
export type ViewerOriginReason = z.infer<typeof ViewerOriginReasonSchema>;

export const ViewerOriginSchema = z.object({
  /**
   * The absolute origin of the `cadgen viewer` serving this project's root,
   * e.g. `"http://127.0.0.1:3250"`. Null when there is not one.
   */
  origin: z.string().nullable(),
  reason: ViewerOriginReasonSchema.optional(),
  /** What went wrong, in the interpreter's or the launcher's words; safe to show. */
  message: z.string().optional(),
  /** The runtime log's path, when there is one to point at. */
  log: z.string().optional(),
});
export type ViewerOrigin = z.infer<typeof ViewerOriginSchema>;

/** What an agent can ask the explorer to do, through the Hardcore MCP server. */
export const CadCommandKindSchema = z.enum([
  /** Open (or focus) a file tab on `path` and reveal it in the tree. */
  "open-file",
  /** Expand the tree to `path` and select it, leaving the open file alone. */
  "reveal",
  /** Open a browser tab on `url`. */
  "open-url",
  /** Answer with the strip: every tab and which is active. */
  "list-tabs",
  /** Answer with the active tab's file and what the viewer exposes about it. */
  "viewer-state",
]);
export type CadCommandKind = z.infer<typeof CadCommandKindSchema>;

export const CadCommandSchema = z.object({
  requestId: z.string().min(1),
  kind: CadCommandKindSchema,
  /** The project the command is about; the renderer switches to it. */
  projectId: z.string().min(1),
  /**
   * The root `path` is relative to: null for the project directory, else the
   * absolute path of the session's worktree (plan §9). Main chose it from the
   * session's cwd and checked it belongs to the project.
   */
  root: z.string().nullable().optional(),
  /** Root-relative, already resolved and checked by main. */
  path: z.string().optional(),
  /** For `reveal`: whether `path` is a folder (opened, not just shown). */
  directory: z.boolean().optional(),
  url: z.string().optional(),
});
export type CadCommand = z.infer<typeof CadCommandSchema>;

export const CadReplySchema = z.object({
  requestId: z.string().min(1),
  ok: z.boolean(),
  /** Whatever the command produced; handed to the agent as JSON. */
  result: z.unknown().optional(),
  /** Set when `ok` is false; shown to the agent verbatim. */
  error: z.string().optional(),
});
export type CadReply = z.infer<typeof CadReplySchema>;

export const cadIpc = {
  cad: {
    /**
     * The viewer origin for a root — the project, or one of its worktrees,
     * each served by its own `cadgen viewer` — starting one if need be.
     * Idempotent: the launcher's reuse contract means asking twice gets the
     * same instance.
     */
    viewerOrigin: invoke(z.object({ projectId: z.string().min(1), root: z.string().optional() }), ViewerOriginSchema),
    /**
     * A project opened in the explorer: start what its first CAD file will
     * need — the runtime probe, the viewer for this root, the warm build
     * daemon — now, off the critical path, rather than on the first click.
     * Answers once the work is STARTED; never waits for the viewer, and a
     * failure here is not an error (the first `viewerOrigin` reports it).
     */
    warm: invoke(z.object({ projectId: z.string().min(1), root: z.string().optional() }), z.void()),
    /** The renderer's answer to a `cad.command`. */
    reply: invoke(CadReplySchema, z.void()),
  },
} as const;

export const cadEvents = {
  /** Main asks the explorer to act on an agent's behalf; answered on `cad.reply`. */
  "cad.command": CadCommandSchema,
} as const;
