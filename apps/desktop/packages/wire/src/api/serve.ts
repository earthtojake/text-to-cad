import { toSerializedError, type Unsubscribe } from '@emdash/shared';
import { getCurrentLogger, runWithLogger, type Logger } from '@emdash/shared/logger';
import {
  createBlobConsumer,
  createBlobProducer,
  createWireFile,
  type BlobConsumer,
  type BlobProducer,
} from './blob-channel';
import { isDownloadFileOpenResult } from './blob-channel';
import type { Controller } from './controller';
import type { WireInstrumentation } from './instrumentation';
import { serializeWireError, WireError, type WireMessage, type WireTransport } from './protocol';
import { formatStructuredCloneFailure, isStructuredCloneError } from './structured-clone';

export type ServeOptions = {
  instrumentation?: WireInstrumentation;
  logger?: Logger;
};

type ServerAttachment = {
  ready: Promise<void>;
  unsubscribe?: Unsubscribe;
  release: () => Promise<void>;
  disposed: boolean;
};

type PostAttempt = { ok: true } | { ok: false; error: unknown };

export function serve(
  transport: WireTransport,
  controller: Controller,
  options: ServeOptions = {}
): Unsubscribe {
  const attached = new Map<string, ServerAttachment>();
  const calls = new Map<string, AbortController>();
  const blobProducers = new Map<string, BlobProducer>();
  const blobConsumers = new Map<string, BlobConsumer>();
  const instrumentation = options.instrumentation;

  function tryPost(message: WireMessage): PostAttempt {
    try {
      transport.post(message);
      return { ok: true };
    } catch (error) {
      return { ok: false, error };
    }
  }

  function post(message: WireMessage): void {
    tryPost(message);
  }

  function postSuccessfulResult(
    id: string,
    value: unknown,
    context: string
  ): ReturnType<typeof serializeWireError> | undefined {
    const attempt = tryPost({ kind: 'result', id, ok: true, value });
    if (attempt.ok || !isStructuredCloneError(attempt.error)) return undefined;

    const serialized = serializeWireError(
      new WireError(
        'SERIALIZATION',
        `Wire response for ${context} could not be serialized: ${formatStructuredCloneFailure(
          value,
          'value'
        )}`,
        { cause: attempt.error }
      )
    );
    post({ kind: 'result', id, ok: false, ...serialized });
    return serialized;
  }

  function replyRequest(
    id: string,
    context: string,
    work: (signal: AbortSignal) => Promise<unknown> | unknown,
    onEnd?: (event: {
      durationMs: number;
      ok: boolean;
      value?: unknown;
      errorCode?: string;
      errorMessage?: string;
    }) => void
  ): void {
    const abort = new AbortController();
    calls.set(id, abort);
    const start = performanceNow();
    let result: Promise<unknown>;
    try {
      result = Promise.resolve(work(abort.signal));
    } catch (error) {
      result = Promise.reject(error);
    }
    result
      .then(
        (value) => {
          let responseValue = value;
          let downloadChannel: string | undefined;
          if (isDownloadFileOpenResult(value)) {
            const channel = createChannelId();
            downloadChannel = channel;
            blobProducers.set(
              channel,
              createBlobProducer({
                channel,
                source: value.data.source,
                post,
                onClose: () => blobProducers.delete(channel),
              })
            );
            responseValue = { success: true, data: { meta: value.data.meta, channel } };
          }
          const serializationError = postSuccessfulResult(id, responseValue, context);
          if (serializationError) {
            if (downloadChannel) {
              blobProducers.get(downloadChannel)?.close();
              blobProducers.delete(downloadChannel);
            }
            onEnd?.({
              durationMs: performanceNow() - start,
              ok: false,
              errorCode: serializationError.code,
              errorMessage: serializationError.message,
            });
          } else {
            onEnd?.({
              durationMs: performanceNow() - start,
              ok: true,
              value,
            });
          }
        },
        (error: unknown) => {
          const serialized = abort.signal.aborted
            ? {
                code: 'CANCELLED' as const,
                message: 'Wire call cancelled',
                cause: error === undefined ? undefined : toSerializedError(error),
              }
            : serializeWireError(error);
          onEnd?.({
            durationMs: performanceNow() - start,
            ok: false,
            errorCode: serialized.code,
            errorMessage: serialized.message,
          });
          post({ kind: 'result', id, ok: false, ...serialized });
        }
      )
      .finally(() => {
        calls.delete(id);
      });
  }

  function replyControllerCallWithUpload(
    id: string,
    path: string,
    input: unknown,
    upload?: { channel: string; meta: Record<string, unknown> }
  ): void {
    instrumentation?.callStart?.({ callId: id, path, input, side: 'server' });
    const logger = options.logger ?? getCurrentLogger();
    const uploadConsumer = upload
      ? createBlobConsumer({ channel: upload.channel, post })
      : undefined;
    if (uploadConsumer) blobConsumers.set(uploadConsumer.channel, uploadConsumer);
    replyRequest(
      id,
      `call '${path}'`,
      async (signal) => {
        try {
          return await runWithLogger(logger.child({ wireCallId: id, wirePath: path }), () =>
            controller.call(path, input, {
              signal,
              uploadFile: uploadConsumer
                ? createWireFile(upload?.meta as never, uploadConsumer)
                : undefined,
            })
          );
        } finally {
          if (uploadConsumer && blobConsumers.has(uploadConsumer.channel)) {
            blobConsumers.delete(uploadConsumer.channel);
            uploadConsumer.cancel();
          }
        }
      },
      (event) =>
        instrumentation?.callEnd?.({
          callId: id,
          path,
          side: 'server',
          durationMs: event.durationMs,
          ok: event.ok,
          result: event.value,
          errorCode: event.errorCode,
          errorMessage: event.errorMessage,
        })
    );
  }

  function replySnapshot(id: string, topic: string): void {
    const start = performanceNow();
    replyRequest(id, `snapshot '${topic}'`, async (signal) => {
      if (signal.aborted) throw new WireError('CANCELLED', 'Wire snapshot cancelled');
      try {
        const lease = requireLiveLease(controller, topic);
        try {
          const source = await lease.ready();
          const snapshot = await source.snapshot();
          instrumentation?.snapshot?.({
            requestId: id,
            topic,
            durationMs: performanceNow() - start,
            ok: true,
          });
          return snapshot;
        } finally {
          await lease.release();
        }
      } catch (error) {
        instrumentation?.snapshot?.({
          requestId: id,
          topic,
          durationMs: performanceNow() - start,
          ok: false,
          errorCode: error instanceof WireError ? error.code : 'HANDLER_ERROR',
        });
        throw error;
      }
    });
  }

  function detachAll(): void {
    for (const attachment of attached.values()) disposeAttachment(attachment);
    attached.clear();
  }

  function disposeAttachment(attachment: ServerAttachment): void {
    if (attachment.disposed) return;
    attachment.disposed = true;
    attachment.unsubscribe?.();
    // Release is fire-and-forget; a rejection here must never escape as an
    // unhandled rejection (fatal in the Electron main process).
    void attachment.release().catch((error: unknown) => {
      const logger = options.logger ?? getCurrentLogger();
      logger.warn('Wire attachment release failed', { error: toSerializedError(error) });
    });
  }

  function closeAllBlobChannels(): void {
    for (const producer of blobProducers.values()) producer.close();
    blobProducers.clear();
    for (const consumer of blobConsumers.values()) {
      consumer.fail(new WireError('DISCONNECTED', 'Wire transport disconnected'));
      consumer.cancel();
    }
    blobConsumers.clear();
  }

  function abortAll(): void {
    for (const abort of calls.values()) abort.abort();
    calls.clear();
  }

  function handleMessage(message: WireMessage): void {
    switch (message.kind) {
      case 'call':
        replyControllerCallWithUpload(message.id, message.path, message.input, message.upload);
        break;
      case 'snapshot':
        replySnapshot(message.id, message.topic);
        break;
      case 'attach':
        replyRequest(message.id, `attach '${message.topic}'`, async (signal) => {
          if (signal.aborted) throw new WireError('CANCELLED', 'Wire attach cancelled');
          const existing = attached.get(message.topic);
          if (existing) {
            await existing.ready;
            if (signal.aborted) throw new WireError('CANCELLED', 'Wire attach cancelled');
            return undefined;
          }
          const lease = requireLiveLease(controller, message.topic);
          const attachment: ServerAttachment = {
            ready: Promise.resolve(),
            release: lease.release,
            disposed: false,
          };
          attached.set(message.topic, attachment);
          attachment.ready = (async () => {
            try {
              const source = await lease.ready();
              if (
                attachment.disposed ||
                signal.aborted ||
                attached.get(message.topic) !== attachment
              ) {
                return;
              }

              const unsubscribe = await source.subscribe(
                (update) => post({ kind: 'update', topic: message.topic, update }),
                {
                  onGap: () => post({ kind: 'topic-gap', topic: message.topic }),
                  onError: (error, context) => {
                    post({
                      kind: 'topic-error',
                      topic: message.topic,
                      error: serializeWireError(error),
                      retrying: context.retrying,
                    });
                    if (!context.retrying && attached.get(message.topic) === attachment) {
                      attached.delete(message.topic);
                      disposeAttachment(attachment);
                    }
                  },
                }
              );
              if (
                attachment.disposed ||
                signal.aborted ||
                attached.get(message.topic) !== attachment
              ) {
                unsubscribe();
                return;
              }
              attachment.unsubscribe = unsubscribe;
              instrumentation?.topicAttach?.({
                topic: message.topic,
                attachmentCount: attached.size,
              });
            } catch (error) {
              if (attached.get(message.topic) === attachment) attached.delete(message.topic);
              disposeAttachment(attachment);
              throw error;
            }
          })();
          await attachment.ready;
          if (signal.aborted) {
            if (attached.get(message.topic) === attachment) attached.delete(message.topic);
            disposeAttachment(attachment);
            throw new WireError('CANCELLED', 'Wire attach cancelled');
          }
          return undefined;
        });
        break;
      case 'detach':
        {
          const attachment = attached.get(message.topic);
          if (attachment) {
            attached.delete(message.topic);
            disposeAttachment(attachment);
          }
        }
        instrumentation?.topicDetach?.({
          topic: message.topic,
          attachmentCount: attached.size,
        });
        break;
      case 'cancel':
        instrumentation?.cancel?.({ callId: message.id, side: 'server' });
        calls.get(message.id)?.abort();
        break;
      case 'blob-pull':
        blobProducers.get(message.channel)?.grant(message.credit);
        break;
      case 'blob-chunk':
        blobConsumers.get(message.channel)?.push(message.seq, message.data);
        break;
      case 'blob-end':
        blobConsumers.get(message.channel)?.end();
        blobConsumers.delete(message.channel);
        break;
      case 'blob-error':
        blobConsumers
          .get(message.channel)
          ?.fail(
            new WireError(message.error.code, message.error.message, { cause: message.error.cause })
          );
        blobConsumers.delete(message.channel);
        break;
      case 'blob-close':
        blobProducers.get(message.channel)?.close();
        blobProducers.delete(message.channel);
        blobConsumers
          .get(message.channel)
          ?.fail(new WireError('CANCELLED', 'Blob channel closed by peer'));
        blobConsumers.delete(message.channel);
        break;
      case 'result':
      case 'update':
      case 'topic-gap':
      case 'topic-error':
        break;
    }
  }

  const unsubscribeMessage = transport.onMessage(handleMessage);
  const unsubscribeDisconnect = transport.onDisconnect(() => {
    abortAll();
    detachAll();
    closeAllBlobChannels();
  });

  return () => {
    unsubscribeMessage();
    unsubscribeDisconnect();
    abortAll();
    detachAll();
    closeAllBlobChannels();
  };
}

function performanceNow(): number {
  return typeof performance !== 'undefined' ? performance.now() : Date.now();
}

function createChannelId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `blob_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
}

function requireLiveLease(controller: Controller, topic: string) {
  const lease = controller.acquireLive(topic);
  if (!lease) throw new WireError('UNKNOWN_TOPIC', `Unknown live topic '${topic}'`);
  return lease;
}
