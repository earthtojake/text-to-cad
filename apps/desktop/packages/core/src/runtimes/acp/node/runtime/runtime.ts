import type { Result } from '@emdash/shared';
import { ok } from '@emdash/shared';
import { createScope } from '@emdash/shared/concurrency';
import type { LiveLogSource } from '@emdash/wire/live';
import type {
  AcpAttachmentError,
  AcpCancelTurnError,
  AcpChangeQueuePromptOrderError,
  AcpDeleteQueuedPromptError,
  AcpEditQueuedPromptError,
  AcpExportRawLogError,
  AcpExportTranscriptError,
  AcpGetHistoryError,
  AcpResolvePermissionError,
  AcpResumeError,
  AcpSendPromptError,
  AcpSetModeOptionError,
  AcpSetModelOptionError,
  AcpSetPromptDraftError,
  AcpStartError,
  AcpKillError,
  AttachmentMimeType,
  AttachmentRef,
  PromptDraftUpdate,
  PromptInput,
  PromptPlacement,
  ResumeResult,
  SessionState,
  TerminalState,
  TranscriptTurn,
} from '#runtimes/acp/api';
import { acpErr } from '#runtimes/acp/api';
import { buildAgentClient } from '#runtimes/acp/node/agent-ports/agent-client';
import { FsPort } from '#runtimes/acp/node/agent-ports/fs-port';
import { AgentTerminalManager } from '#runtimes/acp/node/agent-ports/terminal-manager';
import { TerminalPort } from '#runtimes/acp/node/agent-ports/terminal-port';
import {
  createAcpConnectionSource,
  type AcpConnectionSource,
} from '#runtimes/acp/node/connection/source';
import type { SessionLiveModels, SessionsListModel } from '#runtimes/acp/node/state/live-models';
import type { StoredAttachment } from './attachment-store';
import { discoverModels } from './discover-models';
import { SessionManager, type HistoryPage } from './session-manager';
import { TerminalLiveRegistry } from './terminal-live-registry';
import type { AcpRuntimeDeps, AcpStartInput } from './types';

export class AcpRuntime {
  private readonly discoveryScope = createScope({ label: 'model-discovery' });

  discoverModels(input: { providerId: string; env?: Record<string, string> }) {
    return discoverModels(this.deps, this.discoveryScope, input);
  }

  readonly terminals: AgentTerminalManager;
  readonly connections: AcpConnectionSource;
  readonly manager: SessionManager;
  private readonly terminalLiveRegistry: TerminalLiveRegistry;

  constructor(private readonly deps: AcpRuntimeDeps) {
    let manager: SessionManager | null = null;
    this.terminalLiveRegistry = new TerminalLiveRegistry((conversationId) =>
      manager?.syncTerminals(conversationId)
    );
    this.terminals = new AgentTerminalManager(deps.host, this.terminalLiveRegistry.hooks);
    const fs = new FsPort(deps.host);
    const terminalPort = new TerminalPort(this.terminals);
    this.connections = createAcpConnectionSource({
      host: deps.host,
      agentHost: deps.agentHost,
      logger: deps.logger,
      clock: deps.clock,
      idleTtlMs: deps.lifecycle?.connectionIdleTtlMs ?? 120_000,
      buildClient: (_agent, context) => {
        if (!manager) throw new Error('AcpRuntime session manager not initialized');
        return buildAgentClient(context, manager, { fs, terminals: terminalPort });
      },
      onClosed: (key, exitCode) => manager?.onProcessClosed(key, exitCode),
    });
    manager = new SessionManager(deps, this.connections, this.terminals, {
      fs,
      terminals: terminalPort,
    });
    this.manager = manager;
  }

  startSession(input: AcpStartInput): Promise<Result<{ sessionId: string }, AcpStartError>> {
    return this.manager.start(input);
  }

  async resumeSession(
    input: AcpStartInput & { sessionId: string },
    limit = 50
  ): Promise<Result<ResumeResult, AcpResumeError>> {
    const result = await this.manager.start(input);
    if (!result.success) return result;
    const page = this.manager.getHistory(input.conversationId, undefined, limit);
    return ok({ sessionId: result.data.sessionId, ...page });
  }

  /** Runtime-internal graceful stop (persists suspended intent); not exposed on the wire. */
  stopSession(conversationId: string): Promise<Result<void, AcpKillError>> {
    return this.manager.stop(conversationId);
  }

  killSession(conversationId: string): Promise<Result<void, AcpKillError>> {
    return this.manager.kill(conversationId);
  }

  reconcile(): Promise<void> {
    return this.manager.reconcile();
  }

  sendPrompt(
    conversationId: string,
    prompt: PromptInput,
    placement?: PromptPlacement
  ): Promise<Result<{ queued: boolean }, AcpSendPromptError>> {
    return this.manager.prompt({ conversationId, prompt, placement });
  }

  editQueuedPrompt(
    conversationId: string,
    id: string,
    prompt: PromptInput
  ): Result<void, AcpEditQueuedPromptError> {
    return this.manager.editQueuedPrompt(conversationId, id, prompt);
  }

  deleteQueuedPrompt(conversationId: string, id: string): Result<void, AcpDeleteQueuedPromptError> {
    return this.manager.removeQueuedPrompt(conversationId, id);
  }

  changeQueuePromptOrder(
    conversationId: string,
    ids: readonly string[]
  ): Result<void, AcpChangeQueuePromptOrderError> {
    return this.manager.reorderQueue(conversationId, ids);
  }

  cancelTurn(conversationId: string): Promise<Result<void, AcpCancelTurnError>> {
    return this.manager.cancel(conversationId);
  }

  setPromptDraft(
    conversationId: string,
    draft: PromptDraftUpdate
  ): Result<void, AcpSetPromptDraftError> {
    return this.manager.setPromptDraft(conversationId, draft);
  }

  resolvePermission(
    conversationId: string,
    requestId: string,
    optionId: string
  ): Result<void, AcpResolvePermissionError> {
    return this.manager.resolvePermission(conversationId, requestId, optionId);
  }

  setModeOption(
    conversationId: string,
    modeId: string
  ): Promise<Result<void, AcpSetModeOptionError>> {
    return this.manager.setMode(conversationId, modeId);
  }

  setModelOption(
    conversationId: string,
    dimension: 'model' | 'effort',
    value: string
  ): Promise<Result<void, AcpSetModelOptionError>> {
    return this.manager.setConfigOption(conversationId, dimension, value);
  }

  getHistory(
    conversationId: string,
    before?: number,
    limit?: number
  ): Result<HistoryPage, AcpGetHistoryError> {
    return ok(this.manager.getHistory(conversationId, before, limit));
  }

  getChatHistory(conversationId: string): {
    committed: TranscriptTurn[];
    active: TranscriptTurn | null;
  } {
    return this.manager.getChatHistory(conversationId);
  }

  exportParsedTranscript(conversationId: string): Result<string, AcpExportTranscriptError> {
    return this.manager.exportParsedTranscript(conversationId);
  }

  exportRawAcpLog(conversationId: string): Result<string, AcpExportRawLogError> {
    return this.manager.exportRawAcpLog(conversationId);
  }

  getSessionState(conversationId: string): SessionState {
    return this.manager.getSessionState(conversationId);
  }

  getTerminals(conversationId: string): TerminalState[] {
    return this.manager.getTerminals(conversationId);
  }

  getHostTerminals(): TerminalState[] {
    return this.manager.getHostTerminals();
  }

  killAllTerminals(): void {
    this.manager.killAllTerminals();
  }

  async uploadAttachment(input: {
    conversationId: string;
    data?: Uint8Array;
    mimeType: AttachmentMimeType;
    name?: string;
    originalPath?: string;
  }): Promise<Result<AttachmentRef, AcpAttachmentError>> {
    if (!this.deps.attachmentStore) return acpErr.invalidState('No attachment store configured');
    return ok(await this.deps.attachmentStore.put(input));
  }

  async downloadAttachment(
    conversationId: string,
    attachmentId: string
  ): Promise<Result<StoredAttachment, AcpAttachmentError>> {
    if (!this.deps.attachmentStore) return acpErr.invalidState('No attachment store configured');
    const stored = await this.deps.attachmentStore.get(conversationId, attachmentId);
    if (!stored) return acpErr.invalidState(`Attachment '${attachmentId}' not found`);
    return ok(stored);
  }

  async deleteAttachment(
    conversationId: string,
    attachmentId: string
  ): Promise<Result<void, AcpAttachmentError>> {
    if (!this.deps.attachmentStore) return acpErr.invalidState('No attachment store configured');
    await this.deps.attachmentStore.delete(conversationId, attachmentId);
    return ok();
  }

  /**
   * Conversation-deletion cleanup (spec §3.6): removes the conversation's attachment
   * directory. Idempotent; a runtime without attachment storage has nothing to clean.
   */
  async deleteConversationAttachments(
    conversationId: string
  ): Promise<Result<void, AcpAttachmentError>> {
    if (!this.deps.attachmentStore) return ok();
    await this.deps.attachmentStore.deleteConversation(conversationId);
    return ok();
  }

  sessionLiveModels(conversationId: string): SessionLiveModels | null {
    return this.manager.getLiveModels(conversationId);
  }

  sessionsListLiveModel(): SessionsListModel {
    return this.manager.sessionsList;
  }

  sessionLiveHost() {
    return this.manager.sessionHost;
  }

  sessionsLiveHost() {
    return this.manager.sessionsHost;
  }

  terminalOutputLog(terminalId: string): LiveLogSource | null {
    return this.terminalLiveRegistry.getTerminalLog(terminalId);
  }

  async dispose(): Promise<void> {
    this.manager.dispose();
    this.killAllTerminals();
    await this.discoveryScope.dispose();
    await this.connections.dispose();
  }
}
