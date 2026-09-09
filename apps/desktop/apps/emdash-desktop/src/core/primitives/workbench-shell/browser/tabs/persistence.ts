export type PersistedTabDescriptor = {
  kind: string;
  tabId: string;
  isPreview: boolean;
  [key: string]: unknown;
};

export type TabManagerSnapshot = {
  tabs: PersistedTabDescriptor[];
  activeTabId?: string;
};

export type TabGroupsSnapshot = {
  groups: Array<{
    groupId: string;
    tabManager: TabManagerSnapshot;
  }>;
  activeGroupId: string;
};

/**
 * The persisted memento document backing a PaneLayoutStore: the snapshot plus
 * whatever versioned-schema envelope the owning feature defines. The store
 * only reads/writes the snapshot fields; envelope fields (e.g. `version`) are
 * carried through unchanged on persist.
 */
export type PaneLayoutSnapshotDocument = TabGroupsSnapshot & { version: string };

/**
 * The slice of a memento handle that PaneLayoutStore needs to hydrate and
 * persist its snapshot. A feature's `MementoHandle` for its versioned
 * pane-layout document satisfies this structurally — no adapter class.
 */
export interface PaneLayoutSnapshotMemento {
  /** Resolves once the memento's initial hydration has settled. */
  readonly ready: Promise<void>;
  /** True when a persisted document exists. Accurate only after `ready`. */
  readonly hasStoredValue: boolean;
  read(): PaneLayoutSnapshotDocument;
  /**
   * Start persisting `read()` through the memento's debounced write path,
   * re-running on observable changes with structural equality.
   * @returns A disposer — call it to stop persistence.
   */
  autoPersist(read: () => PaneLayoutSnapshotDocument): () => void;
}
