import type { Logger } from '@emdash/shared/logger';
import type { Clock } from '@emdash/shared/scheduling';
import type {
  AcpStartInputWire,
  PromptAttachment,
  PromptInput,
  PromptPlacement,
} from '#runtimes/acp/api';
import type { AcpProcessHost } from '#runtimes/acp/api/transport';
import type { AgentPluginHost, ResolvedAcpProvider } from '#services/agent-plugins/api/plugins';
import type { ConversationLifecycleReporter } from '#services/conversation-reports/node';
import type { SessionIntentStore } from '#services/session-intents/api';
import type { IdlePolicyConfig } from '#services/session-lifecycle/api';
import type { AttachmentStore } from './attachment-store';

export type AcpStartInput = AcpStartInputWire;

export type ResolveAcpProvider = (providerId: string) => ResolvedAcpProvider | null;

export interface ResolvedPromptAttachment {
  data: string;
  mimeType: string;
}

export type ResolvePromptAttachment = (
  conversationId: string,
  attachment: PromptAttachment
) => Promise<ResolvedPromptAttachment>;

export type AcpRuntimeProcessHost = Omit<AcpProcessHost, 'resolveSpawnContext'>;

export interface AcpRuntimeDeps {
  agentHost: AgentPluginHost;
  host: AcpRuntimeProcessHost;
  resolveAttachment: ResolvePromptAttachment;
  attachmentStore?: AttachmentStore;
  intents: SessionIntentStore;
  /** Lifecycle reports into the conversation index (spec §3.3); defaults to a no-op. */
  conversationReports?: ConversationLifecycleReporter;
  clock?: Clock;
  lifecycle?: {
    session?: IdlePolicyConfig;
    sweepIntervalMs?: number;
    connectionIdleTtlMs?: number;
  };
  logger: Logger;
}

export interface SendPromptInput {
  conversationId: string;
  prompt: PromptInput;
  /** 'queue' always queues; 'auto' (default) delivers if idle and queues while a turn is active. */
  placement?: PromptPlacement;
}
