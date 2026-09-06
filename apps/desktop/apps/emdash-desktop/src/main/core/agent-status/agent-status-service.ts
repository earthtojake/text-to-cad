import { isAttentionNotification } from '@emdash/core/runtimes/tui-agents/api';
import { and, eq, inArray } from 'drizzle-orm';
import {
  type AgentEvent,
  type AgentStatus,
  type AgentStatusSignal,
} from '@core/primitives/agents/api';
import type { ConversationEvent } from '@core/primitives/conversations/api';
import { HookCore, type Hookable } from '@core/primitives/hooks/api/hookable';
import { conversations } from '@core/services/app-db/node/schema';
import { getAppDb } from '@main/db/instance';
import { log } from '@main/lib/logger';

export type AgentStatusServiceHooks = {
  'agent:event': (event: AgentEvent) => void | Promise<void>;
};

export type ApplyAgentStatusSignalOptions = {
  deliver?: boolean;
  preserveSeen?: boolean;
};

type ConversationContext = {
  projectId: string;
  taskId: string;
  providerId: string | null;
};

let publishConversationEvent: (event: ConversationEvent) => void = () => {};

export function setAgentStatusConversationEventPublisher(
  publisher: (event: ConversationEvent) => void
): void {
  publishConversationEvent = publisher;
}

function conversationContextSelection() {
  return {
    projectId: conversations.projectId,
    taskId: conversations.taskId,
    providerId: conversations.provider,
  };
}

function deriveAgentStatus(event: AgentStatusSignal): AgentStatus | null {
  if (event.type === 'start') return 'working';
  if (event.type === 'stop') return 'completed';
  if (event.type === 'error') return 'error';
  if (event.type === 'notification') {
    const nt = event.payload.notificationType;
    if (!nt) return null;
    if (isAttentionNotification(nt)) return 'awaiting-input';
  }
  return null;
}

export class AgentStatusService implements Hookable<AgentStatusServiceHooks> {
  private readonly queues = new Map<string, Promise<void>>();
  private readonly hooks = new HookCore<AgentStatusServiceHooks>((name, error) =>
    log.error(`AgentStatusService: ${String(name)} hook error`, error)
  );

  on<K extends keyof AgentStatusServiceHooks>(name: K, handler: AgentStatusServiceHooks[K]) {
    return this.hooks.on(name, handler);
  }

  applySignal(
    signal: AgentStatusSignal,
    options: ApplyAgentStatusSignalOptions = {}
  ): Promise<void> {
    return this.enqueue(signal.conversationId, () => this.applySignalQueued(signal, options));
  }

  cacheSignal(signal: AgentStatusSignal): Promise<void> {
    return this.applySignal(signal, { deliver: false, preserveSeen: true });
  }

  resetToIdle(params: { conversationId: string }): Promise<void> {
    return this.enqueue(params.conversationId, () => this.resetToIdleQueued(params.conversationId));
  }

  private async applySignalQueued(
    signal: AgentStatusSignal,
    options: ApplyAgentStatusSignalOptions
  ): Promise<void> {
    const deliver = options.deliver ?? true;
    const status = deriveAgentStatus(signal);
    let context: ConversationContext;

    if (status) {
      const derivedSeen = status === 'working' ? 1 : 0;
      // Direct write is sanctioned: agent_status/agent_status_seen are a device-local
      // cache outside the registry's observation discipline (see schema comment).
      const [row] = await getAppDb()
        .update(conversations)
        .set(
          options.preserveSeen
            ? { agentStatus: status }
            : { agentStatus: status, agentStatusSeen: derivedSeen }
        )
        .where(eq(conversations.id, signal.conversationId))
        .returning({
          ...conversationContextSelection(),
          agentStatusSeen: conversations.agentStatusSeen,
        });
      if (!row) return;
      // Unlinked mirror rows have no task surface to notify.
      if (row.projectId === null || row.taskId === null) return;

      context = { projectId: row.projectId, taskId: row.taskId, providerId: row.providerId };
      publishConversationEvent({
        type: 'agent-status-changed',
        conversationId: signal.conversationId,
        taskId: row.taskId,
        projectId: row.projectId,
        status,
        seen: (row.agentStatusSeen ?? derivedSeen) === 1,
      });
    } else {
      const [row] = await getAppDb()
        .select(conversationContextSelection())
        .from(conversations)
        .where(eq(conversations.id, signal.conversationId))
        .limit(1);
      if (!row) return;
      if (row.projectId === null || row.taskId === null) return;
      context = { projectId: row.projectId, taskId: row.taskId, providerId: row.providerId };
    }

    if (deliver) {
      this.hooks.callHookBackground('agent:event', {
        ...signal,
        providerId: signal.providerId ?? context.providerId ?? undefined,
        projectId: context.projectId,
        taskId: context.taskId,
      });
    }
  }

  private async resetToIdleQueued(conversationId: string): Promise<void> {
    const [row] = await getAppDb()
      .update(conversations)
      .set({ agentStatus: 'idle', agentStatusSeen: 1 })
      .where(
        and(
          eq(conversations.id, conversationId),
          inArray(conversations.agentStatus, ['working', 'awaiting-input'])
        )
      )
      .returning(conversationContextSelection());
    if (!row) return;
    if (row.projectId === null || row.taskId === null) return;

    publishConversationEvent({
      type: 'agent-status-changed',
      conversationId,
      taskId: row.taskId,
      projectId: row.projectId,
      status: 'idle',
      seen: true,
    });
  }

  private enqueue(conversationId: string, work: () => Promise<void>): Promise<void> {
    const previous = this.queues.get(conversationId) ?? Promise.resolve();
    const current = previous.catch(() => undefined).then(work);
    this.queues.set(conversationId, current);
    void current.then(
      () => this.removeQueue(conversationId, current),
      () => this.removeQueue(conversationId, current)
    );
    return current;
  }

  private removeQueue(conversationId: string, queue: Promise<void>): void {
    if (this.queues.get(conversationId) === queue) this.queues.delete(conversationId);
  }

  async dispose(): Promise<void> {
    while (this.queues.size > 0) {
      await Promise.allSettled(this.queues.values());
    }
  }
}

export const agentStatusService = new AgentStatusService();
