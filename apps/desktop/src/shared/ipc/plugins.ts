/**
 * `plugins.*`: which plugins this run has (`HARDCORE_PLUGINS`, read by main) and what each adds.
 * The window reads it once before its first render (`@renderer/state/plugins`); Settings › Plugins
 * lists it.
 */
import { z } from "zod";

import { invoke } from "./define";

export const PluginInfoSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  enabled: z.boolean(),
  /** The extensions it opens. */
  extensions: z.array(z.string()),
  /** The skills it hands to agents: app-owned and repository ones, by name. */
  skills: z.array(z.string()),
  /** The agent tools it adds. */
  tools: z.array(z.string()),
});
export type PluginInfo = z.infer<typeof PluginInfoSchema>;

export const pluginsContract = {
  plugins: {
    list: invoke(z.void(), z.array(PluginInfoSchema)),
  },
} as const;
