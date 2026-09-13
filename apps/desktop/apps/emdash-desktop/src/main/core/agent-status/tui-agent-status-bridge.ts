import { formatHostRef, LOCAL_HOST_REF, type HostRef } from '@emdash/core/primitives/host/api';
import {
  tuiAgentsContract,
  tuiAgentStateListSchema,
  tuiSessionListSchema,
  type TuiAgentState,
  type TuiAgentStateList,
  type TuiAgentsContract,
  type TuiSessionList,
  type TuiSessionState,
} from '@emdash/core/runtimes/tui-agents/api';
import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import type { Unsubscribe } from '@emdash/shared';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { observe, remote, whenReady } from '@emdash/wire/state';
import type { WireWorker } from '@emdash/wire/worker';
import { log } from '@main/lib/logger';
import { agentStatusService } from './agent-status-service';
import {
  eventFromTuiAgentState,
  shouldApplyAgentStateTransition,
} from './tui-agent-status-transition';

type TuiAgentStatusBridgeDependencies = {
  runtimes: RuntimeBroker;
  onLocalWorkerStateChanged: WireWorker<TuiAgentsContract>['onStateChanged'];
  loadActiveConversationIds(host: HostRef): Promise<string[]>;
};

type TuiHostAttachment = {
  scope: Scope;
  agentStates: Map<string, TuiAgentState>;
  sessions: Map<string, TuiSessionState>;
};

export class TuiAgentStatusBridge {
  private readonly attachments = new Map<string, TuiHostAttachment>();
  private workerStateUnsubscribe: Unsubscribe | null = null;
  private dependencies: TuiAgentStatusBridgeDependencies | undefined;
  private disposed = false;

  initialize(dependencies: TuiAgentStatusBridgeDependencies): void {
    this.disposed = false;
    this.dependencies = dependencies;
    this.workerStateUnsubscribe ??= dependencies.onLocalWorkerStateChanged((state) => {
      if (state.kind === 'failed' || state.kind === 'disposed') {
        this.detachHost(LOCAL_HOST_REF);
        void this.resetHost(LOCAL_HOST_REF).catch((error) => {
          log.warn('TUI agent status bridge failed to reset local statuses after worker exit', {
            error: String(error),
          });
        });
      } else if (state.kind === 'ready') {
        void this.attachHost(LOCAL_HOST_REF).catch((error) => {
          log.warn('TUI agent status bridge failed to reattach after worker recovery', {
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
    if (!dependencies) throw new Error('TUI agent status bridge has not been initialized');
    const client = await dependencies.runtimes.client(host);
    if (!client.success || this.disposed) return;
    const key = formatHostRef(host);
    if (this.attachments.has(key)) return;

    const scope = createScope({ label: `tui-agent-status-bridge:${key}` });
    const attachment: TuiHostAttachment = {
      scope,
      agentStates: new Map(),
      sessions: new Map(),
    };
    this.attachments.set(key, attachment);
    const remoteAgentStates = remote(
      tuiAgentsContract.agentStates,
      client.data.tuiAgents.agentStates,
      { scope, lingerMs: 15_000 }
    );
    const remoteSessions = remote(tuiAgentsContract.sessions, client.data.tuiAgents.sessions, {
      scope,
      lingerMs: 15_000,
    });
    const agentStatesList = remoteAgentStates(undefined).states.list;
    const sessionsList = remoteSessions(undefined).states.list;
    let firstAgentStates = true;
    let firstSessions = true;
    let agentStatesChain = Promise.resolve();
    let sessionsChain = Promise.resolve();
    observe(
      agentStatesList,
      (snapshot) => {
        if (snapshot.status === 'loading') return;
        const states = tuiAgentStateListSchema.parse(snapshot.value ?? {});
        const bootstrap = firstAgentStates;
        firstAgentStates = false;
        agentStatesChain = agentStatesChain
          .then(() => this.applyAgentStates(host, attachment, states, { bootstrap }))
          .catch((error) => {
            log.warn('TUI agent status bridge failed to apply agent states', {
              host: key,
              error: String(error),
            });
          });
      },
      { scope }
    );
    observe(
      sessionsList,
      (snapshot) => {
        if (snapshot.status === 'loading') return;
        const sessions = tuiSessionListSchema.parse(snapshot.value ?? {});
        const bootstrap = firstSessions;
        firstSessions = false;
        sessionsChain = sessionsChain
          .then(() => this.applySessions(attachment, sessions, { bootstrap }))
          .catch((error) => {
            log.warn('TUI agent status bridge failed to apply sessions', {
              host: key,
              error: String(error),
            });
          });
      },
      { scope }
    );

    await Promise.all([whenReady(agentStatesList, { scope }), whenReady(sessionsList, { scope })]);
    await Promise.all([agentStatesChain, sessionsChain]);
    if (this.attachments.get(key) !== attachment) await scope.dispose();
  }

  detachHost(host: HostRef): void {
    const key = formatHostRef(host);
    const attachment = this.attachments.get(key);
    if (!attachment) return;
    this.attachments.delete(key);
    attachment.agentStates.clear();
    attachment.sessions.clear();
    void attachment.scope.dispose();
  }

  dispose(): void {
    this.disposed = true;
    this.workerStateUnsubscribe?.();
    this.workerStateUnsubscribe = null;
    for (const attachment of this.attachments.values()) void attachment.scope.dispose();
    this.attachments.clear();
    this.dependencies = undefined;
  }

  private async applyAgentStates(
    host: HostRef,
    attachment: TuiHostAttachment,
    nextStates: TuiAgentStateList,
    options: { bootstrap?: boolean } = {}
  ): Promise<void> {
    const bootstrap = options.bootstrap ?? false;
    const seen = new Set<string>();

    for (const state of Object.values(nextStates)) {
      seen.add(state.conversationId);
      const previous = attachment.agentStates.get(state.conversationId);
      if (bootstrap) {
        await this.applyAgentStateSnapshot(state);
      } else if (shouldApplyAgentStateTransition(previous, state)) {
        await this.applyAgentStateTransition(state);
      }
      attachment.agentStates.set(state.conversationId, state);
    }

    for (const [conversationId, previous] of [...attachment.agentStates]) {
      if (seen.has(conversationId)) continue;
      await this.resetConversation(previous.conversationId);
      attachment.agentStates.delete(conversationId);
    }
    if (bootstrap) await this.resetMissingHostStatuses(host, seen);
  }

  private async applySessions(
    attachment: TuiHostAttachment,
    nextSessions: TuiSessionList,
    options: { bootstrap?: boolean } = {}
  ): Promise<void> {
    const bootstrap = options.bootstrap ?? false;
    const seen = new Set<string>();

    // Session ids are not persisted here: the TUI runtime reports resume handles into
    // the conversation index (spec §3.3) and convergence caches them client-side.
    for (const session of Object.values(nextSessions)) {
      seen.add(session.conversationId);
      const previous = attachment.sessions.get(session.conversationId);
      if (!bootstrap && previous?.status !== 'exited' && session.status === 'exited') {
        await this.resetConversation(session.conversationId);
      }
      attachment.sessions.set(session.conversationId, session);
    }

    for (const [conversationId, previous] of [...attachment.sessions]) {
      if (seen.has(conversationId)) continue;
      if (!bootstrap) await this.resetConversation(previous.conversationId);
      attachment.sessions.delete(conversationId);
    }
  }

  private async applyAgentStateSnapshot(state: TuiAgentState): Promise<void> {
    if (state.status === 'idle') {
      await this.resetConversation(state.conversationId);
      return;
    }
    const event = eventFromTuiAgentState(state);
    if (event) await agentStatusService.cacheSignal(event);
  }

  private async applyAgentStateTransition(state: TuiAgentState): Promise<void> {
    if (state.status === 'idle') {
      await this.resetConversation(state.conversationId);
      return;
    }
    const event = eventFromTuiAgentState(state);
    if (event) await agentStatusService.applySignal(event);
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

  private async resetConversation(conversationId: string): Promise<void> {
    await agentStatusService.resetToIdle({ conversationId });
  }
}

export const tuiAgentStatusBridge = new TuiAgentStatusBridge();
