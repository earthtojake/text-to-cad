import { err, ok, type Result } from '@emdash/shared';
import { makeAutoObservable, observable } from 'mobx';
import type { ModalDismissed, ModalDismissReason } from '@core/primitives/modals/react';

interface Deferred<T> {
  readonly promise: Promise<T>;
  settled: boolean;
  resolve(value: T): void;
}

function createDeferred<T>(): Deferred<T> {
  let resolvePromise!: (value: T) => void;
  const deferred: Deferred<T> = {
    promise: new Promise<T>((resolve) => {
      resolvePromise = resolve;
    }),
    settled: false,
    resolve(value) {
      if (deferred.settled) return;
      deferred.settled = true;
      resolvePromise(value);
    },
  };
  return deferred;
}

export interface ModalStackEntry {
  readonly key: number;
  readonly id: string;
  readonly args: Record<string, unknown>;
  readonly closeGuardActive: boolean;
  readonly closing: boolean;
}

interface ModalEntry extends ModalStackEntry {
  pendingOpen: Deferred<Result<unknown, ModalDismissed>> | null;
  closeSequence: number;
}

export class ModalStore {
  stack: ModalEntry[] = [];
  previousFocus: HTMLElement | null = null;
  private nextKey = 1;

  constructor() {
    makeAutoObservable<this, 'nextKey'>(this, {
      stack: observable.shallow,
      previousFocus: observable.ref,
      nextKey: false,
    });
  }

  open(id: string, props: unknown): Promise<Result<unknown, ModalDismissed>> {
    const pendingOpen = createDeferred<Result<unknown, ModalDismissed>>();
    this.activateModal(id, props as Record<string, unknown>, pendingOpen);
    return pendingOpen.promise;
  }

  complete(result: unknown): void {
    const entry = this.topOpenEntry;
    if (!entry) return;
    this.completeEntry(entry.key, result);
  }

  completeEntry(key: number, result: unknown): void {
    const entry = this.findEntry(key);
    if (!entry || entry.closing) return;
    entry.pendingOpen?.resolve(ok(result));
    entry.pendingOpen = null;
    this.scheduleEntryClose(entry);
  }

  dismiss(reason: ModalDismissReason = 'explicit'): void {
    const entry = this.topOpenEntry;
    if (!entry) return;
    this.dismissEntry(entry.key, reason);
  }

  dismissEntry(key: number, reason: ModalDismissReason = 'explicit'): void {
    const entry = this.findEntry(key);
    if (!entry || entry.closing) return;
    entry.pendingOpen?.resolve(err<ModalDismissed>({ type: 'modal_dismissed', reason }));
    entry.pendingOpen = null;
    this.scheduleEntryClose(entry);
  }

  dismissAll(reason: ModalDismissReason = 'explicit'): void {
    for (const entry of this.stack.slice().reverse()) {
      if (!entry.closing) {
        this.dismissEntry(entry.key, reason);
      }
    }
  }

  setCloseGuard(active: boolean): void {
    const entry = this.topOpenEntry;
    if (!entry) return;
    this.setEntryCloseGuard(entry.key, active);
  }

  setEntryCloseGuard(key: number, active: boolean): void {
    const entry = this.findEntry(key);
    if (!entry || entry.closing) return;
    this.replaceEntry(entry, { closeGuardActive: active });
  }

  removeEntry(key: number): void {
    this.stack = this.stack.filter((entry) => entry.key !== key);
  }

  consumePreviousFocus(): HTMLElement | null {
    const previousFocus = this.previousFocus;
    this.previousFocus = null;
    return previousFocus;
  }

  get isOpen(): boolean {
    return this.topOpenEntry !== null;
  }

  get activeModalId(): string | null {
    return this.topOpenEntry?.id ?? null;
  }

  get activeModalArgs(): Record<string, unknown> | null {
    return this.topOpenEntry?.args ?? null;
  }

  get closeGuardActive(): boolean {
    return this.topOpenEntry?.closeGuardActive ?? false;
  }

  get topEntry(): ModalEntry | null {
    return this.stack[this.stack.length - 1] ?? null;
  }

  private get topOpenEntry(): ModalEntry | null {
    for (let index = this.stack.length - 1; index >= 0; index -= 1) {
      const entry = this.stack[index];
      if (!entry.closing) return entry;
    }
    return null;
  }

  private activateModal(
    id: string,
    args: Record<string, unknown>,
    pendingOpen: Deferred<Result<unknown, ModalDismissed>>
  ): void {
    const topEntry = this.topEntry;
    if (!topEntry && typeof document !== 'undefined') {
      this.previousFocus = document.activeElement as HTMLElement | null;
    }

    const entry: ModalEntry = {
      key: this.nextKey++,
      id,
      args,
      pendingOpen,
      closeGuardActive: false,
      closing: false,
      closeSequence: 0,
    };

    if (topEntry?.closing) {
      this.replaceEntry(topEntry, entry);
      return;
    }

    this.stack = [...this.stack, entry];
  }

  private scheduleEntryClose(entry: ModalEntry): void {
    const closeSequence = entry.closeSequence + 1;
    this.replaceEntry(entry, {
      pendingOpen: null,
      closeGuardActive: false,
      closing: true,
      closeSequence,
    });
    if (typeof document === 'undefined') {
      queueMicrotask(() => this.finalizeEntryClose(entry.key, closeSequence));
    }
  }

  private finalizeEntryClose(key: number, closeSequence: number): void {
    const entry = this.findEntry(key);
    if (!entry || !entry.closing || entry.closeSequence !== closeSequence) return;
    this.removeEntry(key);
  }

  private findEntry(key: number): ModalEntry | undefined {
    return this.stack.find((entry) => entry.key === key);
  }

  private replaceEntry(entry: ModalEntry, patch: Partial<ModalEntry>): void {
    this.stack = this.stack.map((current) =>
      current.key === entry.key ? { ...current, ...patch } : current
    );
  }
}

export const modalStore = new ModalStore();
