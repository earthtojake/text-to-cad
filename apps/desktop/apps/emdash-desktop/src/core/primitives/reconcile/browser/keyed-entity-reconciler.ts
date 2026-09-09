import { runInAction } from 'mobx';

export type KeyedEntityReconcileOptions<Row, Store> = {
  readonly rows: readonly Row[];
  readonly stores: Map<string, Store>;
  readonly getRowId: (row: Row) => string;
  readonly shouldKeepMissing?: (id: string, store: Store) => boolean;
  readonly create: (row: Row) => Store;
  readonly update: (store: Store, row: Row) => void;
  readonly remove?: (store: Store, id: string) => void;
  readonly onAppear?: (store: Store, row: Row) => void;
};

export function reconcileKeyedEntities<Row, Store>(
  options: KeyedEntityReconcileOptions<Row, Store>
): void {
  const seen = new Set(options.rows.map(options.getRowId));
  runInAction(() => {
    for (const row of options.rows) {
      const id = options.getRowId(row);
      const current = options.stores.get(id);
      if (current) {
        options.update(current, row);
        continue;
      }

      const created = options.create(row);
      options.stores.set(id, created);
      options.onAppear?.(created, row);
    }

    for (const [id, store] of options.stores) {
      if (seen.has(id) || options.shouldKeepMissing?.(id, store)) continue;
      options.stores.delete(id);
      options.remove?.(store, id);
    }
  });
}
