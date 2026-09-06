import type { Unsubscribe } from '@emdash/shared';

export type EventEmitterLike = {
  on(event: string, cb: (...args: unknown[]) => void): void;
  off?(event: string, cb: (...args: unknown[]) => void): void;
  removeListener?(event: string, cb: (...args: unknown[]) => void): void;
};

export function listen(
  emitter: EventEmitterLike | undefined,
  event: string,
  cb: (...args: unknown[]) => void
): Unsubscribe {
  if (!emitter) return () => {};
  emitter.on(event, cb);
  return () => {
    emitter.off?.(event, cb);
    emitter.removeListener?.(event, cb);
  };
}
