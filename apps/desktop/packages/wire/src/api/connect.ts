import type { Unsubscribe } from '@emdash/shared';
import { systemClock, type Clock, type TimerHandle } from '@emdash/shared/scheduling';
import {
  createBlobConsumer,
  createBlobProducer,
  type BlobConsumer,
  type BlobProducer,
  type BlobSource,
} from './blob-channel';
import type { LiveSnapshot, LiveUpdate } from './channel';
import type { WireInstrumentation } from './instrumentation';
import {
  WireError,
  type SerializedWireError,
  type WireFileMeta,
  type WireMessage,
  type WireTransport,
} from './protocol';
import {
  findStructuredCloneFailure,
  formatStructuredCloneFailure,
  isStructuredCloneError,
} from './structured-clone';

export type CallOptions = {
  signal?: AbortSignal;
  /**
   * Per-call override of the connection-level call deadline. Values <= 0
   * disable the deadline for this call.
   */
  timeoutMs?: number;
  upload?: {
    channel: string;
    meta: WireFileMeta;
  };
};

export type AttachOptions = {
  onReattach?: () => void;
  onReattachError?: (error: WireError, context: { retrying: boolean }) => void;
};

export type ConnectOptions = {
  instrumentation?: WireInstrumentation;
  clock?: Clock;
  /**
   * Default deadline for calls and snapshot requests, spanning call-issued to
   * result-received — including any time a call spends held while the
   * transport is disconnected. Live attach traffic and blob streaming are
   * exempt. Values <= 0 disable the deadline.
   */
  callTimeoutMs?: number;
  /**
   * Bound on calls held while disconnected. Overflow rejects the newly issued
   * call immediately; held calls are never silently dropped.
   */
  maxHeldCalls?: number;
};

export const DEFAULT_CALL_TIMEOUT_MS = 30_000;
const DEFAULT_MAX_HELD_CALLS = 1_000;

type PendingCall = {
  message: WireMessage & { id: string };
  resolve(value: unknown): void;
  reject(error: Error): void;
  cleanup(): void;
  posted: boolean;
  deadline: TimerHandle | undefined;
};

type Attachment = {
  pushes: Set<(update: LiveUpdate) => void>;
  onReattach: Set<() => void>;
  onReattachError: Set<(error: WireError, context: { retrying: boolean }) => void>;
  established: Promise<void>;
  establishedSettled: boolean;
  attempt: object | null;
  attachId: string | undefined;
};

export type Connection = {
  call(path: string, input: unknown, options?: CallOptions): Promise<unknown>;
  openBlobConsumer(channel: string): BlobConsumer;
  openBlobProducer(channel: string, source: BlobSource): BlobProducer;
  snapshot(topic: string): Promise<LiveSnapshot<unknown>>;
  attach(
    topic: string,
    push: (update: LiveUpdate) => void,
    options?: AttachOptions
  ): Promise<Unsubscribe>;
  onDisconnect(cb: () => void): Unsubscribe;
  /** Disposes this logical connection without closing the underlying transport. */
  dispose(): void;
};

export function connect(transport: WireTransport, options: ConnectOptions = {}): Connection {
  const pending = new Map<string, PendingCall>();
  const heldCallIds: string[] = [];
  const attachments = new Map<string, Attachment>();
  const blobConsumers = new Map<string, BlobConsumer>();
  const blobProducers = new Map<string, BlobProducer>();
  const disconnectListeners = new Set<() => void>();
  const instrumentation = options.instrumentation;
  const clock = options.clock ?? systemClock;
  const callTimeoutMs = options.callTimeoutMs ?? DEFAULT_CALL_TIMEOUT_MS;
  const maxHeldCalls = Math.max(0, options.maxHeldCalls ?? DEFAULT_MAX_HELD_CALLS);
  // Only reconnect-capable transports can restore connectivity, so only they
  // opt calls into hold-until-deadline; plain transports keep failing fast.
  const holdsWhileDisconnected = typeof transport.onReconnect === 'function';
  let connected = true;
  let terminal = false;
  let terminalCause: unknown;
  let disposed = false;

  instrumentation?.transport?.({ event: 'connect' });

  const unsubscribeMessage = transport.onMessage((message) => {
    if (disposed) return;
    if (message.kind === 'result') {
      const pendingCall = pending.get(message.id);
      if (!pendingCall) return;
      pending.delete(message.id);
      pendingCall.cleanup();
      if (message.ok) {
        pendingCall.resolve(message.value);
      } else {
        pendingCall.reject(new WireError(message.code, message.message, { cause: message.cause }));
      }
      return;
    }

    if (message.kind === 'update') {
      for (const push of attachments.get(message.topic)?.pushes ?? []) push(message.update);
      return;
    }

    if (message.kind === 'topic-gap') {
      notifyReattached(attachments.get(message.topic));
      return;
    }

    if (message.kind === 'topic-error') {
      const entry = attachments.get(message.topic);
      const error = wireErrorFromSerialized(message.error);
      notifyReattachError(entry, error, { retrying: message.retrying });
      if (!message.retrying) attachments.delete(message.topic);
      return;
    }

    if (message.kind === 'blob-pull') {
      blobProducers.get(message.channel)?.grant(message.credit);
      return;
    }

    if (message.kind === 'blob-chunk') {
      blobConsumers.get(message.channel)?.push(message.seq, message.data);
      return;
    }

    if (message.kind === 'blob-end') {
      blobConsumers.get(message.channel)?.end();
      blobConsumers.delete(message.channel);
      return;
    }

    if (message.kind === 'blob-error') {
      blobConsumers
        .get(message.channel)
        ?.fail(
          new WireError(message.error.code, message.error.message, { cause: message.error.cause })
        );
      blobConsumers.delete(message.channel);
      return;
    }

    if (message.kind === 'blob-close') {
      blobProducers.get(message.channel)?.close();
      blobProducers.delete(message.channel);
    }
  });

  const unsubscribeDisconnect = transport.onDisconnect(() => {
    if (disposed) return;
    if (holdsWhileDisconnected) connected = false;
    instrumentation?.transport?.({ event: 'disconnect' });
    // In-flight calls lost their peer and reject; calls held while
    // disconnected stay held until reconnect or their deadline.
    for (const [id, pendingCall] of [...pending]) {
      if (!pendingCall.posted) continue;
      pending.delete(id);
      pendingCall.cleanup();
      pendingCall.reject(new WireError('DISCONNECTED', 'Wire transport disconnected'));
    }

    for (const listener of disconnectListeners) listener();

    for (const consumer of blobConsumers.values()) {
      consumer.fail(new WireError('DISCONNECTED', 'Wire transport disconnected'));
    }
    blobConsumers.clear();
    for (const producer of blobProducers.values()) producer.close();
    blobProducers.clear();
  });

  const unsubscribeReconnect = transport.onReconnect?.(() => {
    if (disposed || terminal) return;
    connected = true;
    instrumentation?.transport?.({ event: 'reconnect' });
    const flushed = flushHeldCalls();
    if (!connected) return;
    for (const [topic, entry] of attachments) {
      // An unsettled attach just flushed from the held buffer already reached
      // the new peer; re-establishing it here would double-attach the topic.
      // Any other unsettled attach was addressed to the old peer, so a fresh
      // attempt supersedes it.
      if (
        !entry.establishedSettled &&
        entry.attachId !== undefined &&
        flushed.has(entry.attachId)
      ) {
        continue;
      }
      entry.established = establishAttachment(topic, entry, true);
    }
  });

  const unsubscribeTerminalFailure = transport.onTerminalFailure?.((cause) => {
    if (disposed || terminal) return;
    terminal = true;
    terminalCause = cause;
    connected = false;
    for (const pendingCall of pending.values()) {
      pendingCall.cleanup();
      pendingCall.reject(terminalFailureError());
    }
    pending.clear();
    heldCallIds.length = 0;

    for (const consumer of blobConsumers.values()) consumer.fail(terminalFailureError());
    blobConsumers.clear();
    for (const producer of blobProducers.values()) producer.close();
    blobProducers.clear();
  });

  function request(
    message: WireMessage & { id: string },
    options: CallOptions = {}
  ): Promise<unknown> {
    const callStart = message.kind === 'call' ? performanceNow() : undefined;
    if (message.kind === 'call') {
      instrumentation?.callStart?.({
        callId: message.id,
        path: message.path,
        input: message.input,
        side: 'client',
      });
    }
    return new Promise((resolve, reject) => {
      if (disposed) {
        reject(new WireError('DISCONNECTED', 'Wire connection disposed'));
        return;
      }
      if (terminal) {
        reject(terminalFailureError());
        return;
      }
      if (options.signal?.aborted) {
        if (message.kind === 'call') {
          instrumentation?.cancel?.({ callId: message.id, side: 'client' });
          instrumentation?.callEnd?.({
            callId: message.id,
            path: message.path,
            side: 'client',
            durationMs: 0,
            ok: false,
            errorCode: 'CANCELLED',
            errorMessage: 'Wire call cancelled',
          });
        }
        reject(new WireError('CANCELLED', 'Wire call cancelled'));
        return;
      }

      const onAbort = (): void => {
        const pendingCall = pending.get(message.id);
        if (!pendingCall) return;
        pending.delete(message.id);
        const wasPosted = pendingCall.posted;
        pendingCall.cleanup();
        if (wasPosted) {
          try {
            transport.post({ kind: 'cancel', id: message.id });
          } catch {
            // The peer may already be gone; the local call is still cancelled.
          }
        }
        if (message.kind === 'call') {
          instrumentation?.cancel?.({ callId: message.id, side: 'client' });
          instrumentation?.callEnd?.({
            callId: message.id,
            path: message.path,
            side: 'client',
            durationMs: performanceNow() - (callStart ?? performanceNow()),
            ok: false,
            errorCode: 'CANCELLED',
            errorMessage: 'Wire call cancelled',
          });
        }
        reject(new WireError('CANCELLED', 'Wire call cancelled'));
      };
      const removeAbortListener = (): void => options.signal?.removeEventListener('abort', onAbort);
      options.signal?.addEventListener('abort', onAbort, { once: true });

      const pendingCall: PendingCall = {
        message,
        resolve,
        reject,
        posted: false,
        deadline: undefined,
        cleanup() {
          removeAbortListener();
          pendingCall.deadline?.dispose();
          pendingCall.deadline = undefined;
          const heldIndex = heldCallIds.indexOf(message.id);
          if (heldIndex >= 0) heldCallIds.splice(heldIndex, 1);
        },
      };
      pending.set(message.id, pendingCall);

      const deadlineMs = deadlineFor(message, options);
      if (deadlineMs !== undefined) {
        pendingCall.deadline = clock.schedule(
          deadlineMs,
          () => expireCall(message.id, deadlineMs),
          {
            unref: true,
          }
        );
      }

      if (holdsWhileDisconnected && !connected) {
        holdCall(pendingCall);
        return;
      }
      postPendingCall(pendingCall);
    });
  }

  /**
   * The call deadline covers request/response traffic (calls and snapshots).
   * Live attach traffic is exempt (connection lifecycle and reattach own it);
   * blob uploads are exempt (credit flow and the blob idle timeout own them)
   * unless the caller overrides the deadline explicitly.
   */
  function deadlineFor(
    message: WireMessage & { id: string },
    options: CallOptions
  ): number | undefined {
    if (message.kind === 'attach') return undefined;
    if (message.kind === 'call' && message.upload && options.timeoutMs === undefined) {
      return undefined;
    }
    const timeoutMs = options.timeoutMs ?? callTimeoutMs;
    return timeoutMs > 0 ? timeoutMs : undefined;
  }

  function expireCall(id: string, deadlineMs: number): void {
    const pendingCall = pending.get(id);
    if (!pendingCall) return;
    pending.delete(id);
    const wasPosted = pendingCall.posted;
    pendingCall.cleanup();
    if (wasPosted) {
      try {
        transport.post({ kind: 'cancel', id });
      } catch {
        // The peer may already be gone; the local call still timed out.
      }
    }
    pendingCall.reject(
      new WireError(
        'TIMEOUT',
        `Wire ${describeRequest(pendingCall.message)} timed out after ${deadlineMs}ms`
      )
    );
  }

  function holdCall(pendingCall: PendingCall): void {
    if (heldCallIds.length >= maxHeldCalls) {
      pending.delete(pendingCall.message.id);
      pendingCall.cleanup();
      pendingCall.reject(
        new WireError('DISCONNECTED', 'Wire held-call buffer is full while disconnected')
      );
      return;
    }
    heldCallIds.push(pendingCall.message.id);
  }

  function postPendingCall(pendingCall: PendingCall): void {
    try {
      transport.post(pendingCall.message);
      pendingCall.posted = true;
    } catch (error) {
      if (!holdsWhileDisconnected || isStructuredCloneError(error)) {
        pending.delete(pendingCall.message.id);
        pendingCall.cleanup();
        pendingCall.reject(createPostError(pendingCall.message, error));
        return;
      }
      // The transport cannot carry messages right now; treat it as
      // disconnected and hold the call until the transport reconnects.
      connected = false;
      holdCall(pendingCall);
    }
  }

  function flushHeldCalls(): Set<string> {
    const flushed = new Set<string>();
    const ids = heldCallIds.splice(0);
    for (let index = 0; index < ids.length; index += 1) {
      const id = ids[index];
      const pendingCall = pending.get(id);
      if (!pendingCall) continue;
      try {
        transport.post(pendingCall.message);
        pendingCall.posted = true;
        flushed.add(id);
      } catch (error) {
        if (isStructuredCloneError(error)) {
          pending.delete(id);
          pendingCall.cleanup();
          pendingCall.reject(createPostError(pendingCall.message, error));
          continue;
        }
        // Went down again mid-flush: keep this call and the rest held.
        connected = false;
        heldCallIds.push(...ids.slice(index));
        return flushed;
      }
    }
    return flushed;
  }

  function terminalFailureError(): WireError {
    return new WireError('DISCONNECTED', 'Wire transport failed permanently', {
      cause: terminalCause,
    });
  }

  return {
    call(path, input, options) {
      const id = createRequestId();
      const start = performanceNow();
      return request({ kind: 'call', id, path, input, upload: options?.upload }, options).then(
        (value) => {
          instrumentation?.callEnd?.({
            callId: id,
            path,
            side: 'client',
            durationMs: performanceNow() - start,
            ok: true,
            result: value,
          });
          return value;
        },
        (error: unknown) => {
          if (error instanceof WireError && error.code === 'CANCELLED') throw error;
          instrumentation?.callEnd?.({
            callId: id,
            path,
            side: 'client',
            durationMs: performanceNow() - start,
            ok: false,
            errorCode: error instanceof WireError ? error.code : 'HANDLER_ERROR',
            errorMessage: error instanceof Error ? error.message : String(error),
          });
          throw error;
        }
      );
    },
    openBlobConsumer(channel) {
      assertActive();
      const base = createBlobConsumer({
        channel,
        post: postBlobMessage,
      });
      const wrapped: BlobConsumer = {
        ...base,
        cancel() {
          base.cancel();
          blobConsumers.delete(channel);
        },
      };
      blobConsumers.set(channel, wrapped);
      return wrapped;
    },
    openBlobProducer(channel, source) {
      assertActive();
      const producer = createBlobProducer({
        channel,
        source,
        post: postBlobMessage,
        onClose: () => blobProducers.delete(channel),
      });
      blobProducers.set(channel, producer);
      return producer;
    },
    snapshot(topic) {
      return request({ kind: 'snapshot', id: createRequestId(), topic }) as Promise<
        LiveSnapshot<unknown>
      >;
    },
    async attach(topic, push, attachOptions = {}) {
      const entry = getOrCreateAttachment(topic);
      entry.pushes.add(push);
      if (attachOptions.onReattach) entry.onReattach.add(attachOptions.onReattach);
      if (attachOptions.onReattachError) entry.onReattachError.add(attachOptions.onReattachError);

      try {
        await entry.established;
      } catch (error) {
        entry.pushes.delete(push);
        if (attachOptions.onReattach) entry.onReattach.delete(attachOptions.onReattach);
        if (attachOptions.onReattachError)
          entry.onReattachError.delete(attachOptions.onReattachError);
        throw error;
      }

      return () => {
        const current = attachments.get(topic);
        if (current !== entry) return;
        current.pushes.delete(push);
        if (attachOptions.onReattach) current.onReattach.delete(attachOptions.onReattach);
        if (attachOptions.onReattachError)
          current.onReattachError.delete(attachOptions.onReattachError);
        if (current.pushes.size > 0) return;
        attachments.delete(topic);
        try {
          transport.post({ kind: 'detach', topic });
        } catch {
          // The peer may already be disconnected; local teardown is complete.
        }
      };
    },
    onDisconnect(cb): Unsubscribe {
      if (disposed) return () => {};
      disconnectListeners.add(cb);
      return () => disconnectListeners.delete(cb);
    },
    dispose() {
      if (disposed) return;
      disposed = true;

      for (const topic of attachments.keys()) {
        try {
          transport.post({ kind: 'detach', topic });
        } catch {
          // The underlying transport may already be disconnected.
        }
      }
      attachments.clear();

      for (const pendingCall of pending.values()) {
        pendingCall.cleanup();
        pendingCall.reject(new WireError('DISCONNECTED', 'Wire connection disposed'));
      }
      pending.clear();

      for (const consumer of blobConsumers.values()) {
        consumer.fail(new WireError('DISCONNECTED', 'Wire connection disposed'));
      }
      blobConsumers.clear();
      for (const producer of blobProducers.values()) producer.close();
      blobProducers.clear();

      unsubscribeTerminalFailure?.();
      unsubscribeReconnect?.();
      unsubscribeDisconnect();
      unsubscribeMessage();
      disconnectListeners.clear();
    },
  };

  function assertActive(): void {
    if (disposed) throw new WireError('DISCONNECTED', 'Wire connection disposed');
  }

  function postBlobMessage(message: WireMessage): void {
    // Blob frames are owned by credit flow and the blob idle timeout; while a
    // reconnect-capable transport is down they are dropped, never held.
    if (holdsWhileDisconnected && !connected) return;
    try {
      transport.post(message);
    } catch (error) {
      if (holdsWhileDisconnected) {
        connected = false;
        return;
      }
      throw error;
    }
  }

  function getOrCreateAttachment(topic: string): Attachment {
    const current = attachments.get(topic);
    if (current) return current;
    const created: Attachment = {
      pushes: new Set(),
      onReattach: new Set(),
      onReattachError: new Set(),
      established: Promise.resolve(),
      establishedSettled: true,
      attempt: null,
      attachId: undefined,
    };
    attachments.set(topic, created);
    created.established = establishAttachment(topic, created, false);
    return created;
  }

  function establishAttachment(
    topic: string,
    entry: Attachment,
    notifyReattach: boolean
  ): Promise<void> {
    const attempt = {};
    entry.attempt = attempt;
    entry.establishedSettled = false;
    const staleAttachId = entry.attachId;
    const id = createRequestId();
    entry.attachId = id;
    // A superseded in-flight attach was addressed to a previous peer; drop it
    // so a stale late result can never win over this attempt.
    if (staleAttachId !== undefined) {
      const stale = pending.get(staleAttachId);
      if (stale) {
        pending.delete(staleAttachId);
        stale.cleanup();
        stale.reject(new WireError('DISCONNECTED', 'Wire attach superseded by reconnect'));
      }
    }
    const established = request({ kind: 'attach', id, topic }).then(() => {});
    established.then(
      () => {
        if (attachments.get(topic) !== entry || entry.attempt !== attempt) return;
        entry.establishedSettled = true;
        if (notifyReattach) notifyReattached(entry);
      },
      (error: unknown) => {
        if (attachments.get(topic) !== entry || entry.attempt !== attempt) return;
        entry.establishedSettled = true;
        const wireError = toWireError(error);
        if (notifyReattach) {
          const retrying = wireError.code === 'DISCONNECTED';
          notifyReattachError(entry, wireError, { retrying });
          if (!retrying) attachments.delete(topic);
          return;
        }
        attachments.delete(topic);
      }
    );
    return established;
  }

  function notifyReattached(entry: Attachment | undefined): void {
    if (!entry) return;
    for (const cb of entry.onReattach) {
      try {
        cb();
      } catch {
        // Reattach observers are best-effort and must not break the connection.
      }
    }
  }

  function notifyReattachError(
    entry: Attachment | undefined,
    error: WireError,
    context: { retrying: boolean }
  ): void {
    if (!entry) return;
    for (const cb of entry.onReattachError) {
      try {
        cb(error, context);
      } catch {
        // Reattach observers are best-effort and must not break the connection.
      }
    }
  }
}

function performanceNow(): number {
  return typeof performance !== 'undefined' ? performance.now() : Date.now();
}

function describeRequest(message: WireMessage): string {
  if (message.kind === 'call') return `call '${message.path}'`;
  if (message.kind === 'snapshot') return `snapshot '${message.topic}'`;
  return message.kind;
}

function createRequestId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `wire_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
}

function toWireError(error: unknown): WireError {
  if (error instanceof WireError) return error;
  return new WireError('HANDLER_ERROR', error instanceof Error ? error.message : String(error), {
    cause: error,
  });
}

function createPostError(message: WireMessage, error: unknown): WireError {
  if (isStructuredCloneError(error)) {
    const callContext = message.kind === 'call' ? `Wire call '${message.path}'` : 'Wire message';
    const inputFailure =
      message.kind === 'call' ? findStructuredCloneFailure(message.input, 'input') : null;
    const diagnostic = inputFailure
      ? `'${inputFailure.path}' ${inputFailure.reason}`
      : formatStructuredCloneFailure(message, 'message');
    return new WireError('SERIALIZATION', `${callContext} could not be serialized: ${diagnostic}`, {
      cause: error,
    });
  }
  return new WireError(
    'DISCONNECTED',
    error instanceof Error ? error.message : 'Wire transport disconnected',
    { cause: error }
  );
}

function wireErrorFromSerialized(error: SerializedWireError): WireError {
  return new WireError(error.code, error.message, { cause: error.cause });
}
