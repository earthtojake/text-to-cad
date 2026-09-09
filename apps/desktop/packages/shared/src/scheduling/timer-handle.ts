import type { Disposable } from '../concurrency/disposable';

export interface TimerHandle extends Disposable {
  readonly active: boolean;
}
