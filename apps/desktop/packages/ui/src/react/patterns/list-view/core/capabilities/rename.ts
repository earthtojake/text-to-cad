import { action, makeObservable, observable } from 'mobx';
import type { RenameSpec } from '../types';
import type { ScrollSlice } from './scroll';

/**
 * RenameSlice — manages inline rename state.
 *
 * `editingId` is the id of the item currently being renamed, or `null` when idle.
 * `begin(id)` also scrolls the item into view so the rename input is visible.
 */
export class RenameSlice<T> {
  editingId: string | null = null;

  constructor(
    readonly spec: RenameSpec<T>,
    private readonly getItemById: (id: string) => T | undefined,
    private readonly getOrderedIds: () => string[],
    private readonly scroll: ScrollSlice
  ) {
    makeObservable(this, {
      editingId: observable,
      begin: action,
      cancel: action,
      _clearEditing: action,
    });
  }

  canRename(item: T): boolean {
    return this.spec.canRename ? this.spec.canRename(item) : true;
  }

  begin(id: string): void {
    this.editingId = id;
    // Scroll the item into view so the inline input is visible.
    this.scroll.toId(id, this.getOrderedIds(), { align: 'auto' });
  }

  async commit(name: string): Promise<void> {
    const id = this.editingId;
    if (!id) return;
    const item = this.getItemById(id);
    if (!item) {
      this._clearEditing();
      return;
    }
    this._clearEditing();
    await this.spec.commit(item, name);
  }

  cancel(): void {
    this._clearEditing();
  }

  /** @internal */
  _clearEditing(): void {
    this.editingId = null;
  }
}
