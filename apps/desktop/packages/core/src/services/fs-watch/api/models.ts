import type { Result } from '@emdash/shared';

export type WatchEventKind = 'create' | 'update' | 'delete';

export type WatchEvent = {
  kind: WatchEventKind;
  path: string;
};

export type WatchOptions = {
  /**
   * Native-level ignore globs, a property of the shared root subscription: consumers watching
   * the same root should agree on the ignore set to share one native watcher (different sets
   * create separate subscriptions). Relevance filtering beyond ignores belongs in consumers.
   */
  ignore?: string[];
  debounceMs?: number;
  /**
   * Called when the native watcher cannot be attached. This is a best-effort notification;
   * callers that require a live subscription should check the handle's ready result.
   */
  onError?: (error: unknown) => void;
  /**
   * Called when the native watcher reports an event gap, after a native resubscribe, or after a
   * subprocess-backed watcher reconnects. Events may have been lost; consumers should treat all
   * derived state as stale and resync.
   */
  onResync?: () => void;
};

export type WatchHandle = {
  ready(): Promise<Result<void, unknown>>;
  release(): Promise<void>;
};

export async function requireWatchReady(handle: WatchHandle): Promise<void> {
  const attached = await handle.ready();
  if (!attached.success) throw attached.error;
}

export type IWatchService = {
  watch(
    root: string,
    onEvents: (events: WatchEvent[]) => void,
    options?: WatchOptions
  ): WatchHandle;
  dispose(): Promise<void>;
};
