import { z } from 'zod';

export const transcriptThinkingSchema = z.object({
  kind: z.literal('thinking'),
  id: z.string(),
  /** Stable order within the owning turn, assigned once by the reducer. */
  seq: z.number().int(),
  /** Provider or synthesized stream segment id for merging reasoning chunks. */
  segmentId: z.string(),
  text: z.string(),
  status: z.enum(['thinking', 'done']),
  /** Epoch ms when the thinking row opened. */
  startedAt: z.number(),
  /** Frozen duration once the row is finalized. */
  durationMs: z.number().optional(),
});
export type TranscriptThinking = z.infer<typeof transcriptThinkingSchema>;

/**
 * Approximate a provider token count from streamed reasoning text.
 *
 * ACP exposes the reasoning text but not a dedicated reasoning-token usage
 * field. Four UTF-8 bytes per token is a deliberately simple, visibly
 * approximate estimate; callers must present the result with a `~` marker.
 */
export function estimateThinkingTokens(text: string): number {
  const normalized = text.trim();
  if (!normalized) return 0;
  return Math.max(1, Math.ceil(new TextEncoder().encode(normalized).byteLength / 4));
}
