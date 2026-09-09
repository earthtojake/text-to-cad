import { randomUUID } from 'node:crypto';
import { err, ok } from '@emdash/shared';
import type { Logger } from '@emdash/shared/logger';
import { createEventStreamHost, type EventStreamHost } from '@emdash/wire/live';
import { type LeasedLiveModelProvider } from '@emdash/wire/rpc';
import { cell, expose, peek, produce, revisionOf, type Cell } from '@emdash/wire/state';
import {
  notificationsContract,
  type AppNotification,
  type NotificationDeliveryEvent,
  type NotificationList,
  type PublishNotification,
} from '../api';
import { reduceDismiss, reduceMarkAllRead, reduceMarkRead } from '../api/optimistic';
import type { Clock, NotificationSink, NotificationStore, TimerHandle } from '../api/ports';
import { systemClock } from '../api/ports';
import type { RoutingContext, RoutingPolicy } from '../api/routing';
import { defaultRoutingPolicy } from '../api/routing';

const DEFAULT_BATCH_WINDOW_MS = 2_000;
const DEFAULT_RETENTION_MS = 14 * 24 * 60 * 60 * 1_000;
const DEFAULT_MAX_ROWS = 500;

export type NotificationServiceDeps = {
  store: NotificationStore;
  routingContext: () => Promise<RoutingContext> | RoutingContext;
  routingPolicy?: RoutingPolicy;
  clock?: Clock;
  logger?: Pick<Logger, 'warn'>;
  batchWindowMs?: number;
  retentionMs?: number;
  maxRows?: number;
};

type PendingBatch = {
  items: AppNotification[];
  timer: TimerHandle;
};

export class NotificationService {
  private readonly clock: Clock;
  private readonly routingPolicy: RoutingPolicy;
  private readonly feed: LeasedLiveModelProvider<typeof notificationsContract.feed>;
  private readonly delivery: EventStreamHost<typeof notificationsContract.delivery>;
  private readonly list: Cell<NotificationList>;
  private readonly disposers = new Set<() => void>();
  private readonly sinks = new Map<string, NotificationSink>();
  private readonly pendingBatches = new Map<string, PendingBatch>();
  private readonly seenDedupeKeys = new Map<string, string>();
  private initializePromise: Promise<void> | undefined;

  constructor(private readonly deps: NotificationServiceDeps) {
    this.clock = deps.clock ?? systemClock;
    this.routingPolicy = deps.routingPolicy ?? defaultRoutingPolicy;
    this.list = cell<NotificationList>({});
    this.feed = expose(
      notificationsContract.feed,
      {
        list: async () => {
          await this.initialize();
          return this.list;
        },
      },
      {
        mutations: {
          markRead: async (context) => {
            const revision = this.updateList((list) => reduceMarkRead(list, context.input), {
              mutationIds: [context.mutationId],
            });
            await context.observed('list', revision);
            const persisted = await this.deps.store.markRead(context.input.ids, context.input.at);
            if (!persisted.success) return err({ message: persisted.error });
            return ok<void>();
          },
          markAllRead: async (context) => {
            const revision = this.updateList((list) => reduceMarkAllRead(list, context.input), {
              mutationIds: [context.mutationId],
            });
            await context.observed('list', revision);
            const persisted = await this.deps.store.markAllRead(context.input.at);
            if (!persisted.success) return err({ message: persisted.error });
            return ok<void>();
          },
          dismiss: async (context) => {
            const revision = this.updateList((list) => reduceDismiss(list, context.input), {
              mutationIds: [context.mutationId],
            });
            await context.observed('list', revision);
            const persisted = await this.deps.store.remove(context.input.ids);
            if (!persisted.success) return err({ message: persisted.error });
            return ok<void>();
          },
        },
      }
    );
    this.delivery = createEventStreamHost(notificationsContract.delivery);
  }

  async initialize(): Promise<void> {
    this.initializePromise ??= this.initializeOnce();
    return await this.initializePromise;
  }

  private async initializeOnce(): Promise<void> {
    const now = this.clock.now();
    const retentionMs = this.deps.retentionMs ?? DEFAULT_RETENTION_MS;
    const maxRows = this.deps.maxRows ?? DEFAULT_MAX_ROWS;

    await this.prune({ olderThan: now - retentionMs, maxRows });
    const recent = await this.deps.store.loadRecent({
      since: now - retentionMs,
      maxRows,
    });
    this.list.set(
      Object.fromEntries(recent.map((notification) => [notification.id, notification]))
    );
  }

  registerSink(sink: NotificationSink): () => void {
    this.sinks.set(sink.id, sink);
    return () => this.sinks.delete(sink.id);
  }

  registerDisposer(disposer: () => void): () => void {
    this.disposers.add(disposer);
    return () => this.disposers.delete(disposer);
  }

  publish(input: PublishNotification): string {
    const deduped = input.dedupeKey ? this.seenDedupeKeys.get(input.dedupeKey) : undefined;
    if (deduped) return deduped;

    const notification: AppNotification = {
      ...input,
      id: randomUUID(),
      count: 1,
      createdAt: this.clock.now(),
      readAt: null,
    };
    if (input.dedupeKey) this.seenDedupeKeys.set(input.dedupeKey, notification.id);

    const supersededIds: string[] = [];
    this.updateList((draft) => {
      for (const existing of Object.values(draft)) {
        if (existing.groupKey === notification.groupKey && existing.readAt === null) {
          notification.count += existing.count;
          supersededIds.push(existing.id);
          delete draft[existing.id];
        }
      }
      draft[notification.id] = notification;
    });

    void this.persistInsert(notification);
    if (supersededIds.length > 0) void this.persistRemove(supersededIds);
    this.enqueueDelivery(notification);
    return notification.id;
  }

  emitDelivery(event: NotificationDeliveryEvent): void {
    this.delivery.emit(undefined, event);
  }

  feedHost(): LeasedLiveModelProvider<typeof notificationsContract.feed> {
    return this.feed;
  }

  deliveryHost(): EventStreamHost<typeof notificationsContract.delivery> {
    return this.delivery;
  }

  dispose(): void {
    for (const disposer of this.disposers) disposer();
    this.disposers.clear();
    for (const pending of this.pendingBatches.values()) this.clock.clearTimeout(pending.timer);
    this.pendingBatches.clear();
    this.sinks.clear();
    void this.feed.dispose();
    this.delivery.dispose();
  }

  snapshot(): NotificationList {
    return peek(this.list);
  }

  private updateList(
    update: (list: NotificationList) => void,
    options: { mutationIds?: readonly string[] } = {}
  ) {
    const next = produce(peek(this.list), update);
    if (Object.is(next, peek(this.list))) return revisionOf(this.list);
    return this.list.set(next, options);
  }

  private enqueueDelivery(notification: AppNotification): void {
    const pending = this.pendingBatches.get(notification.groupKey);
    if (pending) {
      pending.items.push(notification);
      return;
    }

    const timer = this.clock.setTimeout(
      () => void this.flush(notification.groupKey),
      this.deps.batchWindowMs ?? DEFAULT_BATCH_WINDOW_MS
    );
    this.pendingBatches.set(notification.groupKey, { items: [notification], timer });
  }

  private async flush(groupKey: string): Promise<void> {
    const batch = this.pendingBatches.get(groupKey);
    this.pendingBatches.delete(groupKey);
    if (!batch) return;

    const notification = batch.items[batch.items.length - 1];
    if (!notification) return;

    const context = await this.deps.routingContext();
    const decision = this.routingPolicy(notification, context);
    const summary = summarize(batch.items);
    const deliveryBatch = { notification, items: batch.items, summary };

    if (decision.system) {
      await this.sinks.get('system')?.deliver(deliveryBatch);
    }
    if (decision.sound) {
      await this.sinks.get('sound')?.deliver(deliveryBatch);
    }
  }

  private async persistInsert(notification: AppNotification): Promise<void> {
    const result = await this.deps.store.insert(notification);
    if (!result.success) {
      this.deps.logger?.warn('notifications: insert failed', { error: result.error });
    }
  }

  private async persistRemove(ids: string[]): Promise<void> {
    const result = await this.deps.store.remove(ids);
    if (!result.success) {
      this.deps.logger?.warn('notifications: remove failed', { error: result.error });
    }
  }

  private async prune(options: { olderThan: number; maxRows: number }): Promise<void> {
    const result = await this.deps.store.prune(options);
    if (!result.success) {
      this.deps.logger?.warn('notifications: prune failed', { error: result.error });
    }
  }
}

function summarize(items: AppNotification[]) {
  const latest = items[items.length - 1];
  if (!latest) return { title: '', body: '' };

  const count = items.reduce((sum, item) => sum + item.count, 0);
  if (count <= 1) return { title: latest.title, body: latest.body };
  return {
    title: latest.title,
    body: `${latest.body} (${count} notifications)`,
  };
}

export function notificationIds(list: NotificationList): string[] {
  return Object.keys(list);
}
