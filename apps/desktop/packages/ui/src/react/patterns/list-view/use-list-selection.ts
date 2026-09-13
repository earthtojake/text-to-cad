import * as React from 'react';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ListSelectionState {
  selectedIds: Set<string>;
  count: number;
  isSelected: (id: string) => boolean;
  toggle: (id: string, event?: React.MouseEvent | React.KeyboardEvent) => void;
  selectRange: (toId: string) => void;
  selectAll: () => void;
  clear: () => void;
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * useListSelection — store-agnostic multi-select with shift-range support.
 *
 * Extracts the multi-select logic that was previously welded to the `taskView`
 * MobX store in `task-list.tsx`. The hook is purely local React state; callers
 * that need persistence can lift the state or synchronise it externally.
 *
 * @param orderedIds - The stable, ordered list of all item IDs currently visible
 *   in the list. Must be in the same order as the rendered rows so that
 *   shift-click range selection is deterministic.
 *
 * @example
 * ```tsx
 * const sel = ListView.useSelection(items.map(i => i.id));
 *
 * <ListView.Row
 *   selected={sel.isSelected(item.id)}
 *   onClick={(e) => sel.toggle(item.id, e)}
 * />
 *
 * {sel.count > 0 && (
 *   <ListView.Footer>
 *     <SelectionBar count={sel.count} onClear={sel.clear} />
 *   </ListView.Footer>
 * )}
 * ```
 */
export function useListSelection(orderedIds: string[]): ListSelectionState {
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set());
  // Track the last-clicked ID so shift-range works across re-renders.
  const anchorRef = React.useRef<string | null>(null);

  const isSelected = React.useCallback((id: string) => selectedIds.has(id), [selectedIds]);

  const toggle = React.useCallback(
    (id: string, event?: React.MouseEvent | React.KeyboardEvent) => {
      const isShift = event && 'shiftKey' in event && event.shiftKey;
      if (isShift && anchorRef.current) {
        // Shift-click: select the range from anchor → id.
        const anchorIdx = orderedIds.indexOf(anchorRef.current);
        const targetIdx = orderedIds.indexOf(id);
        if (anchorIdx !== -1 && targetIdx !== -1) {
          const [lo, hi] = anchorIdx < targetIdx ? [anchorIdx, targetIdx] : [targetIdx, anchorIdx];
          const rangeIds = orderedIds.slice(lo, hi + 1);
          setSelectedIds((prev) => {
            const next = new Set(prev);
            for (const rid of rangeIds) next.add(rid);
            return next;
          });
          return;
        }
      }
      anchorRef.current = id;
      setSelectedIds((prev) => {
        const next = new Set(prev);
        if (next.has(id)) {
          next.delete(id);
        } else {
          next.add(id);
        }
        return next;
      });
    },
    [orderedIds]
  );

  const selectRange = React.useCallback(
    (toId: string) => {
      if (!anchorRef.current) {
        setSelectedIds(new Set([toId]));
        anchorRef.current = toId;
        return;
      }
      const anchorIdx = orderedIds.indexOf(anchorRef.current);
      const targetIdx = orderedIds.indexOf(toId);
      if (anchorIdx === -1 || targetIdx === -1) return;
      const [lo, hi] = anchorIdx < targetIdx ? [anchorIdx, targetIdx] : [targetIdx, anchorIdx];
      const rangeIds = orderedIds.slice(lo, hi + 1);
      setSelectedIds((prev) => {
        const next = new Set(prev);
        for (const rid of rangeIds) next.add(rid);
        return next;
      });
    },
    [orderedIds]
  );

  const selectAll = React.useCallback(() => {
    setSelectedIds(new Set(orderedIds));
  }, [orderedIds]);

  const clear = React.useCallback(() => {
    setSelectedIds(new Set());
    anchorRef.current = null;
  }, []);

  return {
    selectedIds,
    count: selectedIds.size,
    isSelected,
    toggle,
    selectRange,
    selectAll,
    clear,
  };
}
