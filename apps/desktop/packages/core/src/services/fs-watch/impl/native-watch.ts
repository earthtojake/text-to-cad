import fs from 'node:fs/promises';
import type { Disposable } from '@emdash/shared/concurrency';
import parcelWatcher from '@parcel/watcher';
import type { WatchEvent } from '#services/fs-watch/api';

const RESUBSCRIBE_DELAY_MS = 250;
const MAX_RESUBSCRIBE_DELAY_MS = 30_000;
const RESYNC_DELAY_MS = 250;

export type ParcelSubscribeFn = typeof parcelWatcher.subscribe;

/**
 * One native subscription per (root, ignore set), shared across consumers.
 * Owns event-gap recovery and serialized resubscribe-with-retry; signals resync whenever events
 * may have been lost.
 */
export class NativeWatch implements Disposable {
  readonly root: string;
  readonly ignore: string[];
  private readonly deliver: (events: WatchEvent[]) => void;
  private readonly resync: () => void;
  private readonly onError: (context: string, error: unknown) => void;
  private readonly subscribeFn: ParcelSubscribeFn;
  private subscription: Promise<parcelWatcher.AsyncSubscription> | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private resyncTimer: ReturnType<typeof setTimeout> | null = null;
  private restartPromise: Promise<void> | null = null;
  private generation = 0;
  private activeGeneration = 0;
  private retryRequested = false;
  private retryAttempts = 0;
  private disposed = false;

  constructor(
    root: string,
    ignore: string[],
    deliver: (events: WatchEvent[]) => void,
    resync: () => void,
    onError: (context: string, error: unknown) => void,
    subscribeFn: ParcelSubscribeFn = parcelWatcher.subscribe
  ) {
    this.root = root;
    this.ignore = ignore;
    this.deliver = deliver;
    this.resync = resync;
    this.onError = onError;
    this.subscribeFn = subscribeFn;
    this.subscription = this.subscribe();
    this.subscription.catch(() => {});
  }

  async ready(): Promise<void> {
    if (!this.subscription) throw new Error(`Watcher is not subscribed for ${this.root}`);
    await this.subscription;
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    this.activeGeneration = 0;
    this.retryRequested = false;
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = null;
    if (this.resyncTimer) clearTimeout(this.resyncTimer);
    this.resyncTimer = null;
    await this.restartPromise;
    const subscription = await this.subscription?.catch(() => null);
    this.subscription = null;
    await subscription?.unsubscribe();
  }

  private async subscribe(): Promise<parcelWatcher.AsyncSubscription> {
    await fs.stat(this.root);
    const generation = ++this.generation;
    this.activeGeneration = generation;
    return this.subscribeFn(
      this.root,
      (err, events) => {
        if (this.disposed || generation !== this.activeGeneration) return;
        if (err) {
          this.onError(`watch ${this.root}`, err);
          if (requiresResync(err)) {
            this.scheduleResync();
            return;
          }
          if (this.restartPromise) {
            this.retryRequested = true;
            return;
          }
          this.scheduleResubscribe();
          return;
        }
        if (events.length === 0) return;
        this.deliver(events.map(toWatchEvent));
      },
      { ignore: this.ignore }
    );
  }

  private scheduleResync(): void {
    if (this.resyncTimer || this.disposed) return;
    this.resyncTimer = setTimeout(() => {
      this.resyncTimer = null;
      this.signalResync();
    }, RESYNC_DELAY_MS);
  }

  private signalResync(): void {
    if (this.disposed) return;
    try {
      this.resync();
    } catch (error) {
      this.onError(`resync ${this.root}`, error);
    }
  }

  private scheduleResubscribe(): void {
    if (this.retryTimer || this.disposed) return;
    if (this.restartPromise) {
      this.retryRequested = true;
      return;
    }
    const delay = Math.min(
      RESUBSCRIBE_DELAY_MS * 2 ** this.retryAttempts,
      MAX_RESUBSCRIBE_DELAY_MS
    );
    this.retryAttempts += 1;
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      if (this.disposed) return;
      const restart = this.restart();
      const tracked = restart.then((shouldRetry) => {
        const retry = shouldRetry || this.retryRequested;
        this.retryRequested = false;
        if (this.restartPromise === tracked) this.restartPromise = null;
        if (retry) this.scheduleResubscribe();
      });
      this.restartPromise = tracked;
      void tracked;
    }, delay);
  }

  private async restart(): Promise<boolean> {
    const previousPromise = this.subscription;
    const previousGeneration = this.activeGeneration;
    this.activeGeneration = 0;
    const previous = await previousPromise?.catch(() => null);
    if (this.disposed) return false;

    try {
      await previous?.unsubscribe();
    } catch (error) {
      this.onError(`unsubscribe ${this.root}`, error);
      if (!this.disposed && this.subscription === previousPromise) {
        this.activeGeneration = previousGeneration;
        this.scheduleResync();
      }
      return !this.disposed;
    }
    if (this.subscription === previousPromise) this.subscription = null;
    if (this.disposed) return false;

    const next = this.subscribe();
    this.subscription = next;
    try {
      await next;
    } catch (error) {
      this.onError(`resubscribe ${this.root}`, error);
      return true;
    }
    this.retryAttempts = 0;
    if (this.disposed) return false;
    this.signalResync();
    return false;
  }
}

/**
 * Matches the FSEvents dropped-events error emitted by @parcel/watcher.
 * Keep this in sync with the upstream message; Parcel exposes no structured error code.
 */
function requiresResync(error: Error): boolean {
  return error.message.includes('File system must be re-scanned');
}

function toWatchEvent(event: parcelWatcher.Event): WatchEvent {
  return {
    kind: event.type,
    path: event.path,
  };
}
