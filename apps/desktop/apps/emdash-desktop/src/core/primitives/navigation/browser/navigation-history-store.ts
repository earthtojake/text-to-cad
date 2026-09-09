import { createEmitter } from '@emdash/shared';
import { makeAutoObservable, observable } from 'mobx';
import type { HistoryEntry } from '../api';

const MAX_STACK_SIZE = 50;

/** Collapses adjacent identical entries that appear after a prune. */
function flatten(entries: HistoryEntry[]): HistoryEntry[] {
  return entries.filter(
    (entry, index) => index === entries.length - 1 || entry.key !== entries[index + 1]!.key
  );
}

/**
 * Tracks chronological view refs and participant locations. Traversals push,
 * refinements annotate, and restorations suppress recording.
 */
export class NavigationHistoryStore {
  entries: HistoryEntry[] = [];
  index = -1;
  readonly onDidChange = createEmitter<void>();

  private applying = false;

  constructor() {
    makeAutoObservable(this, {
      entries: observable.shallow,
      onDidChange: false,
      canGoBack: true,
      canGoForward: true,
    });
  }

  get canGoBack(): boolean {
    return this.index > 0;
  }

  get canGoForward(): boolean {
    return this.index < this.entries.length - 1;
  }

  get current(): HistoryEntry | undefined {
    return this.entries[this.index];
  }

  get isApplying(): boolean {
    return this.applying;
  }

  record(entry: HistoryEntry): void {
    if (this.applying) return;

    if (this.current?.key === entry.key) {
      this.entries[this.index] = entry;
      this.onDidChange.emit(undefined);
      return;
    }

    this.entries.splice(this.index + 1);
    this.entries.push(entry);

    if (this.entries.length > MAX_STACK_SIZE) {
      this.entries.shift();
    } else {
      this.index++;
    }
    this.onDidChange.emit(undefined);
  }

  annotate(entry: HistoryEntry): void {
    if (this.applying || !this.current) return;
    this.entries[this.index] = entry;
    this.onDidChange.emit(undefined);
  }

  nearestBefore(predicate: (entry: HistoryEntry) => boolean): HistoryEntry | undefined {
    for (let index = this.index - 1; index >= 0; index--) {
      const entry = this.entries[index]!;
      if (predicate(entry)) return entry;
    }
    return undefined;
  }

  back(apply: (entry: HistoryEntry) => boolean): void {
    this.traverse(-1, apply);
  }

  forward(apply: (entry: HistoryEntry) => boolean): void {
    this.traverse(1, apply);
  }

  /**
   * Removes all entries matching the predicate, then collapses adjacent
   * identical entries so no-op back steps are not created.
   * The cursor is clamped to the surviving entry nearest the removed position.
   *
   */
  prune(predicate: (entry: HistoryEntry) => boolean): void {
    const currentEntry = this.current;
    const oldIndex = this.index;
    this.entries = flatten(this.entries.filter((entry) => !predicate(entry)));
    const newIndex = currentEntry ? this.entries.indexOf(currentEntry) : -1;
    this.index =
      newIndex !== -1
        ? newIndex
        : this.entries.length === 0
          ? -1
          : Math.min(oldIndex, this.entries.length - 1);
    this.onDidChange.emit(undefined);
  }

  replace(entries: readonly HistoryEntry[], index: number): void {
    this.entries = entries.slice(-MAX_STACK_SIZE);
    const removed = Math.max(0, entries.length - this.entries.length);
    this.index =
      this.entries.length === 0
        ? -1
        : Math.min(Math.max(index - removed, 0), this.entries.length - 1);
    this.onDidChange.emit(undefined);
  }

  private traverse(direction: -1 | 1, apply: (entry: HistoryEntry) => boolean): void {
    while (direction === -1 ? this.index > 0 : this.index < this.entries.length - 1) {
      const targetIndex = this.index + direction;
      const target = this.entries[targetIndex]!;
      this.applying = true;
      let accepted: boolean;
      try {
        accepted = apply(target);
      } finally {
        this.applying = false;
      }

      if (accepted) {
        this.index = targetIndex;
        this.onDidChange.emit(undefined);
        return;
      }

      this.entries.splice(targetIndex, 1);
      if (direction === -1) this.index--;
      this.onDidChange.emit(undefined);
    }
  }
}

export type { HistoryEntry };
