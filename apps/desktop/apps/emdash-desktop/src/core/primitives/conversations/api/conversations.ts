import type { AgentProviderId } from '@emdash/plugins/agents/types';
import type { AgentStatus } from '@core/primitives/agents/api';

export const MAX_CONVERSATION_TITLE_LENGTH = 100;

export type ConversationType = 'pty' | 'acp';

export type InitialQueuePrompt = {
  text: string;
  hiddenContext?: string;
};

export type Conversation = {
  id: string;
  projectId: string;
  taskId: string;
  providerId: AgentProviderId;
  title: string;
  lastInteractedAt: string | null;
  autoApprove?: boolean;
  /**
   * The agent-facing session identifier. Null / absent means the conversation has never
   * successfully established a session.
   *
   * PTY conversations write a conversation.id placeholder only after the first fresh
   * process is spawned; provider hooks may later overwrite it with a native id. ACP
   * conversations store the id returned by newSession/loadSession.
   */
  sessionId?: string;
  /** Model to pass to the agent CLI. Absent or empty string means use the CLI default. */
  model?: string;
  /** Stable product resource identity for conversations owned by a domain workspace. */
  contextKey?: string;
  /** Last user-selected ACP session mode id (provider-specific), re-applied on session start. */
  modeId?: string;
  /** Initial queued prompts to deliver on first ACP spawn. Only present before sessionId is set. */
  initialQueue?: InitialQueuePrompt[];
  isInitialConversation: boolean | null;
  agentStatus?: AgentStatus | null;
  agentStatusSeen?: boolean;
  /** Transport type: 'pty' (default) uses the terminal/PTY path; 'acp' uses the Agent Client Protocol. */
  type?: ConversationType;
};

export type ConversationEvent =
  | {
      type: 'changed';
      conversationId: string;
      taskId: string;
      projectId: string;
      changes: Partial<
        Pick<Conversation, 'lastInteractedAt' | 'title' | 'sessionId' | 'model' | 'modeId'>
      >;
    }
  | { type: 'created'; conversation: Conversation }
  | {
      type: 'agent-status-changed';
      conversationId: string;
      taskId: string;
      projectId: string;
      status: AgentStatus;
      seen: boolean;
    };

export type RenameConversationParams = {
  conversationId: string;
  newTitle: string;
};

/** Which host's cached conversation observations to list. */
export type HostConversationScope = {
  location: 'local' | 'remote';
  sshConnectionId: string | null;
};

/**
 * One cached host conversation observation for the machine page (spec §8): the full
 * registry row shape — task-linked and orphaned alike — unlike `Conversation`, which
 * only exists for task-linked records.
 */
export type HostConversationRow = {
  id: string;
  title: string;
  provider: string | null;
  type: string | null;
  projectId: string | null;
  taskId: string | null;
  /** Resolved link names for presentation; null when the link is absent or dangling. */
  projectName: string | null;
  taskName: string | null;
  workspacePath: string | null;
  lastSessionActivityAt: string | null;
  observedStatus: 'present' | 'missing' | null;
  lastObservedAt: string | null;
  createdAt: string;
  updatedAt: string;
  /** Live row carrying a deletion tombstone: removal pending until the sweep converges. */
  pendingRemoval: boolean;
};

export type CreateConversationParams = {
  id: string;
  projectId: string;
  taskId: string;
  provider: AgentProviderId;
  title: string;
  autoApprove?: boolean;
  /** Model to pass to the agent CLI. Absent or empty string means use the CLI default. */
  model?: string;
  /** Stable product resource identity for conversations owned by a domain workspace. */
  contextKey?: string;
  isInitialConversation?: boolean;
  initialSize?: { cols: number; rows: number };
  initialPrompt?: string;
  initialQueue?: InitialQueuePrompt[];
  /** Transport type: 'pty' (default) uses the terminal/PTY path; 'acp' uses the Agent Client Protocol. */
  type?: ConversationType;
};
