/**
 * `agentOptions.*`: what each installed agent last said a session of its own
 * can be configured with, and what the person chose to start the next one
 * with.
 *
 * The composer's model and effort chips used to exist only once a session was
 * live, because only a live `session/new` reply says which models an agent
 * has. This branch is the cache that lets the **new-session** screen draw the
 * same two chips: every live session's config options are remembered against
 * its agent, an agent that has never run is probed once, and the model and
 * effort the person picks are applied to the next session the moment it
 * connects.
 */
import { z } from "zod";

import { ConfigOptionSchema } from "../acp/types";
import { invoke } from "./define";

/** One agent's cached options and the defaults chosen for it. */
export const AgentOptionsSchema = z.object({
  agentId: z.string(),
  /** The `session/new` reply's config options, as last seen. Empty until one is. */
  options: z.array(ConfigOptionSchema),
  /** When the snapshot was taken; null when there has never been one. */
  updatedAt: z.number().nullable(),
  /** The value the next session starts with, when the agent still offers it. */
  defaultModel: z.string().nullable(),
  defaultEffort: z.string().nullable(),
});
export type AgentOptions = z.infer<typeof AgentOptionsSchema>;

export const agentOptionsContract = {
  agentOptions: {
    /** Every agent that has a cached snapshot or a stored default. */
    list: invoke(z.void(), z.array(AgentOptionsSchema)),
    /**
     * Make sure this agent has a snapshot, probing it once if it has none:
     * spawn the adapter, `initialize`, `session/new` in the project's
     * directory, keep the config options, close without prompting.
     *
     * Answers as soon as the request is accepted, never with the result — a
     * probe of an agent that is not installed or not signed in simply never
     * produces a snapshot, and the new-session screen shows that provider
     * nothing rather than an error it cannot act on.
     */
    probe: invoke(
      z.object({ agentId: z.string().min(1), projectId: z.string().optional() }),
      z.void(),
    ),
    /**
     * Remember what the next session with this agent should start as. The
     * model is applied before the effort, because switching model changes
     * which effort levels exist.
     */
    setDefaults: invoke(
      z.object({
        agentId: z.string().min(1),
        model: z.string().nullable().optional(),
        effort: z.string().nullable().optional(),
      }),
      z.array(AgentOptionsSchema),
    ),
  },
} as const;

export const agentOptionsEvents = {
  /** A snapshot or a default changed, anywhere. */
  "agentOptions.changed": z.array(AgentOptionsSchema),
} as const;
