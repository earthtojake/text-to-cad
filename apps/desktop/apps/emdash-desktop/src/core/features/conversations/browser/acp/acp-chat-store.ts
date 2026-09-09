import type { ChatContext, ChatImageAttachment, ChatState, ChatView } from '@emdash/chat-ui';
import type {
  AttachmentMimeType,
  AttachmentRef,
  PromptAttachment,
  PromptDraft,
  PromptInput,
  QueuedPrompt,
  SessionMcpServer,
} from '@emdash/core/runtimes/acp/api/client';
import type {
  CommandItem,
  ComposerEffortOption,
  ComposerModelOption,
  ComposerPermissionModeOption,
  ComposerQueuedPrompt,
} from '@emdash/ui/react/components';
import { toast } from '@emdash/ui/react/primitives';
import type { BlobSource } from '@emdash/wire/rpc';
import { action, computed, makeObservable, observable, reaction, runInAction } from 'mobx';
import { getAgentsClient, hostRefFromConnectionId } from '@core/features/agents/api/browser/client';
import {
  registerConversationCommands,
  unregisterConversationCommands,
} from '@core/features/conversations/api/browser/chat/advertised-command-provider';
import { getChatUiRuntime } from '@core/features/conversations/api/browser/chat/chat-ui-runtime';
import { getSharedChatContext } from '@core/features/conversations/api/browser/chat/shared-chat-context';
import {
  hasBlankChatTitle,
  titleFromPrompt,
} from '@core/features/conversations/api/browser/prompt-title';
import { conversationRegistry } from '@core/features/conversations/api/browser/stores/conversation-registry';
import type { ProjectHostAccess } from '@core/features/projects/api/browser/stores/project-context';
import { getProjectSshConnectionId } from '@core/features/projects/api/browser/stores/project-selectors';
import { getHostClient } from '@core/primitives/desktop-host/browser/host-client';
import { log } from '@core/primitives/logging/browser/logger';
import type { AcpBootstrapPhase } from './acp-bootstrap-status';
import { AcpLiveSession, AcpStartError, asValueSource } from './acp-live-session';
import {
  describeAcpError,
  dispatchAcpPrompt,
  isSessionGoneError,
  SESSION_GONE_ERROR_TYPES,
  type AcpPromptDispatchResult,
} from './acp-prompt-dispatch';
import { bindSessionTerminalOutputs } from './acp-terminal-output-binding';
import { deriveAgentProgress, type AgentProgress } from './agent-progress';

export type BackgroundAgent = {
  agentId: string;
  name: string;
  status: 'running' | 'completed' | 'failed';
  startedAt: number;
  completedAt?: number;
  summary?: string;
  outputFile?: string;
};

export interface AgentAffordances {
  isWorking: boolean;
  isBusy: boolean;
  hasPendingPermission: boolean;
  canSubmit: boolean;
  canCancel: boolean;
}

type StoredPromptAttachment = Extract<PromptAttachment, { type: 'attachment' }>;

export type AcpPromptAttachment = {
  ref: StoredPromptAttachment;
  previewUrl?: string;
};

type PermissionQueueItem = {
  requestId: string;
  kind: 'permission' | 'question';
  title: string;
  body?: string;
  options: Array<{ optionId: string; name: string; kind: string; description?: string }>;
};

export type AcpLoadError =
  | { kind: 'auth_required'; message: string }
  | { kind: 'unavailable'; message: string }
  | { kind: 'generic'; message: string };

export class AcpChatStore {
  readonly chatContext: ChatContext;
  readonly chatState: ChatState;

  session: AcpLiveSession | null = null;
  historyLoading = true;
  bootstrapPhase: AcpBootstrapPhase = 'starting';
  loadError: AcpLoadError | null = null;
  messageCount = 0;
  draftText = '';

  private _view: ChatView | null = null;
  private _bootstrapped = false;
  private _disposed = false;
  private _bootstrapGeneration = 0;
  private _unsubs: Array<() => void> = [];
  private _draftRev = 0;
  private _pendingDraftRev: number | null = null;
  private _draftTimer: number | null = null;
  private readonly _disposeHostReaction: () => void;

  constructor(
    readonly conversationId: string,
    readonly projectId: string,
    readonly taskId: string,
    readonly hostAccess?: ProjectHostAccess
  ) {
    this.chatContext = getSharedChatContext();
    this.chatState = getChatUiRuntime().createChatState(this.chatContext, {
      uri: conversationId,
    });
    registerConversationCommands(conversationId, () =>
      this.commands.map((command) => command.name)
    );

    makeObservable(this, {
      session: observable.ref,
      historyLoading: observable,
      bootstrapPhase: observable,
      loadError: observable,
      messageCount: observable,
      draftText: observable,
      model: computed,
      modelLabel: computed,
      modelOptions: computed,
      permissionMode: computed,
      permissionModeOptions: computed,
      effort: computed,
      effortOptions: computed,
      commands: computed,
      mcpServers: computed,
      permissionQueue: computed,
      queuedPrompts: computed,
      usage: computed,
      agentProgress: computed,
      affordances: computed,
      sessionEnded: computed,
      isEmpty: computed,
      submitPrompt: action,
      stop: action,
      setModel: action,
      setMode: action,
      setEffort: action,
      resolvePermission: action,
      editQueuedPrompt: action,
      deleteQueuedPrompt: action,
      reorderQueuedPrompts: action,
      sendQueuedPromptNow: action,
      setDraftText: action,
      exportTranscript: action,
      retry: action,
    });
    this._disposeHostReaction = reaction(
      () => this.hostAccess?.state.kind,
      (kind) => {
        if (
          kind === 'ready' &&
          this._bootstrapped &&
          !this.historyLoading &&
          this.loadError?.kind === 'unavailable'
        ) {
          this.historyLoading = true;
          this.bootstrapPhase = 'starting';
          this.loadError = null;
          void this._runBootstrap();
        }
      }
    );
  }

  get model(): string | null {
    return (
      this.session?.config.current().modelOptions?.selected ??
      conversationRegistry.get(this.taskId)?.conversations.get(this.conversationId)?.data.model ??
      null
    );
  }

  get modelLabel(): string | null {
    const options = this.session?.config.current().modelOptions;
    const selected = this.model;
    if (!selected) return null;
    return options?.available.find((option) => option.id === selected)?.name ?? selected;
  }

  get modelOptions(): Record<string, ComposerModelOption> | null {
    const options = this.session?.config.current().modelOptions;
    if (!options) return null;
    return Object.fromEntries(
      options.available.map((option) => [
        option.id,
        { name: option.name, description: option.description },
      ])
    );
  }

  get permissionMode(): string | null {
    return this.session?.config.current().modeOptions?.selected ?? null;
  }

  get permissionModeOptions(): Record<string, ComposerPermissionModeOption> | null {
    const options = this.session?.config.current().modeOptions;
    if (!options) return null;
    return Object.fromEntries(
      options.available.map((option) => [
        option.id,
        { name: option.name, description: option.description },
      ])
    );
  }

  get effort(): string | null {
    return this.session?.config.current().efforts?.selected ?? null;
  }

  get effortOptions(): Record<string, ComposerEffortOption> | null {
    const options = this.session?.config.current().efforts;
    if (!options) return null;
    return Object.fromEntries(
      options.available.map((option) => [
        option.id,
        { name: option.name, description: option.description },
      ])
    );
  }

  get commands(): CommandItem[] {
    return (this.session?.config.current().availableCommands ?? []).map((command) => ({
      id: command.name,
      name: command.name,
      description: command.description,
      behavior: 'insert',
    }));
  }

  get mcpServers(): SessionMcpServer[] {
    return this.session?.mcpServers.current() ?? [];
  }

  get permissionQueue(): PermissionQueueItem[] {
    return (this.session?.sessionState.current().pendingPermissions ?? []).map((request) => ({
      requestId: request.requestId,
      kind: request.kind ?? 'permission',
      title: request.toolCall.title,
      ...(request.body !== undefined ? { body: request.body } : {}),
      options: request.options.map((option) => ({
        optionId: option.optionId,
        name: option.name,
        kind: option.kind,
        ...(option.description !== undefined ? { description: option.description } : {}),
      })),
    }));
  }

  /** A one-line account-limit warning from the provider, or null while limits are fine. */
  get rateLimitNotice(): string | null {
    const limit = this.usage?.rateLimit;
    if (!limit || limit.status === 'allowed') return null;
    const resets =
      limit.resetsAt !== undefined
        ? ` Resets ${new Date(limit.resetsAt * 1000).toLocaleTimeString([], {
            hour: 'numeric',
            minute: '2-digit',
          })}.`
        : '';
    const used =
      limit.utilization !== undefined ? ` ${Math.round(limit.utilization * 100)}% used.` : '';
    return limit.status === 'rejected'
      ? `Provider rate limit reached; requests are being refused.${resets}`
      : `Approaching the provider rate limit.${used}${resets}`;
  }

  /**
   * True once the runtime reports the agent session closed (the agent process
   * exited, or the session was evicted after a failed turn). The chat keeps its
   * history; the next prompt reconnects the session before it is sent.
   */
  get sessionEnded(): boolean {
    if (this.historyLoading || !this.session) return false;
    return this.session.sessionState.current().lifecycle === 'closed';
  }

  get queuedPrompts(): ComposerQueuedPrompt[] {
    return this._queuedPromptModels().map((prompt) => ({
      id: prompt.id,
      text: prompt.text,
    }));
  }

  get usage(): {
    contextUsed: number;
    contextSize: number;
    cost?: { amount: number; currency: string } | null;
    rateLimit?: {
      status: 'allowed' | 'allowed_warning' | 'rejected';
      resetsAt?: number;
      rateLimitType?: string;
      utilization?: number;
    };
  } | null {
    return this.session?.usage.current() ?? null;
  }

  /** Background subagents the runtime knows about, newest launch last. */
  get backgroundAgents(): BackgroundAgent[] {
    return (this.session?.agents.current() ?? [])
      .filter((agent) => agent.background)
      .map((agent) => ({
        agentId: agent.agentId,
        name: agent.name,
        status: agent.status,
        startedAt: agent.startedAt,
        ...(agent.completedAt !== undefined ? { completedAt: agent.completedAt } : {}),
        ...(agent.summary !== undefined ? { summary: agent.summary } : {}),
        ...(agent.outputFile !== undefined ? { outputFile: agent.outputFile } : {}),
      }));
  }

  get agentProgress(): AgentProgress {
    return deriveAgentProgress(
      this.session?.activeTurn.current(),
      this.affordances.hasPendingPermission
    );
  }

  get affordances(): AgentAffordances {
    const state = this.session?.sessionState.current();
    const liveActionsEnabled = this.hostAccess?.liveAction.kind !== 'disabled';
    return {
      isWorking: state?.isGenerating ?? false,
      isBusy: state?.isGenerating ?? false,
      hasPendingPermission: (state?.pendingPermissions.length ?? 0) > 0,
      canSubmit: liveActionsEnabled && (state?.canSubmit ?? false),
      canCancel: liveActionsEnabled && (state?.canCancel ?? false),
    };
  }

  get isEmpty(): boolean {
    return !this.historyLoading && this.messageCount === 0;
  }

  bootstrap(): void {
    if (this._bootstrapped || this._disposed) return;
    this._bootstrapped = true;
    void this._runBootstrap();
  }

  retry(): void {
    if (this._disposed || this.historyLoading || !this.loadError) return;
    this.historyLoading = true;
    this.bootstrapPhase = 'starting';
    this.loadError = null;
    void this._runBootstrap();
  }

  bindView(view: ChatView | null): void {
    this._view = view;
  }

  async uploadAttachment(input: {
    data?: Uint8Array;
    source?: BlobSource;
    size?: number;
    mimeType: AttachmentMimeType;
    name?: string;
    originalPath?: string;
  }): Promise<AttachmentRef | null> {
    if (this.hostAccess?.liveAction.kind === 'disabled') return null;
    try {
      const result = await this.session?.uploadAttachment(input);
      if (!result) {
        this._toastError('Failed to upload attachment', new Error('ACP session is not connected'));
        return null;
      }
      if (!result.success) {
        this._toastError('Failed to upload attachment', result.error);
        return null;
      }
      return result.data;
    } catch (error) {
      this._toastError('Failed to upload attachment', error);
      return null;
    }
  }

  async deleteAttachment(id: string): Promise<void> {
    try {
      const result = await this.session?.deleteAttachment(id);
      if (result && !result.success) this._toastError('Failed to delete attachment', result.error);
    } catch (error) {
      this._toastError('Failed to delete attachment', error);
    }
  }

  submitPrompt(
    text: string,
    attachments: AcpPromptAttachment[] = [],
    hiddenContext?: string | Promise<string | undefined>
  ): void {
    void this.dispatchPrompt(text, attachments, hiddenContext).then((result) => {
      if (!result.success) this._toastError('Failed to send message', new Error(result.error));
    });
  }

  async dispatchPrompt(
    text: string,
    attachments: AcpPromptAttachment[] = [],
    hiddenContext?: string | Promise<string | undefined>
  ): Promise<AcpPromptDispatchResult> {
    if (this.hostAccess?.liveAction.kind === 'disabled') {
      return { success: false, error: 'Actions are unavailable for this project.' };
    }

    const initialSession = this.session;
    if (!initialSession) return { success: false, error: 'The agent session is not connected.' };

    const optimisticId = !this.affordances.isWorking ? `optimistic:user:${Date.now()}` : null;
    if (optimisticId) {
      runInAction(() => {
        this.chatState.session.setPendingPrompt({
          id: optimisticId,
          text,
          attachments: attachments.map(toPendingAttachment),
        });
        this._syncMessageCount();
        const pinMode = getChatUiRuntime().pinTopMode(optimisticId);
        this._view?.setScrollMode(pinMode);
        this.chatState.scroll.set(pinMode);
      });
    }

    let resolvedHiddenContext: string | undefined;
    try {
      resolvedHiddenContext = await hiddenContext;
    } catch (error) {
      log.warn('Failed to resolve issue context for ACP prompt', {
        conversationId: this.conversationId,
        error,
      });
    }

    const session = this.session;
    if (!session || session !== initialSession) {
      runInAction(() => {
        if (optimisticId && this.chatState.session.state.pendingPrompt?.id === optimisticId) {
          this.chatState.session.setPendingPrompt(null);
          this._syncMessageCount();
        }
      });
      return { success: false, error: 'The agent session changed before the message was sent.' };
    }

    const prompt = {
      text,
      ...(resolvedHiddenContext ? { hiddenContext: resolvedHiddenContext } : {}),
      ...(attachments.length > 0
        ? { attachments: attachments.map((attachment) => attachment.ref) }
        : {}),
    };
    let result = await dispatchAcpPrompt(session, prompt);
    if (!result.success && isSessionGoneError(result.errorType, result.error)) {
      // The agent session ended underneath the chat (process exit, eviction after a
      // failed turn). Reconnect from the persisted history and send once more
      // instead of handing the person an opaque failure.
      // The first attempt may fail because the runtime still pooled the broken
      // adapter; that failure drops it, so a second attempt gets a fresh one.
      const reconnected =
        (await this._reconnect({ closeFirst: true })) || (await this._reconnect());
      if (reconnected && this.session) result = await dispatchAcpPrompt(this.session, prompt);
    }
    if (result.success) this._titleFromFirstPrompt(text);
    if (!result.success && optimisticId) {
      runInAction(() => {
        if (this.chatState.session.state.pendingPrompt?.id === optimisticId) {
          this.chatState.session.setPendingPrompt(null);
          this._syncMessageCount();
        }
      });
    }
    return result;
  }

  // A chat born as "New chat" takes its sidebar title from the first thing asked in
  // it, the way the Codex and Claude Code apps title threads. An agent that later
  // announces a session title through ACP renames it again.
  private _titleFromFirstPrompt(text: string): void {
    const manager = conversationRegistry.get(this.taskId);
    const conversation = manager?.conversations.get(this.conversationId);
    if (!manager || !conversation || !hasBlankChatTitle(conversation.data.title)) return;
    const title = titleFromPrompt(text);
    if (!title) return;
    void manager.renameConversation(this.conversationId, title).catch((error: unknown) => {
      log.warn('Failed to title chat from its first prompt', {
        conversationId: this.conversationId,
        error,
      });
    });
  }

  setDraftText(text: string): void {
    if (text === this.draftText) return;
    this.draftText = text;
    this._draftRev += 1;
    this._pendingDraftRev = this._draftRev;
    this._scheduleDraftWrite(text, this._draftRev);
  }

  stop(): void {
    void this._stopAndReconnect();
  }

  setModel(model: string): void {
    void this.session
      ?.setModelOption('model', model)
      .then((result) => {
        if (!result.success) this._toastError('Failed to change model', result.error);
      })
      .catch((error: unknown) => this._toastError('Failed to change model', error));
  }

  setMode(modeId: string): void {
    void this.session
      ?.setModeOption(modeId)
      .then((result) => {
        if (!result.success) this._toastError('Failed to change session mode', result.error);
      })
      .catch((error: unknown) => this._toastError('Failed to change session mode', error));
  }

  setEffort(effort: string): void {
    void this.session
      ?.setModelOption('effort', effort)
      .then((result) => {
        if (!result.success) this._toastError('Failed to change effort', result.error);
      })
      .catch((error: unknown) => this._toastError('Failed to change effort', error));
  }

  resolvePermission(optionId: string): void {
    const request = this.permissionQueue[0];
    if (!request) return;
    void this.session?.resolvePermission(request.requestId, optionId);
  }

  editQueuedPrompt(id: string, text: string): void {
    const existing = this._queuedPromptModels().find((prompt) => prompt.id === id);
    if (!existing) return;
    const input: PromptInput = {
      text,
      hiddenContext: existing.hiddenContext,
      attachments: existing.attachments,
    };
    void this.session
      ?.editQueuedPrompt(id, input)
      .then((result) => {
        if (!result.success) this._toastError('Failed to edit queued prompt', result.error);
      })
      .catch((error: unknown) => this._toastError('Failed to edit queued prompt', error));
  }

  deleteQueuedPrompt(id: string): void {
    void this.session
      ?.deleteQueuedPrompt(id)
      .then((result) => {
        if (!result.success) this._toastError('Failed to delete queued prompt', result.error);
      })
      .catch((error: unknown) => this._toastError('Failed to delete queued prompt', error));
  }

  reorderQueuedPrompts(ids: string[]): void {
    void this.session
      ?.changeQueuePromptOrder(ids)
      .then((result) => {
        if (!result.success) this._toastError('Failed to reorder queued prompts', result.error);
      })
      .catch((error: unknown) => this._toastError('Failed to reorder queued prompts', error));
  }

  sendQueuedPromptNow(id: string): void {
    void this._sendQueuedPromptNow(id);
  }

  exportTranscript(kind: 'parsed' | 'raw'): void {
    void this._exportTranscript(kind);
  }

  dispose(): void {
    if (this._disposed) return;
    this._disposed = true;
    this._bootstrapGeneration += 1;
    this._disposeHostReaction();
    unregisterConversationCommands(this.conversationId);
    if (this._draftTimer !== null) {
      window.clearTimeout(this._draftTimer);
      this._draftTimer = null;
    }
    this._unsubs.splice(0).forEach((unsub) => unsub());
    this.session?.dispose();
    this.session = null;
    this.chatState.dispose();
  }

  private async _runBootstrap(): Promise<void> {
    const generation = ++this._bootstrapGeneration;
    let clientSession: AcpLiveSession | null = null;
    const isCurrent = () => !this._disposed && this._bootstrapGeneration === generation;
    if (this.hostAccess?.liveAction.kind === 'disabled') {
      if (!isCurrent()) return;
      runInAction(() => {
        this.historyLoading = false;
        this.loadError = {
          kind: 'unavailable',
          message: 'Live chat is unavailable until Project access returns.',
        };
      });
      return;
    }
    const conversationData = conversationRegistry
      .get(this.taskId)
      ?.conversations.get(this.conversationId)?.data;
    const providerId = conversationData?.providerId;
    const compatibilityKey = JSON.stringify({
      providerId: providerId ?? null,
      model: conversationData?.model ?? null,
    });
    try {
      clientSession = await AcpLiveSession.create(this.conversationId, {
        compatibilityKey,
        onPhase: (phase) => {
          if (!isCurrent()) return;
          runInAction(() => {
            this.bootstrapPhase = phase;
          });
        },
      });
      if (!isCurrent()) {
        clientSession.dispose();
        return;
      }

      runInAction(() => {
        this.bootstrapPhase = 'history';
      });
      const history = await clientSession.getHistory(undefined, 100);
      if (!history.success) throw resultError(history.error);
      if (!isCurrent()) {
        clientSession.dispose();
        return;
      }
      const readySession = clientSession;

      runInAction(() => {
        this.session?.dispose();
        this.session = readySession;
        this.chatState.transcript.history.seed(history.data.turns);
        this._subscribeLiveSession(readySession);
        this._applyDraftSnapshot(readySession.draft.current());
        this.historyLoading = false;
        this.loadError = null;
        this._syncMessageCount();
      });
      clientSession = null;
    } catch (error) {
      const failedSession = clientSession;
      failedSession?.dispose();
      if (!isCurrent()) return;
      log.error('ACP chat bootstrap failed', {
        conversationId: this.conversationId,
        projectId: this.projectId,
        taskId: this.taskId,
        error,
      });
      runInAction(() => {
        if (this.session === failedSession) this.session = null;
        this.historyLoading = false;
        this.loadError =
          this.hostAccess?.liveAction.kind === 'disabled'
            ? {
                kind: 'unavailable',
                message: 'Live chat is unavailable until Project access returns.',
              }
            : toLoadError(error);
      });
      if (this.loadError?.kind === 'auth_required' && providerId) {
        void this._refreshAuthStatus(providerId);
      }
    }
  }

  private async _stopAndReconnect(): Promise<void> {
    const session = this.session;
    if (!session) return;

    try {
      const result = await session.cancelTurn();
      if (!result.success) {
        this._toastError('Failed to stop', result.error);
        return;
      }
      if (this._disposed) return;
      // The host has closed and evicted the provider session at this point;
      // reconnect the same conversation from its persisted history.
      await this._reconnect();
    } catch (error) {
      this._toastError('Failed to stop', error);
    }
  }

  /**
   * Drops the stale live replicas and bootstraps the conversation again so its
   * persisted history and a fresh provider session are available. Resolves to
   * true when a session is connected afterwards.
   */
  private async _reconnect(options: { closeFirst?: boolean } = {}): Promise<boolean> {
    const session = this.session;
    if (this._disposed) return false;
    if (options.closeFirst && session) {
      // The runtime may still hold the broken session (an adapter whose process
      // died underneath it). Cancelling closes and evicts it, so the bootstrap
      // below starts a fresh one instead of reattaching to the same husk.
      await session.cancelTurn().catch(() => undefined);
      if (this._disposed) return false;
    }
    this._unsubs.splice(0).forEach((unsub) => unsub());
    session?.dispose();
    runInAction(() => {
      if (this.session === session) this.session = null;
      this.historyLoading = true;
      this.bootstrapPhase = 'starting';
      this.loadError = null;
    });
    await this._runBootstrap();
    return !this._disposed && this.session !== null && this.loadError === null;
  }

  private async _refreshAuthStatus(providerId: string): Promise<void> {
    try {
      const host = hostRefFromConnectionId(getProjectSshConnectionId(this.projectId));
      const client = await getAgentsClient();
      const result = await client.refreshAuthStatus({ host, providerId });
      if (!result.success) {
        log.warn('Failed to refresh agent auth status after ACP auth error', {
          providerId,
          error: result.error,
        });
      }
    } catch (error) {
      log.warn('Failed to refresh agent auth status after ACP auth error', {
        providerId,
        error,
      });
    }
  }

  private _queuedPromptModels(): QueuedPrompt[] {
    return this.session?.sessionState.current().queuedPrompts ?? [];
  }

  private async _sendQueuedPromptNow(id: string): Promise<void> {
    const current = this._queuedPromptModels();
    if (!current.some((prompt) => prompt.id === id)) return;

    const shouldCancelActiveTurn = this.affordances.isWorking;
    const ids = [id, ...current.map((prompt) => prompt.id).filter((promptId) => promptId !== id)];
    const reorderResult = await this.session?.changeQueuePromptOrder(ids);
    if (!reorderResult?.success) {
      this._toastError('Failed to send queued prompt', reorderResult?.error);
      return;
    }

    if (!shouldCancelActiveTurn) return;
    const cancelResult = await this.session?.cancelTurn();
    if (!cancelResult?.success) {
      this._toastError('Failed to send queued prompt', cancelResult?.error);
    }
  }

  private async _exportTranscript(kind: 'parsed' | 'raw'): Promise<void> {
    const session = this.session;
    if (!session) {
      this._toastError('Failed to export transcript', new Error('Chat is not loaded.'));
      return;
    }

    try {
      const result =
        kind === 'raw' ? await session.exportRawAcpLog() : await session.exportTranscript();
      if (!result.success) {
        this._toastError('Failed to export transcript', result.error);
        return;
      }

      const label = kind === 'raw' ? 'raw ACP log' : 'parsed transcript';
      const suffix = kind === 'raw' ? 'acp-raw' : 'transcript';
      const saved = await (
        await getHostClient()
      ).saveTextFile({
        title: `Export ${label}`,
        defaultPath: `${this.conversationId}-${suffix}.json`,
        content: result.data,
      });
      if (!saved.success) {
        this._toastError('Failed to save transcript', new Error(saved.error));
        return;
      }
      if (!saved.path) return;
      toast(`Exported ${label}`);
    } catch (error) {
      this._toastError('Failed to export transcript', error);
    }
  }

  private _subscribeLiveSession(session: AcpLiveSession): void {
    this._unsubs.splice(0).forEach((unsub) => unsub());
    const disconnectChatSession = getChatUiRuntime().connectSession(
      this.chatState,
      {
        activeTurn: asValueSource(session.activeTurn),
        plan: asValueSource(session.plan),
        sessionState: asValueSource(session.sessionState),
      },
      {
        onTurnCommitted: () => void this._refreshHistory(),
      }
    );
    this._unsubs.push(
      disconnectChatSession,
      this._bindTerminalOutputs(session),
      session.sessionState.onChange(() =>
        runInAction(() => {
          this._syncMessageCount();
        })
      ),
      session.activeTurn.onChange(() => runInAction(() => this._syncMessageCount())),
      session.draft.onChange((draft) =>
        runInAction(() => {
          this._applyDraftSnapshot(draft);
        })
      )
    );
  }

  private _scheduleDraftWrite(text: string, rev: number): void {
    if (this._draftTimer !== null) window.clearTimeout(this._draftTimer);
    this._draftTimer = window.setTimeout(() => {
      this._draftTimer = null;
      const draft = { rev, input: text.trim().length > 0 ? { text } : null };
      void this.session
        ?.setPromptDraft(draft)
        .then((result) => {
          if (!result.success) {
            // A closed session cannot hold a draft; the next prompt reconnects it.
            const described = describeAcpError(result.error);
            if (!described.type || !SESSION_GONE_ERROR_TYPES.has(described.type)) {
              this._toastError('Failed to sync draft', result.error);
            }
          }
          if (result.success && draft.input === null && this._pendingDraftRev === rev) {
            runInAction(() => {
              this._pendingDraftRev = null;
            });
          }
        })
        .catch((error: unknown) => this._toastError('Failed to sync draft', error));
    }, 300);
  }

  private _applyDraftSnapshot(draft: PromptDraft | null | undefined): void {
    if (draft === undefined) return;
    if (draft === null) {
      if (this._pendingDraftRev === null) {
        this._draftRev += 1;
        this.draftText = '';
      }
      return;
    }

    if (this._pendingDraftRev !== null) {
      if (draft.rev >= this._pendingDraftRev) {
        this._draftRev = Math.max(this._draftRev, draft.rev);
        this._pendingDraftRev = null;
      }
      return;
    }

    if (draft.rev >= this._draftRev) {
      this._draftRev = draft.rev;
      this.draftText = draft.text;
    }
  }

  private _bindTerminalOutputs(session: AcpLiveSession): () => void {
    return bindSessionTerminalOutputs(session, (terminalId, snapshot) =>
      this.chatState.session.setTerminalOutput(terminalId, snapshot)
    );
  }

  private async _refreshHistory(): Promise<void> {
    const history = await this.session?.getHistory(undefined, 100);
    if (!history?.success) return;
    runInAction(() => {
      this.chatState.session.setPendingPrompt(null);
      this.chatState.transcript.history.seed(history.data.turns);
      this._syncMessageCount();
    });
  }

  private _syncMessageCount(): void {
    const state = this.chatState.transcript.state;
    const committedCount = state.committedTurns.reduce(
      (count, turn) => count + turn.items.length,
      0
    );
    const activeCount = state.activeTurnSnapshot?.items.length ?? 0;
    const pendingPromptCount = this.chatState.session.state.pendingPrompt ? 1 : 0;
    this.messageCount = committedCount + activeCount + pendingPromptCount;
  }

  private _toastError(title: string, error: unknown): void {
    toast.error(title, { description: describeAcpError(error).message });
  }
}

function toPendingAttachment(attachment: AcpPromptAttachment): ChatImageAttachment {
  return {
    id: attachment.ref.id,
    name: attachment.ref.name ?? 'image',
    dataUrl: attachment.previewUrl,
  };
}

function resultError(error: unknown): Error {
  if (error instanceof Error) return error;
  if (typeof error === 'object' && error !== null) {
    const message = (error as { message?: unknown }).message;
    const type = (error as { type?: unknown }).type;
    return new Error(typeof message === 'string' ? message : String(type ?? 'Unknown error'));
  }
  return new Error(String(error));
}

function toLoadError(error: unknown): AcpLoadError {
  const message = error instanceof Error ? error.message : 'Failed to load chat.';
  if (error instanceof AcpStartError && error.errorType === 'auth_required') {
    return { kind: 'auth_required', message };
  }
  return { kind: 'generic', message };
}
