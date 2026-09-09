import { createManualClock } from '@emdash/shared/testing';
import { describe, expect, it, vi } from 'vitest';
import {
  ConversationHydrationReconciler,
  DEHYDRATE_RETRY_DELAY_MS,
  type ConversationSessionAdapter,
} from './conversation-hydration-reconciler';

function deferred<T = void>(): {
  promise: Promise<T>;
  resolve: (value: T | PromiseLike<T>) => void;
  reject: (reason?: unknown) => void;
} {
  let resolve: (value: T | PromiseLike<T>) => void = () => {};
  let reject: (reason?: unknown) => void = () => {};
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function makeHarness() {
  const adapter: ConversationSessionAdapter = {
    hydrateConversation: vi.fn().mockResolvedValue(undefined),
    dehydrateConversation: vi.fn().mockResolvedValue(undefined),
  };
  const logger = { warn: vi.fn() };
  const clock = createManualClock();
  const reconciler = new ConversationHydrationReconciler({
    taskId: 'task-1',
    getConversations: () => adapter,
    log: logger,
    clock,
  });
  return {
    adapter,
    logger,
    clock,
    reconciler,
    hydrateConversation: vi.mocked(adapter.hydrateConversation),
    dehydrateConversation: vi.mocked(adapter.dehydrateConversation),
  };
}

describe('ConversationHydrationReconciler', () => {
  it('hydrates desired conversations', async () => {
    const { reconciler, hydrateConversation } = makeHarness();

    reconciler.sync(['conversation-1']);
    await Promise.resolve();

    expect(hydrateConversation).toHaveBeenCalledTimes(1);
    expect(hydrateConversation).toHaveBeenCalledWith('conversation-1');
  });

  it('dedupes repeated syncs while hydrate is in flight', () => {
    const { reconciler, hydrateConversation } = makeHarness();
    hydrateConversation.mockReturnValue(deferred().promise);

    reconciler.sync(['conversation-1']);
    reconciler.sync(['conversation-1']);

    expect(hydrateConversation).toHaveBeenCalledTimes(1);
  });

  it('dehydrates when hydrate finishes after the conversation is no longer desired', async () => {
    const { reconciler, hydrateConversation, dehydrateConversation } = makeHarness();
    const hydrate = deferred();
    hydrateConversation.mockReturnValue(hydrate.promise);

    reconciler.sync(['conversation-1']);
    reconciler.sync([]);

    expect(dehydrateConversation).not.toHaveBeenCalled();

    hydrate.resolve();
    await hydrate.promise;
    await Promise.resolve();

    expect(dehydrateConversation).toHaveBeenCalledTimes(1);
    expect(dehydrateConversation).toHaveBeenCalledWith('conversation-1');
  });

  it('accepts a hydrate that finishes after close and reopen', async () => {
    const { reconciler, hydrateConversation, dehydrateConversation } = makeHarness();
    const hydrate = deferred();
    hydrateConversation.mockReturnValue(hydrate.promise);

    reconciler.sync(['conversation-1']);
    reconciler.sync([]);
    reconciler.sync(['conversation-1']);

    hydrate.resolve();
    await hydrate.promise;
    await Promise.resolve();

    expect(dehydrateConversation).not.toHaveBeenCalled();
    expect(hydrateConversation).toHaveBeenCalledTimes(1);
  });

  it('rehydrates when dehydrate finishes after the conversation is desired again', async () => {
    const { reconciler, hydrateConversation, dehydrateConversation } = makeHarness();
    const dehydrate = deferred();
    dehydrateConversation.mockReturnValueOnce(dehydrate.promise);

    reconciler.sync(['conversation-1']);
    await Promise.resolve();
    expect(hydrateConversation).toHaveBeenCalledTimes(1);

    reconciler.sync([]);
    reconciler.sync(['conversation-1']);

    dehydrate.resolve();
    await dehydrate.promise;
    await Promise.resolve();
    await Promise.resolve();

    expect(hydrateConversation).toHaveBeenCalledTimes(2);
  });

  it('does not mark as hydrated when hydrate fails', async () => {
    const { reconciler, hydrateConversation, dehydrateConversation, logger } = makeHarness();
    hydrateConversation.mockRejectedValueOnce(new Error('hydrate failed'));

    reconciler.sync(['conversation-1']);
    await Promise.resolve();
    await Promise.resolve();

    expect(logger.warn).toHaveBeenCalledTimes(1);

    reconciler.sync([]);
    await Promise.resolve();

    expect(dehydrateConversation).not.toHaveBeenCalled();
  });

  it('stops hydrated conversations on dispose', async () => {
    const { reconciler, dehydrateConversation } = makeHarness();

    reconciler.sync(['conversation-1']);
    await Promise.resolve();

    reconciler.dispose();
    await Promise.resolve();

    expect(dehydrateConversation).toHaveBeenCalledTimes(1);
    expect(dehydrateConversation).toHaveBeenCalledWith('conversation-1');
  });

  it('retries failed dehydrate once after the delay without waiting for another sync', async () => {
    const { reconciler, clock, dehydrateConversation, logger } = makeHarness();
    dehydrateConversation
      .mockRejectedValueOnce(new Error('dehydrate failed'))
      .mockResolvedValueOnce(undefined);

    reconciler.sync(['conversation-1']);
    await Promise.resolve();

    reconciler.sync([]);
    await Promise.resolve();

    expect(dehydrateConversation).toHaveBeenCalledTimes(1);
    expect(logger.warn).toHaveBeenCalledTimes(1);

    await clock.advanceBy(DEHYDRATE_RETRY_DELAY_MS - 1);
    expect(dehydrateConversation).toHaveBeenCalledTimes(1);

    await clock.advanceBy(1);
    expect(dehydrateConversation).toHaveBeenCalledTimes(2);
    expect(dehydrateConversation).toHaveBeenLastCalledWith('conversation-1');

    await clock.advanceBy(DEHYDRATE_RETRY_DELAY_MS * 2);
    expect(dehydrateConversation).toHaveBeenCalledTimes(2);
  });

  it('does not retry dehydrate when the conversation becomes desired again', async () => {
    const { reconciler, clock, dehydrateConversation } = makeHarness();
    dehydrateConversation.mockRejectedValueOnce(new Error('dehydrate failed'));

    reconciler.sync(['conversation-1']);
    await Promise.resolve();

    reconciler.sync([]);
    await Promise.resolve();
    expect(dehydrateConversation).toHaveBeenCalledTimes(1);

    reconciler.sync(['conversation-1']);

    await clock.advanceBy(DEHYDRATE_RETRY_DELAY_MS * 2);
    expect(dehydrateConversation).toHaveBeenCalledTimes(1);
  });

  it('does not retry dehydrate after dispose', async () => {
    const { reconciler, clock, dehydrateConversation } = makeHarness();
    dehydrateConversation.mockRejectedValue(new Error('dehydrate failed'));

    reconciler.sync(['conversation-1']);
    await Promise.resolve();

    reconciler.sync([]);
    await Promise.resolve();
    expect(dehydrateConversation).toHaveBeenCalledTimes(1);

    reconciler.dispose();
    await Promise.resolve();
    // dispose itself makes one last dehydrate attempt via reconcile
    expect(dehydrateConversation).toHaveBeenCalledTimes(2);

    await clock.advanceBy(DEHYDRATE_RETRY_DELAY_MS * 2);
    expect(dehydrateConversation).toHaveBeenCalledTimes(2);
  });
});
