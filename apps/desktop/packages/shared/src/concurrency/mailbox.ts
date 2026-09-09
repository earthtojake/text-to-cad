import { abortableWait } from '../scheduling';
import {
  createBoundedBuffer,
  type BoundedBuffer,
  type BoundedBufferOverflow,
} from './bounded-buffer';
import type { Disposable } from './disposable';

export type MailboxOverflow = 'suspend' | 'reject' | 'drop-oldest' | 'drop-newest';
export type MailboxState = 'open' | 'closing' | 'closed' | 'failed';

export type MailboxOfferResult<T> =
  | { kind: 'accepted' }
  | { kind: 'accepted'; dropped: T }
  | { kind: 'dropped'; value: T }
  | { kind: 'full' }
  | { kind: 'closed' };

export type CreateMailboxOptions<T> = {
  capacity: number;
  overflow?: MailboxOverflow;
  onDrop?: (value: T) => void;
};

export interface Mailbox<T> extends AsyncIterable<T>, Disposable {
  readonly state: MailboxState;
  readonly size: number;
  readonly capacity: number;
  tryOffer(value: T): MailboxOfferResult<T>;
  offer(value: T, options?: { signal?: AbortSignal }): Promise<MailboxOfferResult<T>>;
  take(options?: { signal?: AbortSignal }): Promise<T>;
  tryTake(): T | undefined;
  drain(limit?: number): T[];
  close(): void;
  fail(error: unknown): void;
  dispose(): void;
}

type PendingTake<T> = {
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
};

type PendingOffer<T> = {
  value: T;
  resolve: (result: MailboxOfferResult<T>) => void;
  reject: (error: unknown) => void;
};

export class MailboxClosedError extends Error {
  constructor(message = 'Mailbox is closed') {
    super(message);
    this.name = 'MailboxClosedError';
  }
}

export class MailboxConsumerError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'MailboxConsumerError';
  }
}

export function createMailbox<T>(options: CreateMailboxOptions<T>): Mailbox<T> {
  return new MailboxImpl(options);
}

class MailboxImpl<T> implements Mailbox<T> {
  private readonly buffer: BoundedBuffer<T>;
  private readonly overflow: MailboxOverflow;
  private readonly suspendedOffers: PendingOffer<T>[] = [];
  private stateValue: MailboxState = 'open';
  private pendingTake: PendingTake<T> | undefined;
  private failure: unknown;
  private iteratorActive = false;

  constructor(options: CreateMailboxOptions<T>) {
    const capacity = Math.floor(options.capacity);
    if (!Number.isFinite(capacity) || capacity <= 0) {
      throw new Error('Mailbox capacity must be a positive finite number');
    }
    this.overflow = options.overflow ?? 'suspend';
    this.buffer = createBoundedBuffer<T>({
      capacity,
      overflow: mailboxOverflowToBufferOverflow(this.overflow),
      onDrop: options.onDrop,
    });
  }

  get state(): MailboxState {
    return this.stateValue;
  }

  get size(): number {
    return this.buffer.size;
  }

  get capacity(): number {
    return this.buffer.capacity;
  }

  tryOffer(value: T): MailboxOfferResult<T> {
    if (value === undefined) {
      throw new Error('Mailbox cannot accept undefined values');
    }
    if (this.stateValue !== 'open') return { kind: 'closed' };
    if (this.pendingTake && this.buffer.size === 0) {
      const take = this.pendingTake;
      this.pendingTake = undefined;
      take.resolve(value);
      return { kind: 'accepted' };
    }
    if (this.overflow === 'suspend' && this.buffer.size >= this.buffer.capacity) {
      return { kind: 'full' };
    }
    return this.buffer.offer(value) as MailboxOfferResult<T>;
  }

  offer(value: T, options: { signal?: AbortSignal } = {}): Promise<MailboxOfferResult<T>> {
    if (value === undefined) {
      return Promise.reject(new Error('Mailbox cannot accept undefined values'));
    }
    if (this.overflow !== 'suspend') return Promise.resolve(this.tryOffer(value));
    const immediate = this.tryOffer(value);
    if (immediate.kind !== 'full') return Promise.resolve(immediate);

    return abortableWait<MailboxOfferResult<T>>(
      { signal: options.signal, fallback: 'Mailbox offer aborted' },
      (settle) => {
        const pending: PendingOffer<T> = {
          value,
          resolve: settle.resolve,
          reject: settle.reject,
        };
        this.suspendedOffers.push(pending);
        return () => this.removeSuspendedOffer(pending);
      }
    );
  }

  take(options: { signal?: AbortSignal } = {}): Promise<T> {
    return this.takeInternal(options, false);
  }

  tryTake(): T | undefined {
    if (this.iteratorActive)
      throw new MailboxConsumerError('Mailbox already has an active iterator');
    const value = this.buffer.take();
    if (value !== undefined) this.afterTake();
    return value;
  }

  drain(limit = Number.POSITIVE_INFINITY): T[] {
    const values: T[] = [];
    while (values.length < limit) {
      const value = this.buffer.take();
      if (value === undefined) break;
      values.push(value);
    }
    if (values.length > 0) this.afterTake();
    return values;
  }

  close(): void {
    if (this.stateValue !== 'open') return;
    this.stateValue = 'closing';
    this.closeSuspendedOffers();
    this.finishClosingIfDrained();
  }

  fail(error: unknown): void {
    if (this.stateValue !== 'open') return;
    this.failure = error;
    this.stateValue = 'failed';
    this.closeSuspendedOffers();
    if (this.buffer.size === 0) this.rejectPendingTake(error);
  }

  dispose(): void {
    if (this.stateValue === 'closed') return;
    this.stateValue = 'closed';
    this.failure = undefined;
    this.buffer.clear();
    this.closeSuspendedOffers();
    this.rejectPendingTake(new MailboxClosedError('Mailbox disposed'));
  }

  async *[Symbol.asyncIterator](): AsyncIterator<T> {
    if (this.iteratorActive)
      throw new MailboxConsumerError('Mailbox already has an active iterator');
    this.iteratorActive = true;
    try {
      for (;;) {
        try {
          yield await this.takeInternal({}, true);
        } catch (error) {
          if (error instanceof MailboxClosedError) return;
          throw error;
        }
      }
    } finally {
      this.iteratorActive = false;
    }
  }

  private takeInternal(options: { signal?: AbortSignal }, fromActiveIterator: boolean): Promise<T> {
    if (this.iteratorActive && !fromActiveIterator) {
      return Promise.reject(new MailboxConsumerError('Mailbox already has an active iterator'));
    }

    const value = this.buffer.take();
    if (value !== undefined) {
      this.afterTake();
      return Promise.resolve(value);
    }

    if (this.stateValue === 'failed') return Promise.reject(this.failure);
    if (this.stateValue !== 'open') return Promise.reject(new MailboxClosedError());
    if (this.pendingTake) {
      return Promise.reject(new MailboxConsumerError('Mailbox already has a pending take'));
    }

    return abortableWait<T>(
      { signal: options.signal, fallback: 'Mailbox take aborted' },
      (settle) => {
        const pending: PendingTake<T> = {
          resolve: settle.resolve,
          reject: settle.reject,
        };
        this.pendingTake = pending;
        return () => {
          if (this.pendingTake === pending) this.pendingTake = undefined;
        };
      }
    );
  }

  private afterTake(): void {
    if (this.stateValue === 'open') {
      this.acceptSuspendedOffers();
      return;
    }
    this.finishClosingIfDrained();
  }

  private acceptSuspendedOffers(): void {
    while (this.stateValue === 'open' && this.suspendedOffers.length > 0) {
      const pending = this.suspendedOffers[0];
      const result = this.tryOffer(pending.value);
      if (result.kind === 'full') return;
      this.suspendedOffers.shift();
      pending.resolve(result);
    }
  }

  private finishClosingIfDrained(): void {
    if (this.stateValue !== 'closing' || this.buffer.size > 0) return;
    this.stateValue = 'closed';
    this.rejectPendingTake(new MailboxClosedError());
  }

  private closeSuspendedOffers(): void {
    const offers = this.suspendedOffers.splice(0);
    for (const offer of offers) {
      offer.resolve({ kind: 'closed' });
    }
  }

  private removeSuspendedOffer(pending: PendingOffer<T>): void {
    const index = this.suspendedOffers.indexOf(pending);
    if (index >= 0) this.suspendedOffers.splice(index, 1);
  }

  private rejectPendingTake(error: unknown): void {
    const take = this.pendingTake;
    if (!take) return;
    this.pendingTake = undefined;
    take.reject(error);
  }
}

function mailboxOverflowToBufferOverflow(overflow: MailboxOverflow): BoundedBufferOverflow {
  switch (overflow) {
    case 'drop-oldest':
      return 'drop-oldest';
    case 'drop-newest':
      return 'drop-newest';
    case 'reject':
    case 'suspend':
      return 'reject';
  }
}
