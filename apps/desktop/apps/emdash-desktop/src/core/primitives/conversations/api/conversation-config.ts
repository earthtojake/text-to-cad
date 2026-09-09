import { defineVersionedSchema } from '@emdash/core/primitives/versioned-schema/api';
import z from 'zod';

const conversationConfigV0Schema = z.object({
  autoApprove: z.boolean().optional(),
  /** @deprecated Moved to conversations.session_id column; stripped on upgrade to v1. */
  providerSessionId: z.string().optional(),
  initialPrompt: z.string().optional(),
  /** Model to pass to the agent CLI (e.g. 'claude-sonnet-5', 'o4-mini'). Empty string or absent = CLI default. */
  model: z.string().optional(),
});

const initialQueuePromptSchema = z.object({
  text: z.string(),
  hiddenContext: z.string().optional(),
});

const ptyConfigV1 = z.object({
  version: z.literal('1'),
  type: z.literal('pty'),
  autoApprove: z.boolean().optional(),
  /** Initial prompt to deliver once, before the first successful PTY session id is persisted. */
  initialPrompt: z.string().optional(),
  /** Model to pass to the agent CLI. Empty string or absent = CLI default. */
  model: z.string().optional(),
});

const acpConfigV1 = z.object({
  version: z.literal('1'),
  type: z.literal('acp'),
  autoApprove: z.boolean().optional(),
  /** @deprecated Use initialQueue; kept so older in-progress ACP configs remain readable. */
  initialPrompt: z.string().optional(),
  /** Initial queued prompts to deliver once, before the first successful ACP session id is persisted. */
  initialQueue: z.array(initialQueuePromptSchema).optional(),
  /** Model to pass to the agent CLI. Empty string or absent = CLI default. */
  model: z.string().optional(),
  /** Stable product resource identity for conversations owned by a domain workspace. */
  contextKey: z.string().optional(),
  /** Last user-selected ACP session mode id (provider-specific), re-applied on session start. */
  modeId: z.string().optional(),
});

export const conversationConfig = defineVersionedSchema()
  .unversioned(conversationConfigV0Schema)
  .version(
    '1',
    z.discriminatedUnion('type', [ptyConfigV1, acpConfigV1]),
    (v0) =>
      ({
        version: '1' as const,
        type: 'pty' as const,
        autoApprove: v0.autoApprove,
        initialPrompt: v0.initialPrompt,
        model: v0.model,
        // providerSessionId is intentionally dropped; it now lives in conversations.session_id
      }) satisfies z.infer<typeof ptyConfigV1>
  )
  .build();

export type ConversationConfig = typeof conversationConfig.Type;
export type ConversationConfigPty = z.infer<typeof ptyConfigV1>;
export type ConversationConfigAcp = z.infer<typeof acpConfigV1>;
