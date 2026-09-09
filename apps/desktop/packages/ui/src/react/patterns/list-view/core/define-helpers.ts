import type {
  FilterModel,
  FilterSpec,
  PaginationSpec,
  RenameSpec,
  SearchSpec,
  SelectionSpec,
  SortSpec,
} from './types';

/**
 * Identity helper for search specs — preserves literal type inference when the
 * spec is authored outside the `createListView({...})` call.
 *
 * ```ts
 * const mySearch = defineSearch<Task>({
 *   kind: 'sync',
 *   predicate: createTextMatcher((t) => t.name),
 * });
 * const view = createListView({ ..., search: mySearch });
 * ```
 */
export const defineSearch = <T>(spec: SearchSpec<T>): SearchSpec<T> => spec;

/**
 * Identity helper for filter specs.
 *
 * ```ts
 * const myFilter = defineFilter<Task, { status: 'all' | 'open' }>({
 *   kind: 'sync',
 *   initial: { status: 'all' },
 *   apply: (t, f) => f.status === 'all' || t.status === f.status,
 * });
 * ```
 */
export const defineFilter = <T, const F extends FilterModel>(
  spec: FilterSpec<T, F>
): FilterSpec<T, F> => spec;

/**
 * Identity helper for sort specs.
 *
 * ```ts
 * const mySort = defineSort<Task, 'name' | 'updated'>({
 *   keys: {
 *     name: { label: 'Name', compare: byField((t) => t.name) },
 *     updated: { label: 'Updated', compare: byField((t) => t.updatedAt, 'desc') },
 *   },
 *   initial: { key: 'updated', dir: 'desc' },
 * });
 * ```
 */
export const defineSort = <T, const K extends string>(spec: SortSpec<T, K>): SortSpec<T, K> => spec;

/**
 * Identity helper for pagination specs.
 */
export const definePagination = <T>(spec: PaginationSpec<T>): PaginationSpec<T> => spec;

/**
 * Identity helper for selection specs.
 */
export const defineSelection = (spec: SelectionSpec): SelectionSpec => spec;

/**
 * Identity helper for rename specs.
 */
export const defineRename = <T>(spec: RenameSpec<T>): RenameSpec<T> => spec;
