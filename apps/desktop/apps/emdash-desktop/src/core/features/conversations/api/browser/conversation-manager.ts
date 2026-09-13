import type { SerializedHostRef } from '@emdash/core/primitives/host/api';
import type { SessionSummary } from '@emdash/core/runtimes/acp/api/client';
import type { TuiSessionList } from '@emdash/core/runtimes/tui-agents/api';
import { createScope, type Disposable } from '@emdash/shared/concurrency';
import { ReplicaLog } from '@emdash/wire/live';
import { observe, remote } from '@emdash/wire/state';
import type { Terminal } from '@xterm/xterm';
import { action, computed, makeObservable, observable, reaction, runInAction } from 'mobx';
import { conversationsContract } from '@core/features/conversations/api';
// TODO(conversations-extraction): Inject file-link handlers instead of importing task editor plumbing.
import { makeFileLinkHandlers } from '@core/features/editor/api/browser/open-file-in-file-editor';
import {
  classifyLiveRuntimeObservation,
  type LiveRuntimeObservation,
} from '@core/features/projects/api/browser/live-runtime-observation';
import type { ProjectHostAccess } from '@core/features/projects/api/browser/stores/project-context';
import type { FrontendPtyConnector } from '@core/features/terminals/api/browser/pty/pty';
import { PtySession } from '@core/features/terminals/api/browser/pty/pty-session';
import { createXtermLogSink } from '@core/features/terminals/api/browser/pty/xterm-log-sink';
import { type AgentStatus, type NotificationType } from '@core/primitives/agents/api';
import { Resource } from '@core/primitives/async-resource/browser/resource';
import {
  type Conversation,
  type ConversationEvent,
  type CreateConversationParams,
} from '@core/primitives/conversations/api';
import { makePtySessionId } from '@core/primitives/pty/api';
import { getConversationsClient } from './client';

/**
 * Supplies measured terminal dimensions for a conversation's PTY spawn.
 * Injected by the workbench composition (which owns the pane layout); may wait
 * briefly for the pane's first measurement. Resolves null when no measurement
 * is available in time, in which case the spawn falls back to the backend
 * default size.
 */
export type ConversationInitialSizeResolver = (
  conversationId?: string
) => Promise<{ cols: number; rows: number } | null>;

export class ConversationManagerStore implements Disposable {
  private _initialSizeResolver: ConversationInitialSizeResolver | null = null;
  private offAgentStatusChanged: (() => void) | null = null;
  private offTuiSessionState: (() => void) | null = null;
  private offAcpSessionState: (() => void) | null = null;
  private offConversationCreated: (() => void) | null = null;
  private offConversationChanges: (() => void) | null = null;
  private readonly _disposeReaction: () => void;
  private readonly _disposeHostReaction: () => void;
  private _hasObservedTuiSessions = false;
  private _hasObservedAcpSessions = false;

  /** Data layer: plain Conversation records loaded from the main process. */
  readonly list: Resource<Conversation[]>;
  /** Runtime state stores keyed by conversation id — populated by reaction on list.data. */
  conversations = observable.map<string, ConversationStore>();
  /** Session layer keyed by conversation id — created alongside data, connected lazily. */
  sessions = observable.map<string, PtySession>();
  activeTuiSessionIds = observable.set<string>();
  activeAcpSessionIds = observable.set<string>();

  constructor(
    private readonly projectId: string,
    private readonly taskId: string,
    preloaded: Conversation[] | undefined,
    private readonly sessionHost: () => SerializedHostRef,
    readonly hostAccess?: ProjectHostAccess
  ) {
    makeObservable<ConversationManagerStore, '_hasObservedAcpSessions' | '_hasObservedTuiSessions'>(
      this,
      {
        conversations: observable,
        sessions: observable,
        activeTuiSessionIds: observable,
        activeAcpSessionIds: observable,
        _hasObservedTuiSessions: observable,
        _hasObservedAcpSessions: observable,
        activeSessionIds: computed,
        taskStatus: computed,
        runtimeObservation: computed,
      }
    );

    const hasPreloaded = preloaded !== undefined;
    this.list = new Resource<Conversation[]>(
      hasPreloaded
        ? null
        : async () =>
            (await getConversationsClient()).getConversationsForTask({
              projectId,
              taskId,
            }),
      hasPreloaded ? [] : [{ kind: 'demand' }],
      hasPreloaded ? { init: preloaded } : undefined
    );

    // When preloaded data is available, populate the maps synchronously so
    // they are accessible immediately — even when this constructor is called
    // from within a MobX action, where reaction callbacks (including
    // fireImmediately) are deferred until the outermost action completes.
    if (preloaded) {
      runInAction(() => {
        for (const conversation of preloaded) {
          if (!this.conversations.has(conversation.id)) {
            this.conversations.set(conversation.id, new ConversationStore(conversation));
          }
          if (!this.sessions.has(conversation.id)) {
            this.sessions.set(conversation.id, this.createSession(conversation));
          }
        }
      });
    }

    // Sync conversations and sessions maps whenever resource data changes.
    // fireImmediately handles the non-preloaded case; for preloaded data the
    // maps are already populated above so this is a no-op on first run.
    this._disposeReaction = reaction(
      () => this.list.data,
      (data) => {
        if (!data) return;
        runInAction(() => {
          for (const conversation of data) {
            if (!this.conversations.has(conversation.id)) {
              this.conversations.set(conversation.id, new ConversationStore(conversation));
            }
            if (!this.sessions.has(conversation.id)) {
              this.sessions.set(conversation.id, this.createSession(conversation));
            }
          }
        });
      },
      { fireImmediately: true }
    );
    this._disposeHostReaction = reaction(
      () => this.hostAccess?.state,
      (state) => {
        if (state?.kind !== 'ready') return;
        for (const session of this.sessions.values()) session.resumeIfRequested();
      }
    );

    this.offAgentStatusChanged = this.listenToAgentStatusChanged();
    this.offTuiSessionState = this.listenToTuiSessionState();
    this.offAcpSessionState = this.listenToAcpSessionState();
    this.offConversationCreated = this.listenToConversationCreated();
    this.offConversationChanges = this.listenToConversationChanges();
    if (!hasPreloaded) void this.list.load();
  }

  private addConversation(conversation: Conversation): void {
    if (!this.conversations.has(conversation.id)) {
      this.conversations.set(conversation.id, new ConversationStore(conversation));
    }
    if (!this.sessions.has(conversation.id)) {
      this.sessions.set(conversation.id, this.createSession(conversation));
    }
  }

  private subscribeConversationEvents(onEvent: (event: ConversationEvent) => void): () => void {
    if (typeof window === 'undefined') return () => {};
    let disposed = false;
    let unsubscribe: (() => void) | undefined;
    void getConversationsClient().then(async (client) => {
      const nextUnsubscribe = await client.events.subscribe(undefined, {
        onEvent,
        onGap: () => void this.list.load(),
      });
      if (disposed) nextUnsubscribe();
      else unsubscribe = nextUnsubscribe;
    });
    return () => {
      disposed = true;
      unsubscribe?.();
    };
  }

  private listenToAgentStatusChanged(): () => void {
    return this.subscribeConversationEvents((payload) => {
      if (payload.type !== 'agent-status-changed') return;
      if (payload.taskId !== this.taskId) return;
      const conversationStore = this.conversations.get(payload.conversationId);
      if (!conversationStore) return;

      runInAction(() => {
        conversationStore.status = payload.status;
        conversationStore.seen = payload.seen;
        if (payload.status !== 'awaiting-input') {
          conversationStore.lastNotificationType = null;
        }
      });
    });
  }

  private listenToTuiSessionState(): () => void {
    if (typeof window === 'undefined') return () => {};
    let currentScope: ReturnType<typeof createScope> | undefined;
    const disposeReaction = reaction(
      () => ({ host: this.sessionHost(), accessKind: this.hostAccess?.state.kind }),
      ({ host, accessKind }) => {
        void currentScope?.dispose();
        currentScope = undefined;
        if (accessKind !== undefined && accessKind !== 'ready') return;
        currentScope = createScope({ label: `conversation-manager:tui-sessions:${host}` });
        const scope = currentScope;
        void (async () => {
          const client = await getConversationsClient();
          if (scope.disposed) return;
          const sessions = remote(conversationsContract.tui.sessions, client.tui.sessions, {
            scope,
            lingerMs: 15_000,
          });
          const member = sessions({ host, projectId: this.projectId });
          observe(
            member.states.list,
            (snapshot) => this.handleTuiSessionListChanged(snapshot.value ?? {}),
            { scope }
          );
        })();
      },
      { fireImmediately: true }
    );
    return () => {
      disposeReaction();
      void currentScope?.dispose();
    };
  }

  private handleTuiSessionListChanged(list: TuiSessionList): void {
    runInAction(() => {
      this._hasObservedTuiSessions = true;
      this.activeTuiSessionIds.clear();
      for (const [conversationId, session] of Object.entries(list)) {
        if (session.status === 'starting' || session.status === 'running') {
          this.activeTuiSessionIds.add(conversationId);
        }
      }
    });
  }

  private listenToAcpSessionState(): () => void {
    if (typeof window === 'undefined') return () => {};
    let currentScope: ReturnType<typeof createScope> | undefined;
    const disposeReaction = reaction(
      () => ({ host: this.sessionHost(), accessKind: this.hostAccess?.state.kind }),
      ({ host, accessKind }) => {
        void currentScope?.dispose();
        currentScope = undefined;
        if (accessKind !== undefined && accessKind !== 'ready') return;
        currentScope = createScope({ label: `conversation-manager:acp-sessions:${host}` });
        const scope = currentScope;
        void (async () => {
          const client = await getConversationsClient();
          if (scope.disposed) return;
          const sessions = remote(conversationsContract.acp.sessions, client.acp.sessions, {
            scope,
            lingerMs: 15_000,
          });
          const member = sessions({ host, projectId: this.projectId });
          observe(
            member.states.list,
            (snapshot) => this.handleAcpSessionListChanged(snapshot.value ?? {}),
            { scope }
          );
        })();
      },
      { fireImmediately: true }
    );
    return () => {
      disposeReaction();
      void currentScope?.dispose();
    };
  }

  private handleAcpSessionListChanged(list: Record<string, SessionSummary>): void {
    runInAction(() => {
      this._hasObservedAcpSessions = true;
      this.activeAcpSessionIds.clear();
      for (const [conversationId, session] of Object.entries(list)) {
        if (session.lifecycle !== 'closed') {
          this.activeAcpSessionIds.add(conversationId);
        }
      }
    });
  }

  private listenToConversationCreated(): () => void {
    return this.subscribeConversationEvents((event) => {
      if (event.type !== 'created') return;
      const { conversation } = event;
      if (conversation.taskId !== this.taskId || conversation.projectId !== this.projectId) return;
      runInAction(() => {
        this.addConversation(conversation);
      });
    });
  }

  private listenToConversationChanges(): () => void {
    return this.subscribeConversationEvents((event) => {
      if (event.type !== 'changed') return;
      if (event.taskId !== this.taskId) return;
      const store = this.conversations.get(event.conversationId);
      if (!store) return;
      runInAction(() => {
        Object.assign(store.data, event.changes);
      });
    });
  }

  get taskStatus(): AgentStatus | null {
    let hasWorking = false;
    let hasUnseenError = false;
    let hasUnseenCompleted = false;
    for (const conversation of this.conversations.values()) {
      if (!conversation.seen && conversation.status === 'awaiting-input') return 'awaiting-input';
      if (conversation.status === 'working') hasWorking = true;
      if (!conversation.seen && conversation.status === 'error') hasUnseenError = true;
      if (!conversation.seen && conversation.status === 'completed') hasUnseenCompleted = true;
    }
    if (hasWorking) return 'working';
    if (hasUnseenError) return 'error';
    if (hasUnseenCompleted) return 'completed';
    return null;
  }

  get activeSessionIds(): Set<string> {
    return new Set([...this.activeTuiSessionIds, ...this.activeAcpSessionIds]);
  }

  get runtimeObservation(): LiveRuntimeObservation<{
    activeTuiSessionIds: string[];
    activeAcpSessionIds: string[];
  }> {
    const observed =
      this._hasObservedTuiSessions || this._hasObservedAcpSessions
        ? {
            activeTuiSessionIds: [...this.activeTuiSessionIds],
            activeAcpSessionIds: [...this.activeAcpSessionIds],
          }
        : undefined;
    return classifyLiveRuntimeObservation(
      this.hostAccess?.state ?? { kind: 'ready', hostGeneration: 0 },
      observed
    );
  }

  isSessionActive(conversationId: string): boolean {
    return (
      this.activeTuiSessionIds.has(conversationId) || this.activeAcpSessionIds.has(conversationId)
    );
  }

  /**
   * Injected by the owning composition so PTY spawns can start at the pane's
   * measured size instead of the backend default. Pass null to detach.
   */
  setInitialSizeResolver(resolver: ConversationInitialSizeResolver | null): void {
    this._initialSizeResolver = resolver;
  }

  private async resolveInitialSize(
    conversationId?: string
  ): Promise<{ cols: number; rows: number } | undefined> {
    const resolver = this._initialSizeResolver;
    if (!resolver) return undefined;
    try {
      return (await resolver(conversationId)) ?? undefined;
    } catch {
      return undefined;
    }
  }

  async createConversation(params: CreateConversationParams): Promise<Conversation> {
    if (this.hostAccess?.liveAction.kind === 'disabled') {
      throw new Error('Live actions are unavailable for this Project.');
    }
    // ACP conversations start lazily and have no PTY, so skip the size wait.
    const initialSize =
      params.type === 'acp'
        ? params.initialSize
        : (params.initialSize ?? (await this.resolveInitialSize()));
    const result = await (
      await getConversationsClient()
    ).createConversation({ ...params, initialSize });
    if (!result.success) throw new Error(result.error.type);
    const conversation = result.data;
    runInAction(() => {
      this.addConversation(conversation);
    });
    return conversation;
  }

  async hydrateConversation(conversationId: string): Promise<void> {
    if (this.hostAccess?.liveAction.kind === 'disabled') {
      throw new Error('Live actions are unavailable for this Project.');
    }
    // Hydrate is a no-op spawn-wise for ACP conversations; only PTY-backed
    // conversations benefit from waiting on a pane measurement.
    const isPty = this.conversations.get(conversationId)?.data.type !== 'acp';
    const initialSize = isPty ? await this.resolveInitialSize(conversationId) : undefined;
    const result = await (
      await getConversationsClient()
    ).hydrateConversation({
      projectId: this.projectId,
      taskId: this.taskId,
      conversationId,
      initialSize,
    });
    if (!result.success) throw new Error(result.error.type);
  }

  async dehydrateConversation(conversationId: string): Promise<void> {
    const session = this.sessions.get(conversationId);
    session?.dispose();
    if (this.hostAccess?.liveAction.kind === 'disabled') return;
    const result = await (
      await getConversationsClient()
    ).dehydrateConversation({
      projectId: this.projectId,
      taskId: this.taskId,
      conversationId,
    });
    if (!result.success) throw new Error(conversationErrorMessage(result.error));
  }

  async deleteConversation(conversationId: string): Promise<void> {
    const store = this.conversations.get(conversationId);
    const session = this.sessions.get(conversationId);
    if (!store) return;

    runInAction(() => {
      this.conversations.delete(conversationId);
      this.sessions.delete(conversationId);
    });

    try {
      await (
        await getConversationsClient()
      ).deleteConversation({
        projectId: this.projectId,
        taskId: this.taskId,
        conversationId,
      });
      session?.destroy();
    } catch (err) {
      runInAction(() => {
        this.conversations.set(conversationId, store);
        if (session) this.sessions.set(conversationId, session);
      });
      throw err;
    }
  }

  async killSession(conversationId: string): Promise<void> {
    const conversation = this.conversations.get(conversationId);
    if (!conversation) return;
    if (this.hostAccess?.liveAction.kind === 'disabled') {
      throw new Error('Live actions are unavailable for this Project.');
    }
    const client = await getConversationsClient();
    const result =
      conversation.data.type === 'acp'
        ? await client.acp.kill({ conversationId })
        : await client.tui.kill({ conversationId });
    if (!result.success) {
      throw new Error(
        conversationErrorMessage(result.error, `Failed to kill session '${conversationId}'`)
      );
    }
    runInAction(() => {
      this.activeAcpSessionIds.delete(conversationId);
      this.activeTuiSessionIds.delete(conversationId);
    });
  }

  async renameConversation(conversationId: string, name: string): Promise<void> {
    const store = this.conversations.get(conversationId);
    if (!store) return;

    const previousTitle = store.data.title;

    runInAction(() => {
      store.data.title = name;
    });

    try {
      await (
        await getConversationsClient()
      ).renameConversation({
        conversationId,
        name,
      });
    } catch (err) {
      runInAction(() => {
        store.data.title = previousTitle;
      });
      throw err;
    }
  }

  dispose(): void {
    this._disposeReaction();
    this._disposeHostReaction();
    this.offAgentStatusChanged?.();
    this.offAgentStatusChanged = null;
    this.offTuiSessionState?.();
    this.offTuiSessionState = null;
    this.offAcpSessionState?.();
    this.offAcpSessionState = null;
    this.offConversationCreated?.();
    this.offConversationCreated = null;
    this.offConversationChanges?.();
    this.offConversationChanges = null;
    for (const session of this.sessions.values()) {
      session.destroy();
    }
  }

  private createSession(conversation: Conversation): PtySession {
    const handlers = makeFileLinkHandlers(conversation.projectId, conversation.taskId, {
      target: 'right',
    });
    const connector =
      conversation.type === 'acp'
        ? createNoopConnector()
        : createTuiAgentsConnector(conversation.id);
    return new PtySession(
      makePtySessionId(conversation.projectId, conversation.taskId, conversation.id),
      undefined,
      handlers.onOpenFile,
      handlers.onOpenExternal,
      connector,
      () => this.hostAccess?.liveAction.kind !== 'disabled'
    );
  }
}

function conversationErrorMessage(
  error: { type: string; message?: string },
  fallback = `Conversation operation failed: ${error.type}`
): string {
  return error.message ?? fallback;
}

function createNoopConnector(): FrontendPtyConnector {
  return {
    connect() {
      return () => {};
    },
  };
}

function createTuiAgentsConnector(conversationId: string): FrontendPtyConnector {
  let logBinding: ReplicaLog | null = null;
  let clientPromise: ReturnType<typeof getConversationsClient> | null = null;
  const client = () => {
    clientPromise ??= getConversationsClient();
    return clientPromise;
  };
  return {
    async connect(terminal: Terminal) {
      const runtime = await client();
      logBinding = new ReplicaLog(runtime.tui.output.handle({ conversationId }), {
        store: createXtermLogSink(terminal),
      });
      await logBinding.ready;
      return () => {
        void logBinding?.dispose();
        logBinding = null;
      };
    },
    sendInput(data: string) {
      void client().then((runtime) => runtime.tui.sendInput({ conversationId, data }));
    },
    resize(cols: number, rows: number) {
      void client().then((runtime) => runtime.tui.resize({ conversationId, cols, rows }));
    },
  };
}

export class ConversationStore {
  data: Conversation;
  status: AgentStatus;
  seen: boolean;
  lastNotificationType: NotificationType | null = null;

  constructor(conversation: Conversation) {
    this.data = conversation;
    this.status = conversation.agentStatus ?? 'idle';
    this.seen = conversation.agentStatusSeen ?? true;
    makeObservable(this, {
      data: observable,
      status: observable,
      seen: observable,
      lastNotificationType: observable,
      setStatus: action,
      setAwaitingInput: action,
      setWorking: action,
      clearWorking: action,
      markSeen: action,
      isInitialConversation: computed,
      indicatorStatus: computed,
    });
  }

  get isInitialConversation(): boolean {
    return this.data.isInitialConversation === true;
  }

  get indicatorStatus(): AgentStatus | null {
    if (this.status === 'working') return 'working';
    if (this.seen) return null;
    if (this.status === 'awaiting-input') return 'awaiting-input';
    if (this.status === 'error') return 'error';
    if (this.status === 'completed') return 'completed';
    return null;
  }

  setStatus(status: AgentStatus) {
    this.status = status;
    this.seen = status === 'idle' || status === 'working';
    if (status !== 'awaiting-input') {
      this.lastNotificationType = null;
    }
  }

  setAwaitingInput(notificationType: NotificationType) {
    this.lastNotificationType = notificationType;
    this.setStatus('awaiting-input');
  }

  setWorking() {
    if (this.status === 'awaiting-input' && this.lastNotificationType === 'permission_prompt') {
      return;
    }
    this.lastNotificationType = null;
    this.setStatus('working');
  }

  clearWorking() {
    if (this.status === 'working' || this.status === 'awaiting-input') {
      this.setStatus('idle');
    }
  }

  markSeen() {
    this.seen = true;
    void getConversationsClient().then((client) =>
      client.markConversationSeen({ conversationId: this.data.id })
    );
  }

  dispose() {
    // Session is managed by ConversationManagerStore.sessions — nothing to do here.
  }
}
