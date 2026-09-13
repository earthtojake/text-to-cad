import { z } from 'zod';

const nonBlankStringSchema = z.string().trim().min(1);

/**
 * Common error surface for starting a headless session. Runtime-specific
 * errors may carry additional fields; automations only need the tag and
 * optional message.
 */
export const sessionStartErrorSchema = z.object({
  type: nonBlankStringSchema,
  message: z.string().optional(),
});

export const headlessPromptInputSchema = z.object({
  text: nonBlankStringSchema,
  hiddenContext: z.string().optional(),
});

export const acpSessionStartInputSchema = z.object({
  conversationId: nonBlankStringSchema,
  providerId: nonBlankStringSchema,
  cwd: nonBlankStringSchema,
  sessionId: z.null(),
  model: nonBlankStringSchema.nullable(),
  modeId: nonBlankStringSchema.nullable().optional(),
  initialQueue: z.array(headlessPromptInputSchema).min(1),
});

export const acpSessionStartResultSchema = z.object({
  sessionId: nonBlankStringSchema,
});

export const tuiSessionStartInputSchema = z.object({
  conversationId: nonBlankStringSchema,
  providerId: nonBlankStringSchema,
  cwd: nonBlankStringSchema,
  sessionId: z.null(),
  model: nonBlankStringSchema.nullable(),
  initialPrompt: nonBlankStringSchema,
  autoApprove: z.boolean(),
  cols: z.number().int().positive(),
  rows: z.number().int().positive(),
});

export const tuiSessionStartResultSchema = z.object({
  outcome: z.enum(['started', 'attached']),
});

export type SessionStartError = z.infer<typeof sessionStartErrorSchema>;
export type AcpSessionStartInput = z.infer<typeof acpSessionStartInputSchema>;
export type AcpSessionStartResult = z.infer<typeof acpSessionStartResultSchema>;
export type TuiSessionStartInput = z.infer<typeof tuiSessionStartInputSchema>;
export type TuiSessionStartResult = z.infer<typeof tuiSessionStartResultSchema>;
