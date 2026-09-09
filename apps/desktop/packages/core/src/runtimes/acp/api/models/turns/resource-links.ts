import { z } from 'zod';

export const resourceTargetSchema = z.union([
  z.object({ kind: z.literal('workspace-file'), path: z.string() }),
  z.object({ kind: z.literal('external'), url: z.string() }),
  z.object({ kind: z.literal('opaque') }),
]);
export type ResourceTarget = z.infer<typeof resourceTargetSchema>;

/** A resource the agent linked in a message, shown as its own row after the text. */
export const transcriptResourceLinkSchema = z.object({
  kind: z.literal('resource-link'),
  id: z.string(),
  /** Stable order within the owning turn, assigned once by the reducer. */
  seq: z.number().int(),
  uri: z.string(),
  name: z.string(),
  title: z.string().optional(),
  description: z.string().optional(),
  mimeType: z.string().optional(),
  size: z.number().optional(),
  /** Where the link points, resolved once so renderers stay transport-agnostic. */
  target: resourceTargetSchema,
});
export type TranscriptResourceLink = z.infer<typeof transcriptResourceLinkSchema>;

/** file: URIs open in the editor, http(s) URLs open externally, anything else is shown only. */
export function resolveResourceTarget(uri: string): ResourceTarget {
  try {
    const parsed = new URL(uri);
    if (parsed.protocol === 'file:') {
      return { kind: 'workspace-file', path: decodeURIComponent(parsed.pathname) };
    }
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
      return { kind: 'external', url: uri };
    }
  } catch {
    if (uri.startsWith('/')) return { kind: 'workspace-file', path: uri };
  }
  return { kind: 'opaque' };
}
