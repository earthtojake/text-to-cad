import type { Unsubscribe } from '@emdash/shared';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import {
  retrySchedule,
  systemClock,
  type Clock,
  type RetrySchedule,
} from '@emdash/shared/scheduling';
import { WireError, type WireMessage, type WireTransport } from '../protocol';

export type ReconnectingTransportOptions = {
  backoffMs?: number[];
  clock?: Clock;
  retrySchedule?: RetrySchedule;
  /** Return false for failures, such as a protocol mismatch, that retries cannot repair. */
  shouldRetry?: (error: unknown, context: ReconnectFailureContext) => boolean;
};

export type ReconnectFailureContext = {
  /** Zero-based attempt within the current initial-connect or reconnect cycle. */
  attempt: number;
  /** True once this transport has previously reached readiness. */
  isReconnect: boolean;
};

export type ReconnectingTransport = WireTransport & {
  /** Resolves when the current physical connection has passed connectOnce readiness. */
  ready(): Promise<void>;
  onReconnect(cb: () => void): Unsubscribe;
  onTerminalFailure(cb: (error: unknown) => void): Unsubscribe;
  close(): void;
};

type Readiness = {
  promise: Promise<void>;
  settled: boolean;
  resolve(): void;
  reject(error: unknown): void;
};

/**
 * Restores connectivity with backoff and reports it — nothing more. Robustness
 * for calls issued while disconnected (holding, deadlines, overflow) is owned
 * by the Connection; this transport throws on `post` while down and signals
 * `onReconnect` on every established connection and `onTerminalFailure` when
 * reconnecting is permanently abandoned.
 */
export function reconnectingTransport(
  connectOnce: () => Promise<WireTransport>,
  options: ReconnectingTransportOptions = {}
): ReconnectingTransport {
  const clock = options.clock ?? systemClock;
  const scope: Scope = createScope({ label: 'reconnecting-transport', clock });
  const messageListeners = new Set<(message: WireMessage) => void>();
  const disconnectListeners = new Set<() => void>();
  const reconnectListeners = new Set<() => void>();
  const terminalFailureListeners = new Set<(error: unknown) => void>();
  const backoffMs = options.backoffMs ?? [100, 250, 500, 1000, 2000];
  const schedule =
    options.retrySchedule ?? retrySchedule({ delaysMs: backoffMs, repeatLast: true });
  let inner: WireTransport | null = null;
  let reconnecting = false;
  let closed = false;
  let hasConnected = false;
  let cleanupInner: Unsubscribe[] = [];
  let activeReconnect: symbol | undefined;
  let readiness = createReadiness();
  let terminal = false;
  let terminalError: unknown;

  void reconnect();

  async function reconnect(): Promise<void> {
    if (reconnecting || closed || terminal) return;
    reconnecting = true;
    const reconnectToken = Symbol('reconnect');
    activeReconnect = reconnectToken;
    let nextAttempt: Promise<WireTransport> | undefined = startConnectAttempt();
    nextAttempt.then(
      (next) => {
        if (closed) next.close?.();
      },
      () => {}
    );
    const run = scope.run('reconnect', async (signal) => {
      let attempt = 0;
      while (!closed && !signal.aborted) {
        try {
          const pending = nextAttempt ?? startConnectAttempt();
          nextAttempt = undefined;
          const next = await pending;
          if (closed || signal.aborted) {
            next.close?.();
            break;
          }
          setInner(next);
          reconnecting = false;
          activeReconnect = undefined;
          if (inner !== next || closed) return;
          hasConnected = true;
          readiness.resolve();
          notifyReconnect();
          return;
        } catch (error) {
          if (closed || signal.aborted) break;
          const context = { attempt, isReconnect: hasConnected } satisfies ReconnectFailureContext;
          let delay: number | undefined;
          try {
            if (options.shouldRetry && !options.shouldRetry(error, context)) {
              failPermanently(error);
              break;
            }
            delay = schedule.delayFor(attempt);
          } catch (classificationError) {
            failPermanently(classificationError);
            break;
          }
          if (delay === undefined) {
            failPermanently(error);
            break;
          }
          attempt += 1;
          await clock.sleep(delay, { signal, unref: true });
        }
      }
    });
    await run.exit;
    if (activeReconnect === reconnectToken) {
      reconnecting = false;
      activeReconnect = undefined;
    }
  }

  function startConnectAttempt(): Promise<WireTransport> {
    try {
      return Promise.resolve(connectOnce());
    } catch (error) {
      return Promise.reject(error);
    }
  }

  function setInner(next: WireTransport): void {
    for (const cleanup of cleanupInner) cleanup();
    cleanupInner = [];
    inner = next;
    cleanupInner.push(
      next.onMessage((message) => {
        for (const listener of messageListeners) listener(message);
      })
    );
    cleanupInner.push(
      next.onDisconnect(() => {
        if (inner !== next) return;
        inner = null;
        resetReadiness();
        for (const listener of disconnectListeners) listener();
        if (!closed) void reconnect();
      })
    );
  }

  function notifyReconnect(): void {
    for (const listener of reconnectListeners) listener();
  }

  function failPermanently(error: unknown): void {
    terminal = true;
    terminalError = error;
    readiness.reject(error);
    for (const listener of terminalFailureListeners) listener(error);
  }

  function resetReadiness(): void {
    if (!readiness.settled) return;
    readiness = createReadiness();
  }

  return {
    post(message) {
      if (closed) throw new WireError('DISCONNECTED', 'Reconnecting transport closed');
      if (terminal) {
        throw new WireError('DISCONNECTED', 'Reconnecting transport failed permanently', {
          cause: terminalError,
        });
      }
      const current = inner;
      if (!current) {
        void reconnect();
        throw new WireError('DISCONNECTED', 'Reconnecting transport is not connected');
      }
      try {
        current.post(message);
      } catch (error) {
        if (inner === current) {
          inner = null;
          resetReadiness();
          for (const listener of disconnectListeners) listener();
          if (!closed) void reconnect();
        }
        throw error;
      }
    },
    onMessage(cb): Unsubscribe {
      messageListeners.add(cb);
      return () => messageListeners.delete(cb);
    },
    onDisconnect(cb): Unsubscribe {
      disconnectListeners.add(cb);
      return () => disconnectListeners.delete(cb);
    },
    onReconnect(cb): Unsubscribe {
      reconnectListeners.add(cb);
      return () => reconnectListeners.delete(cb);
    },
    onTerminalFailure(cb): Unsubscribe {
      if (terminal) cb(terminalError);
      terminalFailureListeners.add(cb);
      return () => terminalFailureListeners.delete(cb);
    },
    ready() {
      if (closed) return Promise.reject(new Error('Wire transport closed'));
      return readiness.promise;
    },
    close() {
      if (closed) return;
      closed = true;
      const closeError = new Error('Reconnecting transport closed');
      void scope.dispose(closeError);
      for (const cleanup of cleanupInner.splice(0)) cleanup();
      inner?.close?.();
      inner = null;
      readiness.reject(closeError);
      for (const listener of terminalFailureListeners) listener(closeError);
      messageListeners.clear();
      disconnectListeners.clear();
      reconnectListeners.clear();
      terminalFailureListeners.clear();
    },
  };
}

function createReadiness(): Readiness {
  let resolvePromise!: () => void;
  let rejectPromise!: (error: unknown) => void;
  const readiness: Readiness = {
    promise: Promise.resolve(),
    settled: false,
    resolve() {
      if (readiness.settled) return;
      readiness.settled = true;
      resolvePromise();
    },
    reject(error) {
      if (readiness.settled) return;
      readiness.settled = true;
      rejectPromise(error);
    },
  };
  readiness.promise = new Promise<void>((resolve, reject) => {
    resolvePromise = resolve;
    rejectPromise = reject;
  });
  void readiness.promise.catch(() => {});
  return readiness;
}
