import { z } from 'zod';
import { acpPermissionRequestSchema } from './permissions';
import { queuedPromptSchema } from './prompt';

export const stopReasonSchema = z.enum([
  'end_turn',
  'max_tokens',
  'max_turn_requests',
  'refusal',
  'cancelled',
]);
export type StopReason = z.infer<typeof stopReasonSchema>;

/**
 * ACP session lifecycle owned by the SessionMachine.
 *
 * - `starting`: agent process/session setup is in progress.
 * - `replaying`: an existing ACP session is loading historical updates.
 * - `ready`: no foreground work is active; a prompt can start immediately.
 * - `working`: a foreground user prompt turn is running.
 * - `cancelling`: cancellation was requested; waiting for agent settlement.
 * - `closed`: runtime session is no longer usable.
 */
export const sessionLifecycleSchema = z.enum([
  'starting',
  'replaying',
  'ready',
  'working',
  'cancelling',
  'closed',
]);
export type SessionLifecycle = z.infer<typeof sessionLifecycleSchema>;

export const sessionStateSchema = z.object({
  lifecycle: sessionLifecycleSchema,
  /** Current control-plane turn id, or null when no prompt/replay turn is active. */
  activeTurnId: z.string().nullable(),
  pendingPermissions: z.array(acpPermissionRequestSchema),
  /** Last ACP prompt stop reason observed by the machine; separate from transcript outcomes. */
  lastStopReason: stopReasonSchema.nullable(),
  /** True when the last turn failed without producing an ACP stop reason. */
  lastTurnErrored: z.boolean(),
  /** Prompts accepted while busy; attachments are references, never inline bytes. */
  queuedPrompts: z.array(queuedPromptSchema),
  /** True while agent-originated updates are still arriving outside a user prompt turn. */
  agentTurnActive: z.boolean(),
  /** Count of running background subagents, used for affordances and busy state. */
  backgroundAgentCount: z.number().int(),
  /** Machine-owned UI affordance: true while foreground or background work is active. */
  isGenerating: z.boolean(),
  /** Machine-owned UI affordance: true when a prompt may be accepted or queued. */
  canSubmit: z.boolean(),
  /** Machine-owned UI affordance: true when there is cancellable foreground/agent work. */
  canCancel: z.boolean(),
});
export type SessionState = z.infer<typeof sessionStateSchema>;

export const sessionSummarySchema = z.object({
  conversationId: z.string(),
  providerId: z.string(),
  cwd: z.string().optional(),
  lifecycle: sessionLifecycleSchema,
  isGenerating: z.boolean(),
  lastStopReason: stopReasonSchema.nullable(),
  lastTurnErrored: z.boolean(),
  pendingPermissionCount: z.number().int(),
  backgroundAgentCount: z.number().int(),
  queuedPromptCount: z.number().int(),
  title: z.string().nullable(),
  updatedAt: z.number(),
  lastInputAt: z.number().int().optional(),
  lastOutputAt: z.number().int().optional(),
});
export type SessionSummary = z.infer<typeof sessionSummarySchema>;
