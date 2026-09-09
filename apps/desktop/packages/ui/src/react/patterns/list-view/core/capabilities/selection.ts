import { action, makeObservable, observable, ObservableSet } from 'mobx';
import type * as React from 'react';

/**
 * SelectionSlice — built-in multi/single-select with shift-range support.
 *
 * Range selection operates on `orderedIds` (the full visible list supplied by
 * the store), so shift-click works correctly even for off-screen virtualized rows.
 *
 * For external selection stores, use `ExternalSelectionStore` from `types.ts` directly.
 */
export class SelectionSlice {
  readonly selectedIds: ObservableSet<string> = new ObservableSet<string>();
  private anchor: string | null = null;

  constructor(private readonly mode: 'single' | 'multi') {
    // The 'anchor' generic arg tells makeObservable to annotate the private field.
    makeObservable<SelectionSlice, 'anchor'>(this, {
      selectedIds: observable,
      anchor: observable,
      toggle: action,
      selectRange: action,
      selectAll: action,
      clear: action,
      toggleWithRange: action,
    });
  }

  get count(): number {
    return this.selectedIds.size;
  }

  isSelected(id: string): boolean {
    return this.selectedIds.has(id);
  }

  toggle(id: string, e?: React.MouseEvent | React.KeyboardEvent): void {
    const isShift = e && 'shiftKey' in e && e.shiftKey;
    if (this.mode === 'single') {
      if (this.selectedIds.has(id)) {
        this.selectedIds.clear();
      } else {
        this.selectedIds.replace([id]);
        this.anchor = id;
      }
      return;
    }

    if (isShift && this.anchor) {
      // Shift-click requires orderedIds to determine the range.
      // The anchor is stored; the caller is responsible for passing orderedIds
      // via selectRange() when using keyboard/shift.
      return;
    }

    if (this.selectedIds.has(id)) {
      this.selectedIds.delete(id);
    } else {
      this.selectedIds.add(id);
    }
    this.anchor = id;
  }

  /**
   * Selects the range from `fromId` to `toId` (inclusive) using the supplied
   * ordered id list.  Both endpoints must appear in `orderedIds`.
   */
  selectRange(fromId: string, toId: string, orderedIds: string[]): void {
    const fromIdx = orderedIds.indexOf(fromId);
    const toIdx = orderedIds.indexOf(toId);
    if (fromIdx === -1 || toIdx === -1) return;
    const [lo, hi] = fromIdx < toIdx ? [fromIdx, toIdx] : [toIdx, fromIdx];
    this.selectedIds.replace(orderedIds.slice(lo, hi + 1));
  }

  selectAll(orderedIds: string[]): void {
    this.selectedIds.replace(orderedIds);
  }

  clear(): void {
    this.selectedIds.clear();
    this.anchor = null;
  }

  /**
   * Handles toggle with shift-range: if shift is held and an anchor exists,
   * selects the range from anchor → id.  Otherwise toggles the single id.
   */
  toggleWithRange(
    id: string,
    orderedIds: string[],
    e?: React.MouseEvent | React.KeyboardEvent
  ): void {
    const isShift = e && 'shiftKey' in e && e.shiftKey;
    if (isShift && this.anchor && this.mode === 'multi') {
      this.selectRange(this.anchor, id, orderedIds);
      return;
    }
    this.toggle(id);
  }
}
