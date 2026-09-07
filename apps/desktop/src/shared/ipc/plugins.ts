/**
 * `plugins.*`: whether Hardcore's own plugin — the repo's `cad` plugin minus
 * `cad-viewer`, plus `hardcore-app-use`, versioned with the app (plan §8) — is
 * installed into a given agent.
 *
 * Declared by P6 because the Agents drawer and the CAD Runtime page both have
 * to say something about it, and answered by stubs until P5 composes and
 * installs the plugin for real. The stub's honest answer is `not-installed`:
 * nothing has been installed, and a page that claimed otherwise would be
 * lying about the one thing this branch exists to report.
 *
 * `invoke` comes from `./define`, not from `../ipc` — the contract imports this
 * module, so importing it back is a load-time cycle.
 */
import { z } from "zod";

import { invoke } from "./define";

/**
 * - `unsupported` — the agent has no plugin system and no skills directory, so
 *   there is nowhere to put it.
 * - `not-installed` — nothing installed yet.
 * - `installed` — installed, at `installedVersion`.
 * - `update-available` — installed, but older than the app.
 */
export const PluginStateSchema = z.enum([
  "unsupported",
  "not-installed",
  "installed",
  "update-available",
]);
export type PluginState = z.infer<typeof PluginStateSchema>;

export const PluginStatusSchema = z.object({
  /** Registry id of the agent this is about. */
  agentId: z.string(),
  state: PluginStateSchema,
  /** What is installed into the agent, when something is. */
  installedVersion: z.string().nullable().default(null),
  /** What the app would install — its own version. */
  availableVersion: z.string().nullable().default(null),
  /** MCP servers the agent has configured. Read-only in the drawer for now. */
  mcpServers: z.number().int().nonnegative().default(0),
  /** Set when the last install failed; safe to show. */
  message: z.string().optional(),
});
export type PluginStatus = z.infer<typeof PluginStatusSchema>;

const AgentId = z.object({ agentId: z.string().min(1) });

export const pluginsContract = {
  plugins: {
    /** One agent's plugin state. */
    status: invoke(AgentId, PluginStatusSchema),
    /** Every agent's, for the CAD Runtime page's per-agent rows. */
    statusAll: invoke(z.void(), z.array(PluginStatusSchema)),
    /** Install or update the plugin into that agent; answers with the new state. */
    install: invoke(AgentId, PluginStatusSchema),
  },
} as const;

export const pluginsEvents = {
  /** Pushed when an install finishes, so every open page agrees. */
  "plugins.status": z.array(PluginStatusSchema),
} as const;
