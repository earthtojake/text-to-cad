import { z } from 'zod';
import { promptAttachmentSchema } from './attachments';
export type { PromptAttachment } from './attachments';

const HIDDEN_CONTEXT_PREFIX = '<!-- hardcore-internal-context:v1:';
const HIDDEN_CONTEXT_OPEN_SUFFIX = ':begin -->';
const LEGACY_CAD_CONTEXT_MARKER = "You are working from Hardcore's integrated CAD workspace.";
const LEGACY_CAD_TARGET_SIGNATURE = 'The current CAD target is:';
const LEGACY_CAD_DETAIL_SIGNATURES = [
  'The files currently associated with this focus are:',
  'The model-owned files are:',
  'The current validated model revision is:',
] as const;

function hiddenContextClose(nonce: string): string {
  return `<!-- hardcore-internal-context:v1:${nonce}:end -->`;
}

/**
 * Keeps app-supplied prompt context recognizable when a provider flattens ACP
 * content blocks into its persisted user message. The runtime strips this
 * envelope from replayed transcript events before they reach the UI.
 */
export function encodePromptHiddenContext(context: string): string {
  const nonce = crypto.randomUUID();
  return `\n\n${HIDDEN_CONTEXT_PREFIX}${nonce}${HIDDEN_CONTEXT_OPEN_SUFFIX}\n${context}\n${hiddenContextClose(nonce)}`;
}

export function stripPromptHiddenContext(text: string): string {
  const openPattern = new RegExp(
    `\\n\\n${HIDDEN_CONTEXT_PREFIX}([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})${HIDDEN_CONTEXT_OPEN_SUFFIX}\\n`,
    'gi'
  );
  let visible = '';
  let cursor = 0;
  let removed = false;

  while (true) {
    openPattern.lastIndex = cursor;
    const match = openPattern.exec(text);
    if (!match || match.index < cursor) break;

    const nonce = match[1];
    if (!nonce) break;
    visible += text.slice(cursor, match.index);

    const close = hiddenContextClose(nonce);
    const closeStart = text.indexOf(close, openPattern.lastIndex);
    if (closeStart < 0) {
      // Once an app-owned, collision-resistant opener is present, fail closed.
      // A truncated provider replay must not expose internal routing text.
      return visible.trimEnd();
    }

    removed = true;
    cursor = closeStart + close.length;
  }

  const withoutEnvelope = removed ? `${visible}${text.slice(cursor)}`.trimEnd() : text;
  return stripLegacyCadContext(withoutEnvelope);
}

/**
 * Older Hardcore builds appended CAD routing text directly to the user prompt.
 * Keep those existing chat histories readable while requiring the complete
 * legacy signature so ordinary user text containing the product name survives.
 */
function stripLegacyCadContext(text: string): string {
  const markerIndex = text.indexOf(LEGACY_CAD_CONTEXT_MARKER);
  if (markerIndex < 0) return text;

  const legacyContext = text.slice(markerIndex);
  if (
    !legacyContext.includes(LEGACY_CAD_TARGET_SIGNATURE) ||
    !LEGACY_CAD_DETAIL_SIGNATURES.some((signature) => legacyContext.includes(signature))
  ) {
    return text;
  }

  return text.slice(0, markerIndex).trimEnd();
}

export const promptInputSchema = z.object({
  text: z.string(),
  hiddenContext: z.string().optional(),
  attachments: z.array(promptAttachmentSchema).optional(),
});
export type PromptInput = z.infer<typeof promptInputSchema>;

export const promptDraftInputSchema = promptInputSchema.extend({
  /** Monotonic writer revision used by clients to suppress stale draft echoes. */
  rev: z.number(),
});
export type PromptDraftInput = z.infer<typeof promptDraftInputSchema>;

export const promptDraftSchema = promptDraftInputSchema.extend({
  /** Epoch ms when the runtime last accepted this draft revision. */
  updatedAt: z.number(),
});
export type PromptDraft = z.infer<typeof promptDraftSchema>;

export const promptDraftUpdateSchema = z.object({
  /** Monotonic writer revision used to ignore stale draft updates, including clears. */
  rev: z.number(),
  input: promptInputSchema.nullable(),
});
export type PromptDraftUpdate = z.infer<typeof promptDraftUpdateSchema>;

export const queuedPromptSchema = promptInputSchema.extend({
  /** Runtime-generated id used for queue removal and stable UI keys. */
  id: z.string(),
  /** Epoch ms when this prompt entered the runtime queue/model. */
  createdAt: z.number(),
  /** Epoch ms when queued prompt content or attachments were last edited. */
  updatedAt: z.number(),
});
export type QueuedPrompt = z.infer<typeof queuedPromptSchema>;
