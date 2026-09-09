import { type Conversation } from '@core/primitives/conversations/api';

export type EnsureConversationSessionMode = 'start' | 'resume';

export type EnsureConversationSessionOutcome =
  | 'started'
  | 'resumed'
  | 'attached'
  | 'fresh-fallback';

export type EnsureConversationSessionRequest = {
  conversation: Conversation;
  mode: EnsureConversationSessionMode;
  initialSize?: { cols: number; rows: number };
  initialPrompt?: string;
};

export type EnsureConversationSessionResult = {
  outcome: EnsureConversationSessionOutcome;
};

export interface ConversationProvider {
  ensureSession(
    request: EnsureConversationSessionRequest
  ): Promise<EnsureConversationSessionResult>;
  detachSession(conversationId: string): Promise<void>;
  stopSession(conversationId: string): Promise<void>;
  deleteSession(conversationId: string): Promise<void>;
  destroyAll(): Promise<void>;
  detachAll(): Promise<void>;
}

export type ConversationConfig = {
  autoApprove?: boolean;
  /** Provider-native session id (e.g. Codex rollout UUID) used when resuming. */
  providerSessionId?: string;
};
