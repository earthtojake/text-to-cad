import type { VirtualListHandle } from '../../virtual-list';

/**
 * ScrollSlice — bridges the MobX store to the `VirtualListHandle` imperative API.
 *
 * The `List` component forwards the `ref` to `attachHandle` so slices (rename,
 * keyboard navigation) can scroll items into view without holding React refs.
 *
 * No MobX annotations are needed; this slice holds no reactive state.
 */
export class ScrollSlice {
  private handle: VirtualListHandle | null = null;

  /**
   * Called by `List` via `ref` — stores the virtualizer's imperative handle.
   * Pass `null` to clear (called on unmount).
   */
  attachHandle = (h: VirtualListHandle | null): void => {
    this.handle = h;
  };

  /**
   * Scrolls to the item with the given id.
   * No-ops when the id is not in `orderedIds` or the handle is not attached.
   */
  toId(
    id: string,
    orderedIds: string[],
    opts?: { align?: 'auto' | 'start' | 'center' | 'end' }
  ): void {
    const idx = orderedIds.indexOf(id);
    if (idx >= 0) this.handle?.scrollToIndex(idx, opts);
  }

  /** Scrolls to the item at the given flat index. */
  toIndex(index: number, opts?: { align?: 'auto' | 'start' | 'center' | 'end' }): void {
    this.handle?.scrollToIndex(index, opts);
  }
}
