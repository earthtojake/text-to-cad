import * as React from 'react';
import { Select } from '../../primitives/select';
import type { SortApi } from '../list-view';

export interface SortSelectProps<K extends string> {
  /** The view's sort API — `view.useSort()`. */
  sort: SortApi<K>;
  /** Accessible label for the trigger. Defaults to 'Sort'. */
  label?: string;
  className?: string;
}

/**
 * SortSelect — the canonical sorting control for CollectionView toolbars.
 *
 * Binds a `Select` to `view.useSort()`, reading its keys and labels from the
 * sort spec so surfaces never re-declare their sort options in the UI.
 * Call it inside an observer component (like all view hooks):
 *
 * ```tsx
 * const Toolbar = observer(function Toolbar() {
 *   const sort = tasksView.useSort();
 *   return <CollectionToolbar actions={<SortSelect sort={sort} />} ... />;
 * });
 * ```
 */
export function SortSelect<K extends string>({
  sort,
  label = 'Sort',
  className,
}: SortSelectProps<K>) {
  const keys = Object.keys(sort.keys) as K[];
  return (
    <Select.Root
      value={sort.key}
      onValueChange={(key) => {
        if (key) sort.setKey(key as K);
      }}
    >
      <Select.Trigger aria-label={label} className={className}>
        <Select.Value>{sort.keys[sort.key].label}</Select.Value>
      </Select.Trigger>
      <Select.Content align="end">
        {keys.map((key) => (
          <Select.Item key={key} value={key}>
            {sort.keys[key].label}
          </Select.Item>
        ))}
      </Select.Content>
    </Select.Root>
  );
}
