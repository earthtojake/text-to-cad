import {
  agentStateSchema,
  planStateSchema,
  promptDraftSchema,
  sessionUsageSchema,
  sessionConfigStateSchema,
  sessionMcpServerSchema,
  sessionStateSchema,
  terminalStateSchema,
  transcriptTurnSchema,
  type AttachmentMimeType,
  type AttachmentRef,
  type AcpRuntimeError,
  type HistoryPage,
  type PromptDraftUpdate,
  type PromptInput,
  type PromptPlacement,
  type SessionState,
  type TerminalState,
} from '@emdash/core/runtimes/acp/api/client';
import type { RuntimeResolveError } from '@emdash/core/services/runtime-broker/api';
import { createEmitter, type Result, type Unsubscribe } from '@emdash/shared';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { TimeoutError, runWithTimeout } from '@emdash/shared/scheduling';
import { ReplicaLog, createLineLogStore } from '@emdash/wire/live';
import { type BlobSource } from '@emdash/wire/rpc';
import { observe, remote, whenReady, type Readable } from '@emdash/wire/state';
import { observable, runInAction } from 'mobx';
import { z } from 'zod';
import {
  getConversationsClient,
  type ConversationsClient,
} from '@core/features/conversations/api/browser/client';
import type { ProjectAttachmentError } from '@core/features/projects/api/attachments';
import { conversationsContract } from '../../api';
import { AcpStartupCoordinator, type AcpStartupPhase } from './acp-startup-coordinator';

const acpStartupCoordinator = new AcpStartupCoordinator({ maxConcurrent: 2 });

export interface LiveValueSource<T> {
  getSnapshot(): T;
  subscribe(cb: () => void): Unsubscribe;
}

/**
 * Line-structured live terminal output. `lines()` returns the store's
 * identity-stable array (mutated in place); `version()` bumps once per
 * frame-coalesced flush; `truncated()` is true when output was dropped
 * upstream (agent ring buffer) or by the client store's byte cap.
 */
export type AcpTerminalOutput = {
  lines(): readonly string[];
  truncated(): boolean;
  version(): number;
  onFlush(listener: () => void): Unsubscribe;
};

type RemoteValueState<T> = {
  readonly ready: Promise<void>;
  current(): T;
  onChange(cb: (value: T) => void): Unsubscribe;
  dispose(): Promise<void>;
};

export function asValueSource<T>(replica: RemoteValueState<T>): LiveValueSource<T> {
  return {
    getSnapshot: () => replica.current(),
    subscribe: (cb) => replica.onChange(() => cb()),
  };
}

export class AcpStartError extends Error {
  constructor(
    readonly runtimeError: AcpRuntimeError | RuntimeResolveError | ProjectAttachmentError
  ) {
    super(
      ('message' in runtimeError ? runtimeError.message : undefined) ??
        ('cause' in runtimeError ? runtimeError.cause?.message : undefined) ??
        runtimeError.type
    );
    this.name = 'AcpStartError';
  }

  get errorType(): (AcpRuntimeError | RuntimeResolveError | ProjectAttachmentError)['type'] {
    return this.runtimeError.type;
  }
}

export class AcpLiveSession {
  readonly sessionState: RemoteValueState<SessionState>;
  readonly config: RemoteValueState<z.infer<typeof sessionConfigStateSchema>>;
  readonly usage: RemoteValueState<z.infer<typeof sessionUsageSchema> | null>;
  readonly plan: RemoteValueState<z.infer<typeof planStateSchema> | null>;
  readonly activeTurn: RemoteValueState<z.infer<typeof transcriptTurnSchema> | null>;
  readonly draft: RemoteValueState<z.infer<typeof promptDraftSchema> | null>;
  readonly terminals: RemoteValueState<TerminalState[]>;
  readonly mcpServers: RemoteValueState<Array<z.infer<typeof sessionMcpServerSchema>>>;
  readonly agents: RemoteValueState<Array<z.infer<typeof agentStateSchema>>>;
  private readonly scope = createScope({ label: 'acp-live-session' });
  private readonly terminalLogs = new Map<
    string,
    { replica: ReplicaLog; output: AcpTerminalOutput }
  >();
  private disposed = false;

  private constructor(
    readonly conversationId: string,
    private readonly client: ConversationsClient['acp']
  ) {
    const key = { conversationId };
    const sessionRemote = remote(conversationsContract.acp.session, client.session, {
      scope: this.scope,
      lingerMs: 15_000,
    });
    const member = sessionRemote(key);
    this.sessionState = remoteValueState(member.states.state, sessionStateSchema, this.scope);
    this.config = remoteValueState(member.states.config, sessionConfigStateSchema, this.scope);
    this.usage = remoteValueState(member.states.usage, sessionUsageSchema.nullable(), this.scope);
    this.plan = remoteValueState(member.states.plan, planStateSchema.nullable(), this.scope);
    this.activeTurn = remoteValueState(
      member.states.activeTurn,
      transcriptTurnSchema.nullable(),
      this.scope
    );
    this.draft = remoteValueState(member.states.draft, promptDraftSchema.nullable(), this.scope);
    this.terminals = remoteValueState(
      member.states.terminals,
      z.array(terminalStateSchema),
      this.scope
    );
    this.mcpServers = remoteValueState(
      member.states.mcpServers,
      z.array(sessionMcpServerSchema),
      this.scope
    );
    this.agents = remoteValueState(member.states.agents, z.array(agentStateSchema), this.scope);
  }

  static async create(
    conversationId: string,
    options: { onPhase?: (phase: AcpStartupPhase) => void; compatibilityKey?: string } = {}
  ): Promise<AcpLiveSession> {
    const client = (await getConversationsClient()).acp;
    const result = await acpStartupCoordinator.run(
      conversationId,
      () =>
        withTimeout(
          (signal) => client.start({ conversationId }, { signal, timeoutMs: 0 }),
          'Timed out starting ACP session',
          25_000
        ),
      {
        onPhase: options.onPhase,
        compatibilityKey: options.compatibilityKey,
        shouldRetry: shouldRetryAcpStart,
      }
    );
    if (!result.success) {
      throw new AcpStartError(result.error);
    }
    options.onPhase?.('connecting');
    const session = new AcpLiveSession(conversationId, client);
    try {
      await withTimeout(
        Promise.all([
          session.sessionState.ready,
          session.config.ready,
          session.usage.ready,
          session.plan.ready,
          session.activeTurn.ready,
          session.draft.ready,
          session.terminals.ready,
          session.mcpServers.ready,
        ]),
        'Timed out connecting ACP live models'
      );
      return session;
    } catch (error) {
      session.dispose();
      throw error;
    }
  }

  start(): Promise<Result<{ sessionId: string }, unknown>> {
    return this.client.start({ conversationId: this.conversationId });
  }

  async resume(): Promise<Result<HistoryPage, unknown>> {
    const result = await this.client.resume({ conversationId: this.conversationId });
    if (!result.success) return result;
    return {
      success: true,
      data: {
        turns: result.data.turns,
        nextCursor: result.data.nextCursor,
      },
    };
  }

  getHistory(before?: number, limit = 50): Promise<Result<HistoryPage, unknown>> {
    return this.client.getHistory({ conversationId: this.conversationId, before, limit });
  }

  async exportTranscript(): Promise<Result<string, unknown>> {
    const result = await this.client.exportAcpTranscript({
      conversationId: this.conversationId,
    });
    if (!result.success) return result;
    return { success: true, data: result.data.transcript };
  }

  async exportRawAcpLog(): Promise<Result<string, unknown>> {
    const result = await this.client.exportRawAcpLog({ conversationId: this.conversationId });
    if (!result.success) return result;
    return { success: true, data: result.data.log };
  }

  uploadAttachment(input: {
    data?: Uint8Array;
    source?: BlobSource;
    size?: number;
    mimeType: AttachmentMimeType;
    name?: string;
    originalPath?: string;
  }): Promise<Result<AttachmentRef, unknown>> {
    return this.client.uploadAttachment(
      { conversationId: this.conversationId, originalPath: input.originalPath },
      {
        name: input.name ?? 'attachment',
        mimeType: input.mimeType,
        size: input.size ?? input.data?.byteLength,
        source:
          input.source ?? (input.data ? singleChunk(input.data) : singleChunk(new Uint8Array())),
      }
    );
  }

  downloadAttachment(
    id: string
  ): Promise<Result<{ ref: AttachmentRef; data: Uint8Array }, unknown>> {
    return this.client
      .downloadAttachment({ conversationId: this.conversationId, attachmentId: id })
      .then(async (result) => {
        if (!result.success) return result;
        return {
          success: true,
          data: {
            ref: result.data.meta,
            data: await result.data.bytes(),
          },
        };
      });
  }

  deleteAttachment(id: string): Promise<Result<void, unknown>> {
    return this.client.deleteAttachment({
      conversationId: this.conversationId,
      attachmentId: id,
    });
  }

  sendPrompt(
    prompt: PromptInput,
    placement?: PromptPlacement
  ): Promise<Result<{ queued: boolean }, unknown>> {
    return this.client.sendPrompt(
      { conversationId: this.conversationId, prompt, placement },
      { timeoutMs: 0 }
    );
  }

  editQueuedPrompt(id: string, input: PromptInput): Promise<Result<void, unknown>> {
    return this.client.editQueuedPrompt({ conversationId: this.conversationId, id, input });
  }

  deleteQueuedPrompt(id: string): Promise<Result<void, unknown>> {
    return this.client.deleteQueuedPrompt({ conversationId: this.conversationId, id });
  }

  changeQueuePromptOrder(ids: string[]): Promise<Result<void, unknown>> {
    return this.client.changeQueuePromptOrder({ conversationId: this.conversationId, ids });
  }

  cancelTurn(): Promise<Result<void, unknown>> {
    return this.client.cancelTurn({ conversationId: this.conversationId });
  }

  setPromptDraft(draft: PromptDraftUpdate): Promise<Result<void, unknown>> {
    return this.client.setPromptDraft({ conversationId: this.conversationId, draft });
  }

  setModelOption(dimension: 'model' | 'effort', value: string): Promise<Result<void, unknown>> {
    return this.client.setModelOption({ conversationId: this.conversationId, dimension, value });
  }

  setModeOption(value: string): Promise<Result<void, unknown>> {
    return this.client.setModeOption({ conversationId: this.conversationId, value });
  }

  resolvePermission(requestId: string, optionId: string): Promise<Result<void, unknown>> {
    return this.client.resolvePermission({
      conversationId: this.conversationId,
      requestId,
      optionId,
    });
  }

  async terminalOutput(terminalId: string): Promise<AcpTerminalOutput> {
    const existing = this.terminalLogs.get(terminalId);
    if (existing) return existing.output;
    const store = createLineLogStore();
    const replica = new ReplicaLog(
      this.client.terminalOutput.handle({ conversationId: this.conversationId, terminalId }),
      { store }
    );
    const output: AcpTerminalOutput = {
      lines: () => store.lines(),
      truncated: () => store.truncated(),
      version: () => store.version(),
      onFlush: (listener) => store.onFlush(listener),
    };
    this.terminalLogs.set(terminalId, { replica, output });
    await replica.ready;
    if (this.disposed) void replica.dispose();
    return output;
  }

  dispose(): void {
    this.disposed = true;
    void this.scope.dispose();
    for (const { replica } of this.terminalLogs.values()) {
      void replica.dispose();
    }
    this.terminalLogs.clear();
  }
}

export function shouldRetryAcpStart(
  outcome:
    | {
        kind: 'value';
        value: Awaited<ReturnType<ConversationsClient['acp']['start']>>;
      }
    | { kind: 'error'; error: unknown }
): boolean {
  if (outcome.kind === 'error') return isTransientStartupError(outcome.error);
  if (outcome.value.success) return false;
  const error = outcome.value.error;
  if (
    error.type !== 'spawn_failed' &&
    error.type !== 'initialize_failed' &&
    error.type !== 'new_session_failed'
  ) {
    return false;
  }
  return isTransientStartupError(error);
}

export function isTransientStartupError(error: unknown): boolean {
  const details = startupErrorDetails(error);
  const transientCodes = new Set([
    'EBUSY',
    'ECONNREFUSED',
    'ECONNRESET',
    'EPIPE',
    'ETIMEDOUT',
    'EAI_AGAIN',
  ]);
  if (details.codes.some((code) => transientCodes.has(code.toUpperCase()))) return true;
  const message = details.messages.join(' ').toLowerCase();
  return [
    'timed out',
    'timeout',
    'temporarily unavailable',
    'connection closed',
    'connection reset',
    'connection refused',
    'econnrefused',
    'econnreset',
    'etimedout',
    'epipe',
    'resource busy',
    'overloaded',
  ].some((candidate) => message.includes(candidate));
}

function startupErrorDetails(error: unknown): { messages: string[]; codes: string[] } {
  const messages: string[] = [];
  const codes: string[] = [];
  const visited = new Set<object>();
  let current: unknown = error;
  for (let depth = 0; current !== undefined && current !== null && depth < 6; depth += 1) {
    if (current instanceof Error) {
      messages.push(current.message);
      const withCode = current as Error & { code?: unknown; cause?: unknown };
      if (typeof withCode.code === 'string') codes.push(withCode.code);
      current = withCode.cause;
      continue;
    }
    if (typeof current !== 'object') {
      messages.push(String(current));
      break;
    }
    if (visited.has(current)) break;
    visited.add(current);
    const value = current as { message?: unknown; code?: unknown; cause?: unknown };
    if (typeof value.message === 'string') messages.push(value.message);
    if (typeof value.code === 'string') codes.push(value.code);
    current = value.cause;
  }
  if (messages.length === 0) messages.push(String(error));
  return { messages, codes };
}

async function* singleChunk(data: Uint8Array): AsyncIterable<Uint8Array> {
  yield data;
}

export function remoteValueState<T>(
  source: Readable<T | undefined>,
  schema: z.ZodType<T>,
  parentScope: Scope
): RemoteValueState<T> {
  const scope = parentScope.child('remote-value-state');
  const changes = createEmitter<T>();
  const value = observable.box<T | undefined>(undefined, { deep: false });
  const update = (next: T): void => {
    runInAction(() => value.set(next));
  };
  const ready = whenReady(source, { scope }).then((settled) => {
    if (settled.status === 'error' && settled.value === undefined) {
      throw readableError(settled.error);
    }
    if (settled.value !== undefined) update(schema.parse(settled.value));
  });
  observe(
    source,
    (snapshot) => {
      if (snapshot.value !== undefined) {
        const next = schema.parse(snapshot.value);
        update(next);
        changes.emit(next);
      }
    },
    { scope }
  );
  return {
    ready,
    current() {
      return value.get() as T;
    },
    onChange(cb) {
      return changes.subscribe(cb);
    },
    dispose() {
      return scope.dispose();
    },
  };
}

function readableError(error: unknown): Error {
  if (error instanceof Error) return error;
  return new Error(error === undefined ? 'Remote live model failed to load' : String(error));
}

function withTimeout<T>(
  work: Promise<T> | ((signal: AbortSignal) => Promise<T>),
  message: string,
  ms = 10_000
): Promise<T> {
  return runWithTimeout((signal) => (typeof work === 'function' ? work(signal) : work), {
    timeoutMs: ms,
  }).catch((error: unknown) => {
    if (error instanceof TimeoutError) throw new Error(message);
    throw error;
  });
}
