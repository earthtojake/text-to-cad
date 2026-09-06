import type { Result } from '@emdash/shared';
import type { AppNotification, NotificationDeliveryEvent } from './schemas';

export type NotificationSummary = {
  title: string;
  body: string;
};

export type NotificationDeliveryBatch = {
  notification: AppNotification;
  items: AppNotification[];
  summary: NotificationSummary;
};

export type NotificationSink = {
  readonly id: 'system' | 'sound' | string;
  deliver(batch: NotificationDeliveryBatch): void | Promise<void>;
};

export type NotificationStore = {
  loadRecent(options: { maxRows: number; since: number }): Promise<AppNotification[]>;
  insert(notification: AppNotification): Promise<Result<void, string>>;
  markRead(ids: string[], at: number): Promise<Result<void, string>>;
  markAllRead(at: number): Promise<Result<void, string>>;
  remove(ids: string[]): Promise<Result<void, string>>;
  prune(options: { olderThan: number; maxRows: number }): Promise<Result<void, string>>;
};

export type TimerHandle = ReturnType<typeof setTimeout>;

export type Clock = {
  now(): number;
  setTimeout(callback: () => void, ms: number): TimerHandle;
  clearTimeout(timer: TimerHandle): void;
};

export type EmitNotificationDelivery = (event: NotificationDeliveryEvent) => void;

export const systemClock: Clock = {
  now: () => Date.now(),
  setTimeout: (callback, ms) => setTimeout(callback, ms),
  clearTimeout: (timer) => clearTimeout(timer),
};
