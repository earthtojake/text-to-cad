import { createScope, type Scope } from '@emdash/shared/concurrency';
import {
  createDebounced,
  systemClock,
  type Clock,
  type TimerHandle,
} from '@emdash/shared/scheduling';
import {
  makeObservable,
  observable,
  onBecomeObserved,
  onBecomeUnobserved,
  runInAction,
} from 'mobx';

export type ResourceStrategy<T, TEventData = void> =
  | { kind: 'demand' }
  | {
      kind: 'poll';
      intervalMs: number;
      /** Pause the interval while document.hidden */
      pauseWhenHidden?: boolean;
      /**
       * Only run the interval while `data` has at least one MobX observer.
       * The initial load still runs when the first observer attaches.
       */
      demandGated?: boolean;
    }
  | {
      kind: 'event';
      /** Subscribe to an event source; return an unsubscribe function. */
      subscribe: (handler: (event: TEventData) => void) => () => void;
      /**
       * What to do when an event fires:
       *   'reload'  — call load() (with optional debounce)
       *   function  — run a custom handler inside runInAction
       */
      onEvent: 'reload' | ((event: TEventData, ctx: ResourceContext<T>) => void);
      debounceMs?: number;
    };

export interface ResourceContext<T> {
  readonly data: T | null;
  /** Trigger a fresh fetch (debounced/deduped). */
  reload(): void;
  /** Replace data with a new value inside runInAction. */
  set(newData: T): void;
  /**
   * Mutate data in-place inside runInAction.
   * Only safe when T contains MobX observable collections; otherwise MobX
   * will not detect the change — use set() for plain objects/arrays.
   */
  mutate(updater: (data: T) => void): void;
}

export class Resource<T, TEventData = void> {
  data: T | null;
  loading = false;
  error: string | undefined = undefined;
  lastUpdatedAt = 0;

  private readonly _fetch: (() => Promise<T>) | null;
  private readonly _strategies: ResourceStrategy<T, TEventData>[];
  private readonly _clock: Clock;
  private readonly _scope: Scope;
  private _inFlight: Promise<void> | null = null;
  private _reloadQueued = false;
  private readonly _ctx: ResourceContext<T>;

  constructor(
    fetch: (() => Promise<T>) | null,
    strategies: ResourceStrategy<T, TEventData>[],
    options?: {
      init?: T;
      /**
       * Track only data reference changes. Do not use ctx.mutate() with this
       * option unless T contains its own MobX observable state; in-place plain
       * object/array mutations will not notify observers. Use ctx.set() instead.
       */
      refData?: boolean;
      /** Time seam for polling, event debounce, and lastUpdatedAt (tests inject a manual clock). */
      clock?: Clock;
    }
  ) {
    this._fetch = fetch;
    this._strategies = strategies;
    this._clock = options?.clock ?? systemClock;
    this._scope = createScope({ label: 'resource', clock: this._clock });
    this.data = options?.init ?? null;

    makeObservable(this, {
      data: options?.refData ? observable.ref : observable,
      loading: observable,
      error: observable,
      lastUpdatedAt: observable,
    });

    // Build the context object once using arrow functions that capture `this`.
    this._ctx = {
      get data(): T | null {
        // Intentionally returns the resource's current data value; the getter
        // is evaluated lazily each time the handler reads ctx.data.
        return null; // overridden below
      },
      reload: () => this.invalidate(),
      set: (newData: T) => {
        runInAction(() => {
          this.data = newData;
          this.lastUpdatedAt = this._clock.now();
        });
      },
      mutate: (updater: (data: T) => void) => {
        runInAction(() => {
          if (this.data !== null) updater(this.data);
        });
      },
    };
    // Replace the placeholder getter with one that reads the live field.
    Object.defineProperty(this._ctx, 'data', {
      get: () => this.data,
      enumerable: true,
      configurable: true,
    });

    // Wire demand and demandGated strategies in the constructor so
    // onBecomeObserved fires even before start() is called.
    for (const strategy of this._strategies) {
      if (strategy.kind === 'demand') {
        onBecomeObserved(this, 'data', () => {
          void this.load();
        });
      } else if (strategy.kind === 'poll' && strategy.demandGated) {
        this._wireDemandGatedPoll(strategy);
      }
    }
  }

  /** Fetch data, deduplicating concurrent calls. */
  async load(): Promise<void> {
    if (!this._fetch) return;
    if (this._inFlight) return this._inFlight;

    runInAction(() => {
      this.loading = true;
    });

    this._inFlight = this._fetch()
      .then((data) => {
        runInAction(() => {
          this.data = data;
          this.loading = this._reloadQueued;
          this.error = undefined;
          this.lastUpdatedAt = this._clock.now();
        });
      })
      .catch((e: unknown) => {
        runInAction(() => {
          this.error = e instanceof Error ? e.message : String(e);
          this.loading = this._reloadQueued;
        });
      })
      .finally(() => {
        this._inFlight = null;
        if (this._reloadQueued) {
          this._reloadQueued = false;
          void this.load();
        }
      });

    return this._inFlight;
  }

  /** Schedule a fresh load (fire-and-forget). No-op after dispose(). */
  invalidate(): void {
    if (this._scope.disposed) return;
    if (this._inFlight) {
      this._reloadQueued = true;
      return;
    }
    void this.load();
  }

  /**
   * Directly replace data without going through the fetch function.
   * Useful for stores that manage incremental data structures (e.g. FilesStore)
   * where the caller handles the update and needs to signal MobX observers.
   */
  setValue(data: T): void {
    runInAction(() => {
      this.data = data;
      this.lastUpdatedAt = this._clock.now();
    });
  }

  /**
   * Activate non-demand strategies (poll without demandGated, event).
   * Call this from the owning store's start() / activate() method.
   * Also triggers an initial load for active strategies.
   */
  start(): void {
    for (const strategy of this._strategies) {
      if (strategy.kind === 'poll' && !strategy.demandGated) {
        this._startPoll(strategy);
        void this.load();
      } else if (strategy.kind === 'event') {
        this._startEvent(strategy);
        if (this._fetch) void this.load();
      }
    }
  }

  /** Stop all timers and unsubscribe all listeners. Idempotent. */
  dispose(): void {
    this._reloadQueued = false;
    void this._scope.dispose();
  }

  /**
   * Clock has no setInterval; emulate a repeating tick by re-arming a
   * one-shot schedule after each fire. Returns a stop function.
   */
  private _scheduleRepeating(intervalMs: number, tick: () => void): () => void {
    let handle: TimerHandle | null = null;
    const arm = (): void => {
      handle = this._clock.schedule(intervalMs, () => {
        tick();
        arm();
      });
    };
    arm();
    return () => {
      void handle?.dispose();
      handle = null;
    };
  }

  private _wireDemandGatedPoll(
    strategy: Extract<ResourceStrategy<T, TEventData>, { kind: 'poll' }>
  ): void {
    let stopTimer: (() => void) | null = null;
    let visibilityHandler: (() => void) | null = null;

    const startTimer = () => {
      if (stopTimer || this._scope.disposed) return;
      stopTimer = this._scheduleRepeating(strategy.intervalMs, () => void this.load());
    };

    const stop = () => {
      stopTimer?.();
      stopTimer = null;
    };

    const removeVisibilityHandler = () => {
      if (visibilityHandler) {
        document.removeEventListener('visibilitychange', visibilityHandler);
        visibilityHandler = null;
      }
    };

    onBecomeObserved(this, 'data', () => {
      void this.load();

      if (strategy.pauseWhenHidden) {
        if (!document.hidden) startTimer();
        visibilityHandler = () => {
          if (document.hidden) stop();
          else startTimer();
        };
        document.addEventListener('visibilitychange', visibilityHandler);
      } else {
        startTimer();
      }
    });

    onBecomeUnobserved(this, 'data', () => {
      stop();
      removeVisibilityHandler();
    });

    this._scope.add(() => {
      stop();
      removeVisibilityHandler();
    });
  }

  private _startPoll(strategy: Extract<ResourceStrategy<T, TEventData>, { kind: 'poll' }>): void {
    let stopTimer: (() => void) | null = null;

    const startTimer = () => {
      if (stopTimer || this._scope.disposed) return;
      stopTimer = this._scheduleRepeating(strategy.intervalMs, () => void this.load());
    };

    const stop = () => {
      stopTimer?.();
      stopTimer = null;
    };

    if (strategy.pauseWhenHidden) {
      if (!document.hidden) startTimer();
      const handleVisibility = () => {
        if (document.hidden) stop();
        else startTimer();
      };
      document.addEventListener('visibilitychange', handleVisibility);
      this._scope.add(() => {
        stop();
        document.removeEventListener('visibilitychange', handleVisibility);
      });
    } else {
      startTimer();
      this._scope.add(stop);
    }
  }

  private _startEvent(strategy: Extract<ResourceStrategy<T, TEventData>, { kind: 'event' }>): void {
    const debouncedReload = strategy.debounceMs
      ? createDebounced<void>(() => this.invalidate(), {
          delayMs: strategy.debounceMs,
          clock: this._clock,
        })
      : null;

    const rawHandler = (event: TEventData) => {
      // Scope cleanup crosses microtask boundaries, so the subscription can
      // still deliver events synchronously after dispose(); `disposed` flips
      // synchronously, making this guard close that window.
      if (this._scope.disposed) return;
      if (strategy.onEvent === 'reload') {
        if (debouncedReload) {
          debouncedReload.call();
        } else {
          this.invalidate();
        }
      } else {
        runInAction(() => {
          (strategy.onEvent as (event: TEventData, ctx: ResourceContext<T>) => void)(
            event,
            this._ctx
          );
        });
      }
    };

    const unsubscribe = strategy.subscribe(rawHandler);

    this._scope.add(() => {
      unsubscribe();
      debouncedReload?.cancel();
    });
  }
}
