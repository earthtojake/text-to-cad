/** Generic app command relay; domain capabilities remain in their own integrations. */
import { z } from "zod";
import { invoke } from "./define";
/** What an agent can ask the explorer to do, through the Hardcore MCP server. */
export const IntegrationCommandKindSchema = z.enum([
  "open-file", "reveal", "open-url", "open-drawing", "drawing-state", "drawing-capture",
  "list-tabs", "show-tab", "close-tab", "viewer-state", "select-reference", "capture-view",
  "document-read", "document-edit", "document-save", "pdf-state", "pdf-read", "pdf-page", "pdf-capture",
  "terminal-open", "tab-resource", "cad-clear-selection", "cad-camera", "cad-reset-camera", "cad-render-mode",
]);
export type IntegrationCommandKind = z.infer<typeof IntegrationCommandKindSchema>;

export const IntegrationCommandSchema = z.object({
  requestId: z.string().min(1),
  kind: IntegrationCommandKindSchema,
  /** The project the command is about; opening focuses it, scene reads do not. */
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
  tabId: z.string().min(1).optional(),
  title: z.string().min(1).max(200).optional(),
  /** Main-resolved workspace directory, never supplied by the model. */
  rootDirectory: z.string().optional(),
  params: z.record(z.string(), z.unknown()).optional(),
});
export type IntegrationCommand = z.infer<typeof IntegrationCommandSchema>;

export const IntegrationReplySchema = z.object({
  requestId: z.string().min(1),
  ok: z.boolean(),
  /** Whatever the command produced; handed to the agent as JSON. */
  result: z.unknown().optional(),
  /** Set when `ok` is false; shown to the agent verbatim. */
  error: z.string().optional(),
});
export type IntegrationReply = z.infer<typeof IntegrationReplySchema>;

export const integrationsIpc = { integrations: { reply: invoke(IntegrationReplySchema, z.void()) } } as const;
export const integrationsEvents = { "integrations.command": IntegrationCommandSchema, "integrations.cancel": z.object({ requestId: z.string() }) } as const;
