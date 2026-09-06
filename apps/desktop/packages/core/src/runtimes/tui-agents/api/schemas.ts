import { z } from 'zod';
import { gitCredentialsSessionSpecSchema } from '#primitives/git-credentials/api';
import { runtimeUnavailableErrorSchema } from '#workspace-server/shared/schemas';

export const tuiAgentStartInputSchema = z.object({
  /** Logical session key — used as the PTY registry key and emitted on events. */
  conversationId: z.string(),
  providerId: z.string(),
  cwd: z.string(),
  /** Provider-native session id; drives resume routing per provider. */
  sessionId: z.string().nullable(),
  /**
   * Emdash-chosen resume handle for fresh spawns (spec §3.1, emdash-chosen regime): the
   * caller's convention for resuming this session when no provider-native id is captured.
   * Reported to the conversation index as the spawned session's provider session id.
   */
  chosenSessionId: z.string().nullable().optional(),
  model: z.string().nullable(),
  initialPrompt: z.string().optional(),
  autoApprove: z.boolean().optional(),
  trustWorkspace: z.boolean().optional(),
  extraArgs: z.array(z.string()).optional(),
  providerVars: z.record(z.string(), z.string()).optional(),
  /**
   * Per-session git credential behavior, resolved desktop-side from project
   * settings (spec: github-git-settings §4). Absent = native behavior.
   */
  gitCredentials: gitCredentialsSessionSpecSchema.optional(),
  cols: z.number().int(),
  rows: z.number().int(),
  shellSetup: z.string().optional(),
  tmuxSessionName: z.string().optional(),
});

export type TuiAgentStartInput = z.infer<typeof tuiAgentStartInputSchema>;

export const tuiStartOutcomeSchema = z.enum(['started', 'attached']);

export type TuiStartOutcome = z.infer<typeof tuiStartOutcomeSchema>;

export const tuiResumeOutcomeSchema = z.enum(['resumed', 'attached', 'fresh-fallback']);

export type TuiResumeOutcome = z.infer<typeof tuiResumeOutcomeSchema>;

export const tuiOutputEventSchema = z.discriminatedUnion('kind', [
  z.object({
    kind: z.literal('chunk'),
    data: z.string(),
    /** Monotonic byte offset of the first byte of this chunk in the full output log. */
    offset: z.number().int(),
  }),
  z.object({
    kind: z.literal('reset'),
    /** Full retained ring-buffer content, delivered when the requested offset is stale. */
    data: z.string(),
    offset: z.number().int(),
  }),
  z.object({
    kind: z.literal('exit'),
    exitCode: z.number().int().nullable(),
    signal: z.union([z.number().int(), z.string()]).optional(),
  }),
]);

export type TuiOutputEvent = z.infer<typeof tuiOutputEventSchema>;

export const tuiSessionResumeStateSchema = z.object({
  requested: z.boolean(),
  outcome: z.enum(['pending', 'resumed', 'fresh-fallback']),
  reason: z.string().optional(),
});

export type TuiSessionResumeState = z.infer<typeof tuiSessionResumeStateSchema>;

export const tuiSessionStateSchema = z.object({
  conversationId: z.string(),
  providerId: z.string().optional(),
  cwd: z.string().optional(),
  /** Provider-native session id, published from the provider hook stream. */
  sessionId: z.string().nullable(),
  status: z.enum(['starting', 'running', 'exited']),
  pid: z.number().int().optional(),
  cols: z.number().int(),
  rows: z.number().int(),
  isRemote: z.boolean().optional(),
  title: z.string().optional(),
  resume: tuiSessionResumeStateSchema.nullable(),
  /** Unix ms timestamp when the session was started. */
  startedAt: z.number().int(),
  lastInputAt: z.number().int().optional(),
  lastOutputAt: z.number().int().optional(),
  exit: z
    .object({
      exitCode: z.number().int().nullable(),
      signal: z.union([z.number().int(), z.string()]).optional(),
    })
    .optional(),
});

export type TuiSessionState = z.infer<typeof tuiSessionStateSchema>;

export const tuiSessionListSchema = z.record(z.string(), tuiSessionStateSchema);

export type TuiSessionList = z.infer<typeof tuiSessionListSchema>;

export const tuiAgentStateStatusSchema = z.enum([
  'idle',
  'working',
  'awaiting-input',
  'error',
  'completed',
]);

export type TuiAgentStateStatus = z.infer<typeof tuiAgentStateStatusSchema>;

export const tuiNotificationTypeSchema = z.enum([
  'permission_prompt',
  'idle_prompt',
  'auth_success',
  'elicitation_dialog',
]);

export type TuiNotificationType = z.infer<typeof tuiNotificationTypeSchema>;

/** Notification types that require explicit user attention before the agent can continue. */
export const ATTENTION_NOTIFICATION_TYPES: ReadonlySet<TuiNotificationType> = new Set([
  'permission_prompt',
  'idle_prompt',
  'elicitation_dialog',
]);

export function isAttentionNotification(
  nt: TuiNotificationType | undefined
): nt is TuiNotificationType {
  return nt != null && ATTENTION_NOTIFICATION_TYPES.has(nt);
}

export const tuiAgentStateSchema = z.object({
  conversationId: z.string(),
  providerId: z.string().optional(),
  status: tuiAgentStateStatusSchema,
  source: z.enum(['hook', 'input']).optional(),
  notificationType: tuiNotificationTypeSchema.optional(),
  title: z.string().optional(),
  message: z.string().optional(),
  lastAssistantMessage: z.string().optional(),
  updatedAt: z.number().int(),
});

export type TuiAgentState = z.infer<typeof tuiAgentStateSchema>;

export const tuiAgentStateListSchema = z.record(z.string(), tuiAgentStateSchema);

export type TuiAgentStateList = z.infer<typeof tuiAgentStateListSchema>;

export const persistedTuiAgentStartInputSchema = tuiAgentStartInputSchema.extend({
  lastAgentState: tuiAgentStateSchema.optional(),
});

export type PersistedTuiAgentStartInput = z.infer<typeof persistedTuiAgentStartInputSchema>;

export const tuiUnknownProviderErrorSchema = z.object({
  type: z.literal('unknown-provider'),
  providerId: z.string(),
});
/** Provider plugin has no TUI prompt capability. */
export const tuiNoCommandErrorSchema = z.object({
  type: z.literal('no-command'),
  providerId: z.string(),
});
export const tuiNotFoundErrorSchema = z.object({
  type: z.literal('not-found'),
  conversationId: z.string(),
});
export const tuiSpawnFailedErrorSchema = z.object({
  type: z.literal('spawn-failed'),
  conversationId: z.string(),
  message: z.string(),
});

export const tuiStartErrorSchema = z.discriminatedUnion('type', [
  tuiUnknownProviderErrorSchema,
  tuiNoCommandErrorSchema,
  tuiSpawnFailedErrorSchema,
  runtimeUnavailableErrorSchema,
]);
export const tuiResumeErrorSchema = tuiStartErrorSchema;
export const tuiSessionControlErrorSchema = runtimeUnavailableErrorSchema;
export const tuiInputErrorSchema = z.discriminatedUnion('type', [
  tuiNotFoundErrorSchema,
  runtimeUnavailableErrorSchema,
]);
export const tuiAgentErrorSchema = z.discriminatedUnion('type', [
  tuiUnknownProviderErrorSchema,
  tuiNoCommandErrorSchema,
  tuiNotFoundErrorSchema,
  tuiSpawnFailedErrorSchema,
  runtimeUnavailableErrorSchema,
]);

export type TuiAgentError = z.infer<typeof tuiAgentErrorSchema>;
export type TuiStartError = z.infer<typeof tuiStartErrorSchema>;
export type TuiResumeError = z.infer<typeof tuiResumeErrorSchema>;
export type TuiSessionControlError = z.infer<typeof tuiSessionControlErrorSchema>;
export type TuiInputError = z.infer<typeof tuiInputErrorSchema>;
