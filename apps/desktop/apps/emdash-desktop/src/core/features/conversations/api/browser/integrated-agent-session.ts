import type {
  ChatContext,
  ChatState,
} from '@core/features/conversations/api/browser/chat/chat-transcript';
import { conversationRegistry } from '@core/features/conversations/api/browser/stores/conversation-registry';
import { getAcpChatResourceManager } from '@core/features/conversations/browser/acp/acp-chat-resource-manager';
import type {
  AcpChatStore,
  AcpPromptAttachment,
} from '@core/features/conversations/browser/acp/acp-chat-store';
import type { AgentStatus } from '@core/primitives/agents/api';

export type IntegratedAgentAttachment = AcpPromptAttachment;

export interface IntegratedAgentSession {
  readonly conversationId: string;
  readonly providerId: string | null;
  readonly status: AgentStatus;
  readonly isLoading: boolean;
  readonly isWorking: boolean;
  readonly canSubmit: boolean;
  readonly canCancel: boolean;
  readonly error: string | null;
  readonly chatContext: ChatContext;
  readonly chatState: ChatState;
  readonly messageCount: number;
  readonly modelId: string | null;
  readonly modelLabel: string | null;
  readonly modelOptions: ReadonlyArray<{
    id: string;
    name: string;
    description?: string;
  }>;
  submitPrompt(
    text: string,
    hiddenContext?: string,
    attachments?: IntegratedAgentAttachment[]
  ): void;
  uploadPng(
    data: Uint8Array,
    name: string,
    previewUrl?: string
  ): Promise<IntegratedAgentAttachment | null>;
  setModel(modelId: string): void;
  stop(): void;
  retry(): void;
  dispose(): void;
}

class AcpIntegratedAgentSession implements IntegratedAgentSession {
  constructor(
    private readonly store: AcpChatStore,
    private readonly release: () => void
  ) {
    store.bootstrap();
  }

  get conversationId(): string {
    return this.store.conversationId;
  }

  get providerId(): string | null {
    return (
      conversationRegistry.get(this.store.taskId)?.conversations.get(this.store.conversationId)
        ?.data.providerId ?? null
    );
  }

  get status(): AgentStatus {
    return (
      conversationRegistry.get(this.store.taskId)?.conversations.get(this.store.conversationId)
        ?.status ?? 'idle'
    );
  }

  get isLoading(): boolean {
    return this.store.historyLoading;
  }

  get isWorking(): boolean {
    return this.store.affordances.isWorking;
  }

  get canSubmit(): boolean {
    return this.store.affordances.canSubmit;
  }

  get canCancel(): boolean {
    return this.store.affordances.canCancel;
  }

  get error(): string | null {
    return this.store.loadError?.message ?? null;
  }

  get chatContext(): ChatContext {
    return this.store.chatContext;
  }

  get chatState(): ChatState {
    return this.store.chatState;
  }

  get messageCount(): number {
    return this.store.messageCount;
  }

  get modelId(): string | null {
    return this.store.model;
  }

  get modelLabel(): string | null {
    return this.store.modelLabel;
  }

  get modelOptions(): ReadonlyArray<{ id: string; name: string; description?: string }> {
    return Object.entries(this.store.modelOptions ?? {}).map(([id, option]) => ({ id, ...option }));
  }

  submitPrompt(
    text: string,
    hiddenContext?: string,
    attachments: IntegratedAgentAttachment[] = []
  ): void {
    this.store.submitPrompt(text, attachments, hiddenContext);
  }

  async uploadPng(
    data: Uint8Array,
    name: string,
    previewUrl?: string
  ): Promise<IntegratedAgentAttachment | null> {
    const ref = await this.store.uploadAttachment({ data, mimeType: 'image/png', name });
    return ref
      ? {
          ref: {
            type: 'attachment',
            id: ref.id,
            mimeType: ref.mimeType,
            name: ref.name,
          },
          previewUrl,
        }
      : null;
  }

  setModel(modelId: string): void {
    this.store.setModel(modelId);
  }

  stop = (): void => {
    this.store.stop();
  };

  retry = (): void => {
    this.store.retry();
  };

  dispose(): void {
    this.release();
  }
}

export function acquireIntegratedAgentSession(input: {
  conversationId: string;
  projectId: string;
  taskId: string;
}): IntegratedAgentSession {
  const manager = getAcpChatResourceManager(input.taskId, input.projectId);
  const store = manager.acquire(input.conversationId);
  return new AcpIntegratedAgentSession(store, () => manager.release(input.conversationId));
}
