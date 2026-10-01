/**
 * `agents.*`: the registry merged with what the detector found, and the two
 * long-running jobs (install, login) that stream a pty's output.
 */
import { z } from "zod";

import { AgentJobOutputSchema, AgentStatusSchema, PlatformSchema } from "../agents";
import { invoke } from "./define";

const AgentId = z.object({ agentId: z.string().min(1) });

export const agentsContract = {
  agents: {
    /** Every provider with its status; served from the cache, never blocking on a probe. */
    list: invoke(z.void(), z.array(AgentStatusSchema)),
    /** Re-resolve the login shell's PATH and re-probe every binary. */
    refresh: invoke(z.void(), z.array(AgentStatusSchema)),
    /**
     * Run one of the provider's install commands in a pty. Answers with the
     * job id; the output arrives on `agents.output`.
     */
    install: invoke(
      AgentId.extend({
        platform: PlatformSchema.optional(),
        /** Index into `install[platform]`; the first is the recommended one. */
        index: z.number().int().nonnegative().default(0),
      }),
      z.object({ jobId: z.string() }),
    ),
    /** Run the provider's cli-login in a pty. */
    login: invoke(AgentId, z.object({ jobId: z.string() })),
    /** Keystrokes for an interactive install or login. */
    writeJob: invoke(z.object({ jobId: z.string(), data: z.string() }), z.void()),
    cancelJob: invoke(z.object({ jobId: z.string() }), z.void()),
  },
} as const;

export const agentsEvents = {
  /** The status table changed (a probe finished, an install or login ended). */
  "agents.status": z.array(AgentStatusSchema),
  /** Output from an install or login job. */
  "agents.output": AgentJobOutputSchema,
} as const;
