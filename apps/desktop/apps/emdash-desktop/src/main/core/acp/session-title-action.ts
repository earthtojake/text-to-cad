import type { SessionSummary } from '@emdash/core/runtimes/acp/api';

export type AcpSessionTitleAction = { conversationId: string; title: string };

export function deriveAcpSessionTitleAction(
  previous: SessionSummary | undefined,
  next: SessionSummary
): AcpSessionTitleAction | null {
  if (!next.title) return null;
  if (previous?.title === next.title) return null;
  return { conversationId: next.conversationId, title: next.title };
}
