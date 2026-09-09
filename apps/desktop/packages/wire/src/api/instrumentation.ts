export type WireCallStartEvent = {
  callId: string;
  path: string;
  input?: unknown;
  side?: 'client' | 'server';
};

export type WireCallEndEvent = {
  callId: string;
  path: string;
  durationMs: number;
  ok: boolean;
  result?: unknown;
  errorCode?: string;
  errorMessage?: string;
  side?: 'client' | 'server';
};

export type WireSnapshotEvent = {
  requestId: string;
  topic: string;
  durationMs: number;
  ok: boolean;
  errorCode?: string;
};

export type WireTopicAttachEvent = {
  topic: string;
  attachmentCount?: number;
};

export type WireTopicDetachEvent = {
  topic: string;
  attachmentCount?: number;
};

export type WireCancelEvent = {
  callId: string;
  side?: 'client' | 'server';
};

export type WireResyncReason = 'generation' | 'sequence-gap' | 'patch-failed' | 'validation';

export type WireResyncEvent = {
  topic?: string;
  reason: WireResyncReason;
  details?: Record<string, unknown>;
};

export type WireResyncFailedEvent = {
  topic?: string;
  error: unknown;
  /** Consecutive failed resync attempts in the current stale episode, 1-based. */
  attempt: number;
  /** Whether the follower's resync failure policy decided to retry. */
  willRetry: boolean;
};

export type WireCursorTranslationTimeoutEvent = {
  /** Live model id from the cursor entry that failed to translate. */
  model: string;
  mutationId?: string;
  error: unknown;
};

export type WireMutationDedupedEvent = {
  mutationId: string;
  path: string;
};

export type WireBatchDroppedEvent = {
  error: unknown;
};

export type WireScopeCleanupErrorEvent = {
  label?: string;
  error: unknown;
};

export type WireTransportEvent = {
  event: 'connect' | 'disconnect' | 'reconnect';
};

export type WireInstrumentation = {
  callStart?(event: WireCallStartEvent): void;
  callEnd?(event: WireCallEndEvent): void;
  snapshot?(event: WireSnapshotEvent): void;
  topicAttach?(event: WireTopicAttachEvent): void;
  topicDetach?(event: WireTopicDetachEvent): void;
  cancel?(event: WireCancelEvent): void;
  resync?(event: WireResyncEvent): void;
  resyncFailed?(event: WireResyncFailedEvent): void;
  cursorTranslationTimeout?(event: WireCursorTranslationTimeoutEvent): void;
  mutationDeduped?(event: WireMutationDedupedEvent): void;
  batchDropped?(event: WireBatchDroppedEvent): void;
  scopeCleanupError?(event: WireScopeCleanupErrorEvent): void;
  transport?(event: WireTransportEvent): void;
};

export const noopInstrumentation: WireInstrumentation = {};

export function mergeInstrumentation(
  ...parts: Array<WireInstrumentation | undefined>
): WireInstrumentation {
  const active = parts.filter((part): part is WireInstrumentation => part !== undefined);
  if (active.length === 0) return noopInstrumentation;
  if (active.length === 1) return active[0];

  return {
    callStart: (event) => emit(active, 'callStart', event),
    callEnd: (event) => emit(active, 'callEnd', event),
    snapshot: (event) => emit(active, 'snapshot', event),
    topicAttach: (event) => emit(active, 'topicAttach', event),
    topicDetach: (event) => emit(active, 'topicDetach', event),
    cancel: (event) => emit(active, 'cancel', event),
    resync: (event) => emit(active, 'resync', event),
    resyncFailed: (event) => emit(active, 'resyncFailed', event),
    cursorTranslationTimeout: (event) => emit(active, 'cursorTranslationTimeout', event),
    mutationDeduped: (event) => emit(active, 'mutationDeduped', event),
    batchDropped: (event) => emit(active, 'batchDropped', event),
    scopeCleanupError: (event) => emit(active, 'scopeCleanupError', event),
    transport: (event) => emit(active, 'transport', event),
  };
}

function emit<Key extends keyof WireInstrumentation>(
  parts: WireInstrumentation[],
  key: Key,
  event: Parameters<NonNullable<WireInstrumentation[Key]>>[0]
): void {
  for (const part of parts) {
    try {
      (part[key] as ((value: typeof event) => void) | undefined)?.(event);
    } catch {
      // Observability hooks must never affect wire behavior.
    }
  }
}
