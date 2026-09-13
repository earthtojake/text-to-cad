import { z } from 'zod';

const configOptionBaseSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().optional(),
});

export const modelScoreSchema = z.object({
  value: z.number(),
  max: z.number(),
});
export type ModelScore = z.infer<typeof modelScoreSchema>;

export const modelOptionSchema = configOptionBaseSchema.extend({
  /** Optional model metadata used for ranking/display; absent when provider does not report it. */
  features: z
    .object({
      contextWindowSize: z.number().int().optional(),
      speed: modelScoreSchema.optional(),
      intelligence: modelScoreSchema.optional(),
    })
    .optional(),
});
export type ModelOption = z.infer<typeof modelOptionSchema>;
export type ModelChoice = ModelOption;

export const effortOptionSchema = configOptionBaseSchema;
export type EffortOption = z.infer<typeof effortOptionSchema>;

export const modeOptionSchema = configOptionBaseSchema;
export type ModeOption = z.infer<typeof modeOptionSchema>;

export const sessionCommandSchema = z.object({
  name: z.string(),
  description: z.string(),
  /** Distinguishes provider-advertised ACP commands from Emdash-owned skills. */
  source: z.literal('provider-command'),
  /** Optional provider hint for slash-command arguments, shown near the composer. */
  inputHint: z.string().optional(),
});
export type SessionCommand = z.infer<typeof sessionCommandSchema>;

export const sessionMcpServerSchema = z.object({
  name: z.string(),
  transport: z.enum(['stdio', 'http', 'sse']),
});
export type SessionMcpServer = z.infer<typeof sessionMcpServerSchema>;

export const sessionConfigStateSchema = z.object({
  /** Model selector state; null when the provider has not exposed model configuration. */
  modelOptions: z
    .object({
      /** Provider-owned ACP config option id used when sending config updates. */
      configId: z.string(),
      selected: z.string().nullable(),
      available: z.array(modelOptionSchema),
    })
    .nullable(),
  /** Reasoning/effort selector state; null when unsupported by the provider. */
  efforts: z
    .object({
      /** Provider-owned ACP config option id used when sending config updates. */
      configId: z.string(),
      selected: z.string().nullable(),
      available: z.array(effortOptionSchema),
    })
    .nullable(),
  /** Permission/mode selector state; null when unsupported by the provider. */
  modeOptions: z
    .object({
      /** Provider-owned ACP config option id used when sending config updates. */
      configId: z.string(),
      selected: z.string().nullable(),
      available: z.array(modeOptionSchema),
    })
    .nullable(),
  /** Slash commands currently advertised by the active ACP session. */
  availableCommands: z.array(sessionCommandSchema),
});
export type SessionConfigState = z.infer<typeof sessionConfigStateSchema>;

export const initialSessionConfigState: SessionConfigState = {
  modelOptions: null,
  efforts: null,
  modeOptions: null,
  availableCommands: [],
};

export const sessionUsageSchema = z.object({
  /** Total context window capacity reported by the provider. */
  contextSize: z.number().int(),
  /** Tokens currently consumed in the active session context. */
  contextUsed: z.number().int(),
  /** Cumulative provider-reported cost, or null when the provider omits cost. */
  cost: z.object({ amount: z.number(), currency: z.string() }).nullable(),
  /** Provider account limits reported beside usage (Claude); absent for others. */
  rateLimit: z
    .object({
      status: z.enum(['allowed', 'allowed_warning', 'rejected']),
      resetsAt: z.number().optional(),
      rateLimitType: z.string().optional(),
      utilization: z.number().optional(),
    })
    .optional(),
});
export type SessionUsage = z.infer<typeof sessionUsageSchema>;
