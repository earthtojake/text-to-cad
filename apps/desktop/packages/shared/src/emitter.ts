import type { Unsubscribe } from './lifecycle';
import { log } from './logger';

export type EmitterSubscriberError = {
  error: unknown;
};

export type EmitterOptions = {
  onSubscriberError?: (event: EmitterSubscriberError) => void;
};

export interface Emitter<T> {
  readonly size: number;
  subscribe(cb: (value: T) => void): Unsubscribe;
  emit(value: T): void;
  clear(): void;
}

class EmitterImpl<T> implements Emitter<T> {
  private readonly subscribers = new Set<(value: T) => void>();

  constructor(private readonly options: EmitterOptions = {}) {}

  get size(): number {
    return this.subscribers.size;
  }

  subscribe(cb: (value: T) => void): Unsubscribe {
    this.subscribers.add(cb);
    return () => {
      this.subscribers.delete(cb);
    };
  }

  emit(value: T): void {
    for (const subscriber of [...this.subscribers]) {
      try {
        subscriber(value);
      } catch (error) {
        this.reportSubscriberError(error);
      }
    }
  }

  clear(): void {
    this.subscribers.clear();
  }

  private reportSubscriberError(error: unknown): void {
    try {
      if (this.options.onSubscriberError) {
        this.options.onSubscriberError({ error });
        return;
      }
      log.warn('emitter subscriber failed', { error });
    } catch {
      // Subscriber error reporting must not affect event delivery.
    }
  }
}

export function createEmitter<T>(options: EmitterOptions = {}): Emitter<T> {
  return new EmitterImpl<T>(options);
}
