import { ok } from '@emdash/shared';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AppNotification, PublishNotification } from '../api';
import type { Clock, NotificationStore, TimerHandle } from '../api/ports';
import { NotificationService } from './notification-service';

class MemoryNotificationStore implements NotificationStore {
  readonly rows = new Map<string, AppNotification>();

  constructor(initial: AppNotification[] = []) {
    for (const notification of initial) this.rows.set(notification.id, notification);
  }

  async loadRecent(options: { maxRows: number; since: number }) {
    return [...this.rows.values()]
      .filter((notification) => notification.createdAt >= options.since)
      .sort((a, b) => b.createdAt - a.createdAt)
      .slice(0, options.maxRows);
  }

  async insert(notification: AppNotification) {
    this.rows.set(notification.id, notification);
    return ok<void>();
  }

  async markRead(ids: string[], at: number) {
    for (const id of ids) {
      const notification = this.rows.get(id);
      if (notification) this.rows.set(id, { ...notification, readAt: at });
    }
    return ok<void>();
  }

  async markAllRead(at: number) {
    for (const [id, notification] of this.rows) {
      this.rows.set(id, { ...notification, readAt: at });
    }
    return ok<void>();
  }

  async remove(ids: string[]) {
    for (const id of ids) this.rows.delete(id);
    return ok<void>();
  }

  async prune() {
    return ok<void>();
  }
}

class ManualClock implements Clock {
  private nextId = 1;
  private readonly timers = new Map<number, () => void>();
  time = 1_000;

  now() {
    return this.time;
  }

  setTimeout(callback: () => void): TimerHandle {
    const id = this.nextId++;
    this.timers.set(id, callback);
    return id as unknown as TimerHandle;
  }

  clearTimeout(timer: TimerHandle): void {
    this.timers.delete(timer as unknown as number);
  }

  runAll(): void {
    const callbacks = [...this.timers.values()];
    this.timers.clear();
    for (const callback of callbacks) callback();
  }
}

function input(overrides: Partial<PublishNotification> = {}): PublishNotification {
  return {
    kind: 'agent-attention',
    groupKey: 'conversation:1',
    title: 'Codex - Task',
    body: 'Your agent is waiting for input',
    sound: 'needs_attention',
    target: { kind: 'task', projectId: 'project-1', taskId: 'task-1', conversationId: 'conv-1' },
    source: {
      kind: 'conversation',
      projectId: 'project-1',
      taskId: 'task-1',
      conversationId: 'conv-1',
    },
    ...overrides,
  };
}

function feed(service: NotificationService) {
  return service.snapshot();
}

describe('NotificationService', () => {
  let service: NotificationService | null = null;

  afterEach(() => {
    service?.dispose();
    service = null;
  });

  it('dedupes duplicate publish requests and collapses unread group entries', () => {
    const clock = new ManualClock();
    service = new NotificationService({
      store: new MemoryNotificationStore(),
      clock,
      routingContext: routingContext,
    });

    const firstId = service.publish(input({ dedupeKey: 'one' }));
    const duplicateId = service.publish(input({ dedupeKey: 'one' }));
    const secondId = service.publish(input({ dedupeKey: 'two' }));

    expect(duplicateId).toBe(firstId);
    expect(secondId).not.toBe(firstId);

    const list = feed(service);
    expect(Object.keys(list)).toEqual([secondId]);
    expect(list[secondId]?.count).toBe(2);
  });

  it('hydrates recent notifications without delivering them', async () => {
    const clock = new ManualClock();
    const existing: AppNotification = {
      ...input(),
      id: 'existing',
      count: 1,
      createdAt: clock.now(),
      readAt: null,
    };
    const sink = { id: 'system', deliver: vi.fn() };
    service = new NotificationService({
      store: new MemoryNotificationStore([existing]),
      clock,
      routingContext: routingContext,
    });
    service.registerSink(sink);

    await service.initialize();
    expect(feed(service).existing).toEqual(existing);
    expect(sink.deliver).not.toHaveBeenCalled();
  });

  it('routes flushed batches to registered sinks', async () => {
    const clock = new ManualClock();
    const systemSink = { id: 'system', deliver: vi.fn() };
    const soundSink = { id: 'sound', deliver: vi.fn() };
    service = new NotificationService({
      store: new MemoryNotificationStore(),
      clock,
      routingContext: routingContext,
      batchWindowMs: 1,
    });
    service.registerSink(systemSink);
    service.registerSink(soundSink);

    const id = service.publish(input());
    clock.runAll();

    await vi.waitFor(() =>
      expect(systemSink.deliver).toHaveBeenCalledWith(
        expect.objectContaining({ notification: expect.objectContaining({ id }) })
      )
    );
    await vi.waitFor(() =>
      expect(soundSink.deliver).toHaveBeenCalledWith(
        expect.objectContaining({ notification: expect.objectContaining({ id }) })
      )
    );
  });

  it('emits delivery stream events', () => {
    service = new NotificationService({
      store: new MemoryNotificationStore(),
      routingContext: routingContext,
    });
    const events: unknown[] = [];
    const unsubscribe = service
      .deliveryHost()
      .resolve(undefined)
      .subscribe((update) => {
        if (typeof update.delta === 'object' && update.delta !== null && 'event' in update.delta) {
          events.push(update.delta.event);
        }
      });

    service.emitDelivery({ type: 'sound', sound: 'needs_attention', notificationId: 'n-1' });
    unsubscribe();

    expect(events).toEqual([{ type: 'sound', sound: 'needs_attention', notificationId: 'n-1' }]);
  });
});

function routingContext() {
  return {
    appFocused: false,
    settings: {
      enabled: true,
      sound: true,
      osNotifications: true,
      soundFocusMode: 'always' as const,
    },
  };
}
