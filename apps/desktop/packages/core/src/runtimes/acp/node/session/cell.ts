import type {
  CreateElicitationRequest,
  CreateElicitationResponse,
  RequestPermissionRequest,
  RequestPermissionResponse,
  SessionConfigOption,
  SessionModeState,
  SetSessionConfigOptionRequest,
  SetSessionModeRequest,
} from '@agentclientprotocol/sdk';
import type { Result } from '@emdash/shared';
import { ok, toSerializedError } from '@emdash/shared';
import type {
  AcpCancelTurnError,
  AcpPermissionRequest,
  AcpRuntimeError,
  AcpSendPromptError,
  AcpSetModeOptionError,
  AcpSetModelOptionError,
  InvalidStateError,
  NormalizedEvent,
  PromptDraft,
  PromptDraftUpdate,
  PromptInput,
  QueuedPrompt,
  SessionConfigState,
  SessionState,
  SessionUsage,
  StopReason,
  ToolCallItem,
  ToolNode,
  TranscriptTurn,
  TranscriptTurnOutcome,
} from '#runtimes/acp/api';
import {
  AcpTranscriptParser,
  acpErr,
  createToolCallItem,
  encodePromptHiddenContext,
  makeToolId,
  SESSION_PLAN_ID,
  stripPromptHiddenContext,
} from '#runtimes/acp/api';
import {
  type Command,
  type DomainEvent,
  type Effect,
  SessionMachine,
  type SessionMachineContext,
} from '#runtimes/acp/node/machine/machine';
import { createMachineEffectDriver, type MachineEffectDriver } from '../machine/primitive';
import type { SessionCellDeps, SessionPromptResult } from './cell-deps';
import { PermissionBroker } from './permission-broker';
import { RawAcpLog, type RawAcpEvent } from './raw-log';

export interface AcpChatHistory {
  committed: TranscriptTurn[];
  active: TranscriptTurn | null;
}

type ConfigDimension = 'model' | 'effort';

export class SessionCell {
  readonly machine: SessionMachine;
  readonly transcript: AcpTranscriptParser;
  readonly rawLog: RawAcpLog;
  private readonly permissions = new PermissionBroker();
  private _acpSessionId: string;
  private quiesceTimer: ReturnType<typeof setTimeout> | null = null;
  private lastRunningAgentCount = 0;
  private readonly effectDriver: MachineEffectDriver<Effect>;
  private draft: PromptDraft | null = null;
  private draftRev = 0;
  private replayUserChunks: Array<Extract<NormalizedEvent, { kind: 'message' }>> = [];

  constructor(private readonly deps: SessionCellDeps) {
    this._acpSessionId = deps.acpSessionId;
    this.machine = new SessionMachine(deps.conversationId);
    this.transcript = new AcpTranscriptParser({ conversationId: deps.conversationId });
    this.rawLog = new RawAcpLog({
      conversationId: deps.conversationId,
      providerId: deps.providerId,
      acpSessionId: deps.acpSessionId,
      createdAt: new Date().toISOString(),
    });
    this.effectDriver = createMachineEffectDriver({
      interpret: (effect) => this.interpretEffect(effect),
      onDrain: ({ effects }) => {
        if (effects.some(isSessionStateEffect)) {
          this.deps.callbacks?.onSessionStateChanged?.();
        }
      },
      onInterpreterError: ({ error, effect }) => {
        this.deps.logger.warn('SessionCell: effect handler failed', {
          conversationId: this.conversationId,
          effect,
          error,
        });
      },
    });
  }

  get conversationId(): string {
    return this.deps.conversationId;
  }

  get acpSessionId(): string {
    return this._acpSessionId;
  }

  setAcpSessionId(sessionId: string): void {
    this._acpSessionId = sessionId;
    this.rawLog.setAcpSessionId(sessionId);
  }

  get sessionState(): SessionState {
    return this.machine.sessionState();
  }

  get promptDraft(): PromptDraft | null {
    return this.draft ? structuredClone(this.draft) : null;
  }

  get config(): SessionConfigState {
    return this.transcript.config;
  }

  get usage(): SessionUsage | null {
    return this.transcript.usage;
  }

  history(): AcpChatHistory {
    return {
      committed: structuredClone([...this.transcript.history]),
      active: this.transcript.activeTurn ? structuredClone(this.transcript.activeTurn) : null,
    };
  }

  exportParsedTranscript(): string {
    const history = this.history();
    return JSON.stringify(
      {
        meta: {
          conversationId: this.conversationId,
          providerId: this.deps.providerId,
          acpSessionId: this.acpSessionId,
          exportedAt: new Date().toISOString(),
        },
        committed: history.committed,
        active: history.active,
      },
      null,
      2
    );
  }

  recordRaw(event: RawAcpEvent): void {
    this.rawLog.record(event);
  }

  exportRawLog(): string {
    return this.rawLog.exportJson();
  }

  beginReplay(at = Date.now()): void {
    this.replayUserChunks = [];
    this.applyEvent({ type: 'ReplayStarted' });
    this.transcript.beginReplay(at);
    this.lastRunningAgentCount = 0;
  }

  endReplay(at = Date.now()): void {
    this.flushReplayUserChunks();
    const previousRunningAgentCount = this.lastRunningAgentCount;
    this.transcript.endReplay(at);
    this.dispatchAgentsChangedIfNeeded(previousRunningAgentCount);
    this.applyEvent({ type: 'ReplayEnded', status: 'complete' });
    this.emitTranscriptChanged();
  }

  applySessionReady(meta?: {
    modes?: SessionModeState | null;
    configOptions?: readonly SessionConfigOption[] | null;
  }): void {
    this.applyEvent({ type: 'SessionReady' });
    this.seedTranscriptMeta(meta);
  }

  applySessionLoaded(meta?: {
    modes?: SessionModeState | null;
    configOptions?: readonly SessionConfigOption[] | null;
  }): void {
    this.applyEvent({ type: 'SessionLoaded' });
    this.seedTranscriptMeta(meta);
  }

  applySessionMeta(meta: {
    modes?: SessionModeState | null;
    configOptions?: readonly SessionConfigOption[] | null;
  }): void {
    this.seedTranscriptMeta(meta);
  }

  push(event: NormalizedEvent): void {
    if (event.kind === 'ignored') return;

    if (this.machine.phase.kind === 'replaying') {
      if (event.kind === 'message' && event.role === 'user') {
        const activeMessageId = this.replayUserChunks[0]?.messageId;
        if (this.replayUserChunks.length > 0 && activeMessageId !== event.messageId) {
          this.flushReplayUserChunks();
        }
        this.replayUserChunks.push(event);
        return;
      }
      if (this.isTranscriptEvent(event)) this.flushReplayUserChunks();
    }

    const transcriptEvent: NormalizedEvent =
      event.kind === 'message' && event.role === 'user'
        ? { ...event, text: stripPromptHiddenContext(event.text) }
        : event;

    if (
      transcriptEvent.kind === 'message' &&
      transcriptEvent.role === 'user' &&
      transcriptEvent.text.length === 0 &&
      !transcriptEvent.attachments?.length
    ) {
      return;
    }

    this.pushTranscriptEvent(transcriptEvent);
  }

  private flushReplayUserChunks(): void {
    const first = this.replayUserChunks[0];
    if (!first) return;

    const chunks = this.replayUserChunks;
    this.replayUserChunks = [];
    const text = stripPromptHiddenContext(chunks.map((chunk) => chunk.text).join(''));
    const attachments = chunks.flatMap((chunk) => chunk.attachments ?? []);
    if (text.length === 0 && attachments.length === 0) return;

    this.pushTranscriptEvent({
      ...first,
      text,
      ...(attachments.length > 0 ? { attachments } : {}),
    });
  }

  private pushTranscriptEvent(event: NormalizedEvent): void {
    const idleTranscriptEvent = this.isIdleAgentTranscriptEvent(event);
    if (idleTranscriptEvent) this.applyEvent({ type: 'AgentActivity', active: true });

    if (this.isTranscriptEvent(event) && !this.canAcceptTranscriptEvent()) {
      this.deps.logger.warn('SessionCell: dropping transcript update outside active turn', {
        conversationId: this.conversationId,
        phase: this.machine.phase.kind,
      });
      return;
    }

    const previousRunningAgentCount = this.lastRunningAgentCount;
    this.transcript.pushEvent(event);
    this.dispatchAgentsChangedIfNeeded(previousRunningAgentCount);
    if (idleTranscriptEvent) this.scheduleQuiesce();
    this.emitTranscriptChanged();
  }

  async prompt(input: PromptInput): Promise<Result<SessionPromptResult, AcpSendPromptError>> {
    const now = Date.now();
    const result = await this.sendPromptInternal({
      id: crypto.randomUUID(),
      ...input,
      createdAt: now,
      updatedAt: now,
    });
    if (result.success) this.clearDraft();
    return result;
  }

  queuePrompt(input: PromptInput): Result<void, InvalidStateError> {
    const now = Date.now();
    const result = this.dispatchFor<InvalidStateError>(
      {
        type: 'QueuePrompt',
        prompt: {
          id: crypto.randomUUID(),
          ...input,
          createdAt: now,
          updatedAt: now,
        },
      },
      ['invalid_state']
    );
    if (!result.success) return result;
    this.clearDraft();
    return ok();
  }

  setPromptDraft(update: PromptDraftUpdate): Result<void, never> {
    if (update.rev <= this.draftRev) return ok();
    this.draftRev = update.rev;

    if (update.input === null) {
      if (this.draft !== null) {
        this.draft = null;
        this.deps.callbacks?.onDraftChanged?.();
      }
      return ok();
    }

    this.draft = { ...update.input, rev: update.rev, updatedAt: Date.now() };
    this.deps.callbacks?.onDraftChanged?.();
    return ok();
  }

  editQueuedPrompt(id: string, input: PromptInput): Result<void, InvalidStateError> {
    const result = this.dispatchFor<InvalidStateError>(
      {
        type: 'EditQueuedPrompt',
        id,
        input,
        updatedAt: Date.now(),
      },
      ['invalid_state']
    );
    if (!result.success) return result;
    return ok();
  }

  removeQueuedPrompt(id: string): Result<void, InvalidStateError> {
    const result = this.dispatchFor<InvalidStateError>({ type: 'RemoveQueuedPrompt', id }, [
      'invalid_state',
    ]);
    if (!result.success) return result;
    return ok();
  }

  reorderQueue(ids: readonly string[]): Result<void, InvalidStateError> {
    const result = this.dispatchFor<InvalidStateError>({ type: 'ReorderQueue', ids }, [
      'invalid_state',
    ]);
    if (!result.success) return result;
    return ok();
  }

  async cancel(): Promise<Result<void, AcpCancelTurnError>> {
    const dispatchResult = this.dispatchFor<AcpCancelTurnError>({ type: 'Cancel' }, [
      'invalid_state',
    ]);
    if (!dispatchResult.success) return dispatchResult;
    try {
      await this.deps.agent.cancel({ sessionId: this.acpSessionId });
      return ok();
    } catch (e) {
      return acpErr.cancelFailed(toSerializedError(e));
    }
  }

  async closeSession(): Promise<void> {
    if (!this.deps.agent.closeSession) return;
    await this.deps.agent.closeSession({ sessionId: this.acpSessionId });
  }

  resolvePermission(requestId: string, optionId: string): Result<void, InvalidStateError> {
    if (!this.machine.pendingPermissions.some((p) => p.requestId === requestId)) {
      return acpErr.invalidState(`No resolver for requestId '${requestId}'`);
    }
    const dispatchResult = this.dispatchFor<InvalidStateError>(
      { type: 'ResolvePermission', requestId, optionId },
      ['invalid_state']
    );
    if (!dispatchResult.success) return dispatchResult;
    this.rawLog.record({
      kind: 'permission_resolved',
      sessionId: this.acpSessionId,
      requestId,
      optionId,
    });
    this.permissions.settle(requestId, optionId);
    return ok();
  }

  requestPermission(params: RequestPermissionRequest): Promise<RequestPermissionResponse> {
    const requestId = crypto.randomUUID();
    const body = permissionBody(params);
    const request: AcpPermissionRequest = {
      requestId,
      kind: 'permission',
      toolCall: this.buildPermissionToolCall(requestId, params.toolCall),
      ...(body !== undefined ? { body } : {}),
      options: params.options.map((option) => ({
        optionId: option.optionId,
        name: option.name,
        kind: option.kind,
      })),
    };
    this.rawLog.record({
      kind: 'permission_request',
      sessionId: params.sessionId,
      request: params,
    });
    this.applyEvent({ type: 'PermissionRequested', request });
    return this.permissions.request(request);
  }

  /**
   * An ACP form elicitation: Claude's AskUserQuestion and questions MCP
   * servers ask. Every choice field is put to the user one at a time through
   * the same pending-permission channel the composer already renders, and the
   * answers are folded into one accept response. Free-text fields have no
   * input here and stay empty, which the agent treats as skipped; a session
   * that ends mid-question cancels the whole elicitation.
   */
  async requestElicitation(params: CreateElicitationRequest): Promise<CreateElicitationResponse> {
    if (params.mode !== 'form') return { action: 'decline' };
    const questions = elicitationQuestions(params);
    if (questions.length === 0) return { action: 'decline' };
    const toolCallId = (params as { toolCallId?: unknown }).toolCallId;
    const content: Record<string, string | string[]> = {};
    for (const question of questions) {
      const requestId = crypto.randomUUID();
      const request: AcpPermissionRequest = {
        requestId,
        kind: 'question',
        toolCall: this.buildPermissionToolCall(
          requestId,
          typeof toolCallId === 'string'
            ? { toolCallId, title: question.title, kind: 'other' }
            : { toolCallId: requestId, title: question.title, kind: 'other' }
        ),
        body: question.body,
        options: [
          ...question.options.map((option) => ({
            optionId: option.value,
            name: option.label,
            kind: 'answer',
            ...(option.description !== undefined ? { description: option.description } : {}),
          })),
          { optionId: ELICITATION_SKIP_OPTION, name: 'Skip', kind: 'reject_once' },
        ],
      };
      this.applyEvent({ type: 'PermissionRequested', request });
      const response = await this.permissions.request(request);
      if (response.outcome.outcome !== 'selected') return { action: 'cancel' };
      const optionId = response.outcome.optionId;
      if (optionId === ELICITATION_SKIP_OPTION) continue;
      content[question.key] = question.multiSelect ? [optionId] : optionId;
    }
    return { action: 'accept', content };
  }

  async setMode(modeId: string): Promise<Result<void, AcpSetModeOptionError>> {
    const result = this.dispatchFor<AcpSetModeOptionError>({ type: 'SetMode', modeId }, [
      'invalid_state',
      'set_mode_failed',
    ]);
    if (!result.success) return result;
    const configId = this.transcript.config.modeOptions?.configId ?? null;
    if (configId && this.deps.agent.setSessionConfigOption) {
      try {
        const response = await this.deps.agent.setSessionConfigOption({
          sessionId: this.acpSessionId,
          configId,
          value: modeId,
        } satisfies SetSessionConfigOptionRequest);
        this.seedTranscriptMeta({ configOptions: response.configOptions });
        return ok();
      } catch (e) {
        return acpErr.setModeFailed(toSerializedError(e));
      }
    }
    if (!this.deps.agent.setSessionMode) {
      return acpErr.setModeFailed({
        name: 'Error',
        message: 'Agent connection does not support setSessionMode',
      });
    }
    try {
      await this.deps.agent.setSessionMode({
        sessionId: this.acpSessionId,
        modeId,
      } satisfies SetSessionModeRequest);
      return ok();
    } catch (e) {
      return acpErr.setModeFailed(toSerializedError(e));
    }
  }

  async setConfigOption(
    dimension: ConfigDimension,
    value: string
  ): Promise<Result<void, AcpSetModelOptionError>> {
    const configId = this.configIdForDimension(dimension);
    if (!configId) {
      return acpErr.setConfigFailed({
        name: 'Error',
        message: `Agent connection does not expose ${dimension} configuration`,
      });
    }
    const result = this.dispatchFor<AcpSetModelOptionError>(
      { type: 'SetConfigOption', configId, value },
      ['invalid_state', 'set_config_failed']
    );
    if (!result.success) return result;
    if (!this.deps.agent.setSessionConfigOption) return ok();
    try {
      const response = await this.deps.agent.setSessionConfigOption({
        sessionId: this.acpSessionId,
        configId,
        value,
      } satisfies SetSessionConfigOptionRequest);
      this.seedTranscriptMeta({ configOptions: response.configOptions });
      return ok();
    } catch (e) {
      return acpErr.setConfigFailed(toSerializedError(e));
    }
  }

  settleTurn(outcome: TranscriptTurnOutcome): void {
    const previousRunningAgentCount = this.lastRunningAgentCount;
    this.transcript.settleTurn(outcome);
    this.dispatchAgentsChangedIfNeeded(previousRunningAgentCount);
    this.emitTranscriptChanged();
    this.applyEvent({ type: 'TurnEnded', outcome: machineOutcome(outcome) });
  }

  processClosed(exitCode: number | null): void {
    this.clearQuiesce();
    this.applyEvent({ type: 'ProcessClosed', exitCode });
  }

  dispose(): void {
    this.clearQuiesce();
    this.effectDriver.dispose();
    this.permissions.drain(this.machine.pendingPermissions);
  }

  private dispatch(command: Command): Result<Effect[], AcpRuntimeError> {
    const result = this.machine.dispatch(command, this.context());
    if (!result.success) return result;
    this.interpretEffects(result.data);
    return result;
  }

  private dispatchFor<E extends AcpRuntimeError>(
    command: Command,
    expected: readonly E['type'][]
  ): Result<Effect[], E> {
    const result = this.dispatch(command);
    if (result.success) return result;
    if (expected.includes(result.error.type as E['type'])) return result as Result<Effect[], E>;
    throw new Error(`Unexpected ACP dispatch error '${result.error.type}'`);
  }

  private applyEvent(event: DomainEvent): void {
    this.interpretEffects(this.machine.apply(event));
  }

  private interpretEffects(effects: readonly Effect[]): void {
    this.effectDriver.run(effects);
  }

  private interpretEffect(effect: Effect): void {
    switch (effect.type) {
      case 'state':
      case 'permissionRequest':
        break;
      case 'permissionResolved':
        if (effect.cancelled) this.permissions.cancel(effect.requestId);
        break;
      case 'closed':
        this.deps.callbacks?.onClosed?.(effect.exitCode);
        break;
      case 'agentEvent':
        this.deps.callbacks?.onAgentEvent?.(effect.phase);
        break;
      case 'settleAgents':
        this.settleRunningAgents(effect.scope, effect.status);
        break;
      case 'sendPrompt':
        this.deps.callbacks?.onSendQueuedPrompt?.(effect.prompt);
        void this.sendPromptInternal(effect.prompt).then((result) => {
          if (!result.success) {
            this.deps.logger.warn('SessionCell: failed to send queued prompt', {
              conversationId: this.conversationId,
              error: result.error,
            });
          }
        });
        break;
      case 'warn':
        this.deps.logger.warn(`SessionCell: ${effect.message}`, {
          conversationId: this.conversationId,
        });
        break;
    }
  }

  private async sendPromptInternal(
    prompt: QueuedPrompt
  ): Promise<Result<SessionPromptResult, AcpSendPromptError>> {
    const decision = this.dispatchFor<AcpSendPromptError>({ type: 'Prompt', prompt }, [
      'invalid_state',
    ]);
    if (!decision.success) return decision;
    const started = decision.data.some(
      (effect) => effect.type === 'agentEvent' && effect.phase === 'start'
    );
    if (!started) return ok({ queued: true });

    const messageId = `${this.conversationId}-${this.machine.nextTurnIndex}-user`;
    this.transcript.pushEvent({
      kind: 'message',
      role: 'user',
      messageId,
      text: prompt.text,
      ...(prompt.attachments?.length
        ? {
            attachments: prompt.attachments.map((attachment, index) => ({
              id: attachment.type === 'attachment' ? attachment.id : `${messageId}-image-${index}`,
              name: attachment.name ?? `image-${index + 1}`,
              mimeType: attachment.mimeType,
            })),
          }
        : {}),
    });
    this.emitTranscriptChanged();

    try {
      const resolvedAttachments = await Promise.all(
        (prompt.attachments ?? []).map((attachment) =>
          this.deps.resolveAttachment(this.deps.conversationId, attachment)
        )
      );
      const promptRequest = {
        sessionId: this.acpSessionId,
        prompt: [
          ...resolvedAttachments.map((attachment) => ({
            type: 'image' as const,
            data: attachment.data,
            mimeType: attachment.mimeType,
          })),
          ...(prompt.text ? [{ type: 'text' as const, text: prompt.text }] : []),
          ...(prompt.hiddenContext
            ? [{ type: 'text' as const, text: encodePromptHiddenContext(prompt.hiddenContext) }]
            : []),
        ],
      };
      this.rawLog.record({
        kind: 'prompt',
        sessionId: this.acpSessionId,
        content: promptRequest.prompt,
      });
      const response = await this.deps.agent.prompt(promptRequest);
      this.rawLog.record({
        kind: 'prompt_result',
        sessionId: this.acpSessionId,
        stopReason: response.stopReason,
      });
      this.settleTurn(outcomeFromStopReason(response.stopReason));
      return ok({ queued: false });
    } catch (e) {
      const err = acpErr.promptFailed(toSerializedError(e));
      this.rawLog.record({
        kind: 'prompt_result',
        sessionId: this.acpSessionId,
        stopReason: null,
      });
      this.settleTurn({ kind: 'error', reason: 'prompt_failed' });
      return err;
    }
  }

  private seedTranscriptMeta(meta?: {
    modes?: SessionModeState | null;
    configOptions?: readonly SessionConfigOption[] | null;
  }): void {
    if (!meta) return;
    if (meta.configOptions !== undefined) {
      this.transcript.pushEvent({
        kind: 'config',
        options: meta.configOptions ?? [],
      });
    }
    if (meta.modes?.currentModeId) {
      this.transcript.pushEvent({
        kind: 'mode_selected',
        modeId: meta.modes.currentModeId,
      });
    }
    if (meta.configOptions !== undefined || meta.modes?.currentModeId) {
      this.emitTranscriptChanged();
    }
  }

  private dispatchAgentsChangedIfNeeded(previousRunningAgentCount: number): void {
    const nextRunningAgentCount = this.transcript.agents.filter(
      (agent) => agent.background === true && agent.status === 'running'
    ).length;
    if (nextRunningAgentCount === previousRunningAgentCount) return;
    this.lastRunningAgentCount = nextRunningAgentCount;
    this.applyEvent({ type: 'AgentsChanged', runningCount: nextRunningAgentCount });
  }

  private settleRunningAgents(scope: 'turn' | 'all', status: 'completed' | 'failed'): void {
    const runningAgents = this.transcript.agents.filter((agent) => {
      if (agent.status !== 'running') return false;
      return scope === 'all' || agent.background !== true;
    });

    for (const agent of runningAgents) {
      this.push({
        kind: 'subagent_update',
        agentId: agent.agentId,
        toolCallId: agent.toolCallId,
        status,
      });
    }
  }

  private clearDraft(): void {
    this.draftRev += 1;
    if (this.draft === null) return;
    this.draft = null;
    this.deps.callbacks?.onDraftChanged?.();
  }

  private scheduleQuiesce(): void {
    if (this.quiesceTimer) clearTimeout(this.quiesceTimer);
    this.quiesceTimer = setTimeout(() => {
      this.quiesceTimer = null;
      if (!this.machine.agentTurnActive) return;
      this.transcript.settleTurn({ kind: 'done', reason: 'quiesced' });
      this.emitTranscriptChanged();
      this.applyEvent({ type: 'AgentActivity', active: false });
    }, 250);
  }

  private clearQuiesce(): void {
    if (!this.quiesceTimer) return;
    clearTimeout(this.quiesceTimer);
    this.quiesceTimer = null;
  }

  private context(): SessionMachineContext {
    return {
      modeIds: this.transcript.config.modeOptions?.available.map((mode) => mode.id) ?? [],
      configOptionIds: [
        ...(this.transcript.config.modelOptions
          ? [this.transcript.config.modelOptions.configId]
          : []),
        ...(this.transcript.config.efforts ? [this.transcript.config.efforts.configId] : []),
      ],
    };
  }

  private configIdForDimension(dimension: ConfigDimension): string | null {
    switch (dimension) {
      case 'model':
        return this.transcript.config.modelOptions?.configId ?? null;
      case 'effort':
        return this.transcript.config.efforts?.configId ?? null;
    }
  }

  private isTranscriptEvent(event: NormalizedEvent): boolean {
    switch (event.kind) {
      case 'message':
      case 'thinking':
      case 'tool_call':
      case 'tool_update':
      case 'subagent':
      case 'search':
      case 'mcp_tool':
      case 'web_fetch':
      case 'plan':
        return true;
      default:
        return false;
    }
  }

  private isIdleAgentTranscriptEvent(event: NormalizedEvent): boolean {
    return (
      this.machine.phase.kind === 'ready' &&
      this.isTranscriptEvent(event) &&
      !(event.kind === 'message' && event.role === 'user')
    );
  }

  private canAcceptTranscriptEvent(): boolean {
    return (
      this.machine.phase.kind === 'working' ||
      this.machine.phase.kind === 'replaying' ||
      this.machine.phase.kind === 'ready' ||
      this.machine.agentTurnActive
    );
  }

  private buildPermissionToolCall(
    requestId: string,
    rawToolCall: RequestPermissionRequest['toolCall'] | undefined
  ): ToolCallItem {
    const activeTurn = this.transcript.activeTurn;
    const toolCallId = rawToolCall?.toolCallId ?? requestId;
    if (activeTurn) {
      const id = makeToolId(activeTurn.id, toolCallId);
      const existing = findToolCall(activeTurn.items, id, toolCallId);
      if (existing) return structuredClone(existing);
    }

    return createToolCallItem({
      id: activeTurn ? makeToolId(activeTurn.id, toolCallId) : `permission:${toolCallId}`,
      seq: 0,
      toolCallId,
      title: rawToolCall?.title ?? permissionTitle(rawToolCall),
      toolKind: rawToolCall?.kind ?? null,
      status: 'pending',
      parentToolCallId: undefined,
    });
  }

  private emitTranscriptChanged(): void {
    this.deps.callbacks?.onTranscriptChanged?.();
  }
}

const ELICITATION_SKIP_OPTION = '__skip__';
const PERMISSION_BODY_LIMIT = 2_000;

/** A request that arrives before its tool call still gets a meaningful name. */
function permissionTitle(rawToolCall: RequestPermissionRequest['toolCall'] | undefined): string {
  const rawInput = rawToolCall?.rawInput;
  const command =
    rawInput && typeof rawInput === 'object' ? (rawInput as { command?: unknown }).command : null;
  if (typeof command === 'string' && command.trim()) return command.trim();
  switch (rawToolCall?.kind) {
    case 'edit':
      return 'Edit files';
    case 'execute':
      return 'Run a command';
    case 'fetch':
      return 'Fetch a page';
    default:
      return 'Permission request';
  }
}

/**
 * What the user is deciding on: the request's text content (a plan, a
 * permissions scope, an MCP question), else the command, else the file paths
 * Codex tucks into its own metadata.
 */
function permissionBody(params: RequestPermissionRequest): string | undefined {
  const parts: string[] = [];
  const content = params.toolCall?.content;
  if (Array.isArray(content)) {
    for (const block of content) {
      if (block.type === 'content' && block.content.type === 'text' && block.content.text.trim()) {
        parts.push(block.content.text.trim());
      }
    }
  }
  if (parts.length === 0) {
    const rawInput = params.toolCall?.rawInput;
    const command =
      rawInput && typeof rawInput === 'object' ? (rawInput as { command?: unknown }).command : null;
    if (typeof command === 'string' && command.trim()) parts.push(command.trim());
  }
  if (parts.length === 0) {
    const meta = (params as { _meta?: unknown })._meta as { codex?: { params?: unknown } } | null;
    const paths = collectPathLike(meta?.codex?.params);
    if (paths.length > 0) parts.push(paths.join('\n'));
  }
  const body = parts.join('\n\n');
  if (!body) return undefined;
  return body.length > PERMISSION_BODY_LIMIT ? `${body.slice(0, PERMISSION_BODY_LIMIT)}…` : body;
}

function collectPathLike(value: unknown, depth = 0, out: string[] = []): string[] {
  if (!value || typeof value !== 'object' || depth > 3) return out;
  if (Array.isArray(value)) {
    for (const entry of value) collectPathLike(entry, depth + 1, out);
    return out;
  }
  for (const [key, entry] of Object.entries(value)) {
    if (
      (key === 'path' || key === 'file' || key === 'cwd' || key === 'command') &&
      typeof entry === 'string' &&
      entry &&
      !out.includes(entry)
    ) {
      out.push(entry);
    } else if (entry && typeof entry === 'object') {
      collectPathLike(entry, depth + 1, out);
    }
  }
  return out;
}

type ElicitationQuestion = {
  key: string;
  title: string;
  body: string;
  multiSelect: boolean;
  options: Array<{ value: string; label: string; description?: string }>;
};

/** The choice fields of a form elicitation, in schema order. */
function elicitationQuestions(
  params: Extract<CreateElicitationRequest, { mode: 'form' }>
): ElicitationQuestion[] {
  const properties = params.requestedSchema.properties ?? {};
  const questions: ElicitationQuestion[] = [];
  for (const [key, schema] of Object.entries(properties)) {
    const field = schema as {
      type?: unknown;
      title?: unknown;
      description?: unknown;
      enum?: unknown;
      oneOf?: unknown;
      items?: { anyOf?: unknown } | null;
    };
    const multiSelect = field.type === 'array';
    const enumOptions = multiSelect ? field.items?.anyOf : (field.oneOf ?? field.enum);
    if (!Array.isArray(enumOptions) || enumOptions.length === 0) continue;
    const options = enumOptions.flatMap((option) => {
      if (typeof option === 'string') return [{ value: option, label: option }];
      const candidate = option as { const?: unknown; title?: unknown; _meta?: unknown };
      if (typeof candidate.const !== 'string') return [];
      const meta = (candidate._meta as Record<string, unknown> | null | undefined)?.[
        '_claude/askUserQuestionOption'
      ] as { description?: unknown } | undefined;
      const description = typeof meta?.description === 'string' ? meta.description : undefined;
      const label =
        description !== undefined
          ? candidate.const
          : typeof candidate.title === 'string' && candidate.title
            ? candidate.title
            : candidate.const;
      return [{ value: candidate.const, label, ...(description ? { description } : {}) }];
    });
    if (options.length === 0) continue;
    const title = typeof field.title === 'string' && field.title ? field.title : key;
    const body =
      typeof field.description === 'string' && field.description
        ? field.description
        : params.message;
    questions.push({ key, title, body, multiSelect, options });
  }
  return questions;
}

function findToolCall(
  items: Array<ToolNode | { kind: string; id: string }>,
  id: string,
  toolCallId: string
): ToolCallItem | undefined {
  for (const item of items) {
    if (item.kind.endsWith('-tool-call') && 'toolCallId' in item) {
      if (item.id === id || item.toolCallId === toolCallId) return item as ToolCallItem;
      const found = findToolCall((item as ToolCallItem).children ?? [], id, toolCallId);
      if (found) return found;
    } else if (item.kind === 'tool-group' && 'children' in item) {
      const found = findToolCall(item.children as ToolNode[], id, toolCallId);
      if (found) return found;
    }
  }
  return undefined;
}

function machineOutcome(
  outcome: TranscriptTurnOutcome
): { kind: 'stopped'; stopReason: StopReason } | { kind: 'errored' } {
  if (outcome.kind === 'error') return { kind: 'errored' };
  if (outcome.kind === 'cancelled') return { kind: 'stopped', stopReason: 'cancelled' };
  return { kind: 'stopped', stopReason: toStopReason(outcome.reason) };
}

function outcomeFromStopReason(stopReason: StopReason): TranscriptTurnOutcome {
  if (stopReason === 'cancelled') return { kind: 'cancelled', reason: stopReason };
  return { kind: 'done', reason: stopReason };
}

function isSessionStateEffect(effect: Effect): boolean {
  return (
    effect.type === 'state' ||
    effect.type === 'permissionRequest' ||
    effect.type === 'permissionResolved'
  );
}

function toStopReason(reason: TranscriptTurnOutcome['reason']): StopReason {
  switch (reason) {
    case 'cancelled':
    case 'end_turn':
    case 'max_tokens':
    case 'max_turn_requests':
    case 'refusal':
      return reason;
    default:
      return 'end_turn';
  }
}

export { SESSION_PLAN_ID };
