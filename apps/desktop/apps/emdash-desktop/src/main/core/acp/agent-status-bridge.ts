import { formatHostRef, LOCAL_HOST_REF, type HostRef } from '@emdash/core/primitives/host/api';
import {
  acpApiContract,
  sessionSummarySchema,
  type AcpApiContract,
  type SessionSummary,
} from '@emdash/core/runtimes/acp/api';
import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import type { Unsubscribe } from '@emdash/shared';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { observe, remote, whenReady } from '@emdash/wire/state';
import type { WireWorker } from '@emdash/wire/worker';
import { z } from 'zod';
import { agentStatusService } from '@main/core/agent-status/agent-status-service';
import { log } from '@main/lib/logger';
import {
  deriveAcpAgentStatusActions,
  projectAcpStatusSnapshot,
  type AcpAgentStatusAction,
} from './agent-status-transition';
import { deriveAcpSessionTitleAction, type AcpSessionTitleAction } from './session-title-action';

type SessionSummaryList = Record<string, SessionSummary>;
export type ConversationCreatedSubscription = (
  handler: (conversation: { id: string }) => void
) => Unsubscribe;

type AcpAgentStatusBridgeDependencies = {
  runtimes: RuntimeBroker;
  onLocalWorkerStateChanged: WireWorker<AcpApiContract>['onStateChanged'];
  loadActiveConversationIds(host: HostRef): Promise<string[]>;
  renameConversation: (conversationId: string, name: string) => Promise<unknown>;
};

type AcpHostAttachment = {
  scope: Scope;
  summaries: Map<string, SessionSummary>;
};

const sessionSummaryListSchema = z.record(z.string(), sessionSummarySchema);

export class AcpAgentStatusBridge {
  private readonly attachments = new Map<string, AcpHostAttachment>();
  private workerStateUnsubscribe: Unsubscribe | null = null;
  private conversationCreatedUnsubscribe: Unsubscribe | null = null;
  private dependencies: AcpAgentStatusBridgeDependencies | undefined;
  private disposed = false;

  initialize(
    onConversationCreated: ConversationCreatedSubscription,
    dependencies: AcpAgentStatusBridgeDependencies
  ): void {
    this.disposed = false;
    this.dependencies = dependencies;
    this.conversationCreatedUnsubscribe ??= onConversationCreated((conversation) =>
      this.cacheConversationSnapshot(conversation.id)
    );
    this.workerStateUnsubscribe ??= dependencies.onLocalWorkerStateChanged((state) => {
      if (state.kind === 'failed' || state.kind === 'disposed') {
        this.detachHost(LOCAL_HOST_REF);
        void this.resetHost(LOCAL_HOST_REF).catch((error) => {
          log.warn('ACP agent status bridge failed to reset local statuses after worker exit', {
            error: String(error),
          });
        });
      } else if (state.kind === 'ready') {
        void this.attachHost(LOCAL_HOST_REF).catch((error) => {
          log.warn('ACP agent status bridge failed to reattach after worker recovery', {
            error: String(error),
          });
        });
      }
    });
  }

  async attachHost(host: HostRef): Promise<void> {
    if (this.disposed) return;
    this.detachHost(host);
    const dependencies = this.dependencies;
    if (!dependencies) throw new Error('ACP agent status bridge has not been initialized');
    const client = await dependencies.runtimes.client(host);
    if (!client.success || this.disposed) return;
    const key = formatHostRef(host);
    if (this.attachments.has(key)) return;

    const scope = createScope({ label: `acp-agent-status-bridge:${key}` });
    const attachment: AcpHostAttachment = { scope, summaries: new Map() };
    this.attachments.set(key, attachment);
    const sessions = remote(acpApiContract.sessions, client.data.acp.sessions, {
      scope,
      lingerMs: 15_000,
    });
    const list = sessions(undefined).states.list;
    let first = true;
    let applyChain = Promise.resolve();
    observe(
      list,
      (snapshot) => {
        if (snapshot.status === 'loading') return;
        const summaries = sessionSummaryListSchema.parse(snapshot.value ?? {});
        const bootstrap = first;
        first = false;
        applyChain = applyChain
          .then(() => this.applySummaries(host, attachment, summaries, { bootstrap }))
          .catch((error) => {
            log.warn('ACP agent status bridge failed to apply summaries', {
              host: key,
              error: String(error),
            });
          });
      },
      { scope }
    );
    await whenReady(list, { scope });
    await applyChain;
    if (this.attachments.get(key) !== attachment) await scope.dispose();
  }

  detachHost(host: HostRef): void {
    const key = formatHostRef(host);
    const attachment = this.attachments.get(key);
    if (!attachment) return;
    this.attachments.delete(key);
    attachment.summaries.clear();
    void attachment.scope.dispose();
  }

  dispose(): void {
    this.disposed = true;
    this.conversationCreatedUnsubscribe?.();
    this.conversationCreatedUnsubscribe = null;
    this.workerStateUnsubscribe?.();
    this.workerStateUnsubscribe = null;
    for (const attachment of this.attachments.values()) void attachment.scope.dispose();
    this.attachments.clear();
    this.dependencies = undefined;
  }

  private async applySummaries(
    host: HostRef,
    attachment: AcpHostAttachment,
    nextSummaries: SessionSummaryList,
    options: { bootstrap?: boolean } = {}
  ): Promise<void> {
    const bootstrap = options.bootstrap ?? false;
    const seen = new Set<string>();
    for (const summary of Object.values(nextSummaries)) {
      seen.add(summary.conversationId);
      const previous = attachment.summaries.get(summary.conversationId);
      const actions = bootstrap
        ? [projectAcpStatusSnapshot(summary)].filter(
            (action): action is AcpAgentStatusAction => action !== null
          )
        : deriveAcpAgentStatusActions(previous, summary);
      await this.applyActions(actions, { cache: bootstrap });
      if (!bootstrap) {
        const titleAction = deriveAcpSessionTitleAction(previous, summary);
        if (titleAction) this.applyTitleAction(titleAction);
      }
      attachment.summaries.set(summary.conversationId, summary);
    }

    for (const [conversationId, summary] of [...attachment.summaries]) {
      if (seen.has(conversationId)) continue;
      await this.applyActions(deriveAcpAgentStatusActions(summary, undefined));
      attachment.summaries.delete(conversationId);
    }
    if (bootstrap) await this.resetMissingHostStatuses(host, seen);
  }

  private async applyActions(
    actions: AcpAgentStatusAction[],
    options: { cache?: boolean } = {}
  ): Promise<void> {
    await Promise.all(
      actions.map(async (action) => {
        try {
          if (action.kind === 'event') {
            await (options.cache
              ? agentStatusService.cacheSignal(action.event)
              : agentStatusService.applySignal(action.event));
          } else {
            await agentStatusService.resetToIdle({ conversationId: action.conversationId });
          }
        } catch (error) {
          this.logApplyError(action, error);
        }
      })
    );
  }

  private async resetMissingHostStatuses(host: HostRef, seen: ReadonlySet<string>): Promise<void> {
    const dependencies = this.dependencies;
    if (!dependencies) return;
    const activeIds = await dependencies.loadActiveConversationIds(host);
    await Promise.all(
      activeIds.flatMap((conversationId) =>
        seen.has(conversationId) ? [] : [agentStatusService.resetToIdle({ conversationId })]
      )
    );
  }

  private async resetHost(host: HostRef): Promise<void> {
    await this.resetMissingHostStatuses(host, new Set());
  }

  private applyTitleAction(action: AcpSessionTitleAction): void {
    const pending = this.dependencies?.renameConversation(action.conversationId, action.title);
    if (!pending) {
      log.warn('ACP session title bridge missing rename dependency', {
        conversationId: action.conversationId,
      });
      return;
    }
    void pending.catch((error) => {
      log.warn('ACP session title apply failed', {
        conversationId: action.conversationId,
        error: String(error),
      });
    });
  }

  private cacheConversationSnapshot(conversationId: string): void {
    for (const attachment of this.attachments.values()) {
      const summary = attachment.summaries.get(conversationId);
      if (!summary) continue;
      const action = projectAcpStatusSnapshot(summary);
      if (action) void this.applyActions([action], { cache: true });
      return;
    }
  }

  private logApplyError(action: AcpAgentStatusAction, error: unknown): void {
    const conversationId =
      action.kind === 'event' ? action.event.conversationId : action.conversationId;
    log.warn('ACP agent status bridge failed to apply conversation status', {
      conversationId,
      error: String(error),
    });
  }
}

export const acpAgentStatusBridge = new AcpAgentStatusBridge();
