/**
 * `agentOptions.*`: what each installed agent last said a session of its own
 * can be configured with, and what the person chose to start the next one
 * with.
 *
 * The composer's model, effort and mode chips used to exist only once a
 * session was live, because only a live `session/new` reply says which models
 * and which modes an agent has. This branch is the cache that lets the
 * **new-session** screen draw the same three chips: every live session's
 * config options and modes are remembered against its agent, an agent that
 * has never run is probed once, and the model, effort and mode the person
 * picks are applied to the next session the moment it connects.
 */
import { z } from "zod";

import { ConfigOptionSchema, SessionModeSchema } from "../acp/types";
import { invoke } from "./define";

/** One agent's cached options and the defaults chosen for it. */
export const AgentOptionsSchema = z.object({
  agentId: z.string(),
  /** The `session/new` reply's config options, as last seen. Empty until one is. */
  options: z.array(ConfigOptionSchema),
  /**
   * The same reply's `modes`. Kept beside the options because the mode chip
   * is drawn on the new-session screen too, and an agent that sends its
   * modes in `modes` rather than as a `mode` config option would otherwise
   * have nothing there to draw.
   */
  modes: z.array(SessionModeSchema),
  /** When the snapshot was taken; null when there has never been one. */
  updatedAt: z.number().nullable(),
  /** The value the next session starts with, when the agent still offers it. */
  defaultModel: z.string().nullable(),
  /**
   * The effort last picked, **per model** (migration 9): Claude reports its
   * `effort` option for whichever model the session is on and its levels
   * change with the model, so a level remembered against the agent belongs to
   * no model in particular. Keyed by the model option's `value`, or by
   * `NO_MODEL` for an agent that offers no model dropdown.
   */
  defaultEfforts: z.record(z.string(), z.string()),
  /**
   * The effort option as last reported while each model was current — the
   * levels that model offers. A snapshot only ever describes the model it was
   * taken with, so this is how switching the model chip can swap the effort
   * list as well as its value; it fills in as live sessions report their
   * options after a model change.
   */
  effortOptions: z.record(z.string(), ConfigOptionSchema),
  /** The mode the next session starts in; null means the agent's own auto preset. */
  defaultMode: z.string().nullable(),
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
     * Remember the model, or the mode, the next session with this agent
     * should start as. Per provider, both of them — and picking a model
     * deliberately says nothing about the effort: that is `setEffort`, keyed
     * by the model it was picked under, so switching model and switching back
     * comes back to the level that was chosen there.
     */
    setDefaults: invoke(
      z.object({
        agentId: z.string().min(1),
        model: z.string().nullable().optional(),
        mode: z.string().nullable().optional(),
      }),
      z.array(AgentOptionsSchema),
    ),
    /**
     * Remember the effort level for one of this agent's models. `model` is
     * the model option's value, or `NO_MODEL` (the empty string) for an agent
     * that offers no model dropdown — hence no `.min(1)`.
     */
    setEffort: invoke(
      z.object({
        agentId: z.string().min(1),
        model: z.string(),
        effort: z.string().nullable(),
      }),
      z.array(AgentOptionsSchema),
    ),
  },
} as const;

export const agentOptionsEvents = {
  /** A snapshot or a default changed, anywhere. */
  "agentOptions.changed": z.array(AgentOptionsSchema),
} as const;
