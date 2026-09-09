import type { Logger } from '@emdash/shared/logger';
import type { PromptAttachment, QueuedPrompt } from '#runtimes/acp/api';
import type { AcpAgentApi } from '#services/agent-plugins/api/plugins';

export interface ResolvedPromptAttachment {
  data: string;
  mimeType: string;
}

export type ResolvePromptAttachment = (
  conversationId: string,
  attachment: PromptAttachment
) => Promise<ResolvedPromptAttachment>;

export interface SessionCellCallbacks {
  onSessionStateChanged?: () => void;
  onTranscriptChanged?: () => void;
  onDraftChanged?: () => void;
  onClosed?: (exitCode: number | null) => void;
  onAgentEvent?: (phase: 'start' | 'stop' | 'error') => void;
  onSendQueuedPrompt?: (prompt: QueuedPrompt) => void;
}

export interface SessionCellDeps {
  conversationId: string;
  providerId: string;
  acpSessionId: string;
  agent: AcpAgentApi;
  resolveAttachment: ResolvePromptAttachment;
  logger: Logger;
  callbacks?: SessionCellCallbacks;
}

export interface SessionPromptResult {
  queued: boolean;
}
