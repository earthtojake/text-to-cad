import { FilterButton, FilterPill } from './filter-pill';
import { Row, SectionHeader } from './list-row';
import { ListViewRoot, Toolbar, FilterPills, Body, Footer } from './list-view';
import { useListSelection } from './use-list-selection';
import { VirtualList } from './virtual-list';

// ── Public namespace ──────────────────────────────────────────────────────────

/**
 * ListView — the raw, virtualized list chrome. **Internal escape hatch, not a
 * page pattern**: page-level lists render through `CollectionView`
 * (`../collection-view/`), which owns this chrome and pairs it with the
 * headless `createListView` state factory below. Compose these pieces directly
 * only when a surface genuinely cannot fit `CollectionView`'s shell (for
 * example the workbench sidebar lists) — and expect to justify that in review.
 *
 * Usage (escape hatch only):
 * ```tsx
 * <ListView>
 *   <ListView.Toolbar>
 *     <SearchInput ... />
 *   </ListView.Toolbar>
 *   <ListView.FilterPills>
 *     <ListView.FilterPill label="open" onRemove={...} />
 *   </ListView.FilterPills>
 *   <ListView.Body>
 *     <ListView.List
 *       items={myItems}
 *       getItemKey={i => i.id}
 *       renderItem={item => (
 *         <ListView.Row interactive>...</ListView.Row>
 *       )}
 *     />
 *   </ListView.Body>
 * </ListView>
 * ```
 */
export const ListView = Object.assign(ListViewRoot, {
  Toolbar,
  FilterPills,
  Body,
  Footer,
  List: VirtualList,
  Row,
  SectionHeader,
  FilterButton,
  FilterPill,
  useSelection: useListSelection,
});

// ── Re-export types ───────────────────────────────────────────────────────────

export type { ListViewSection, VirtualListProps, VirtualListHandle } from './virtual-list';
export type { RowProps, SectionHeaderProps } from './list-row';
export type { FilterPillProps, FilterButtonProps } from './filter-pill';
export type { ListSelectionState } from './use-list-selection';

// ── Pure primitives ───────────────────────────────────────────────────────────

export { matchesQuery, createTextMatcher } from './matching';
export type { TextMatcherOptions } from './matching';

export {
  compareStrings,
  compareNumbers,
  compareDates,
  byField,
  chainComparators,
} from './comparators';
export type { Comparator } from './comparators';

export { useClientListFilter } from './use-client-list-filter';
export type { ClientListFilterOptions } from './use-client-list-filter';

export { useQueryListSource } from './use-query-list-source';
export type { ExternalListSource, QueryResultLike } from './use-query-list-source';

// ── Headless state factory (createListView) ───────────────────────────────────

export { createListView } from './core/create-list-view';
export type {
  ListViewApi,
  ListProps,
  StaticListProps,
  VirtualizationOptions,
} from './core/create-list-view';

export { ListViewStore } from './core/list-view-store';

export {
  defineSearch,
  defineFilter,
  defineSort,
  definePagination,
  defineSelection,
  defineRename,
} from './core/define-helpers';

export type {
  ListViewSpec,
  ListSource,
  SearchSpec,
  FilterSpec,
  FilterModel,
  SortSpec,
  SectionsSpec,
  PaginationSpec,
  SelectionSpec,
  RenameSpec,
  ExternalSelectionStore,
  SearchApi,
  FilterApi,
  SortApi,
  PaginationApi,
  SelectionApi,
  RenameApi,
  ScrollApi,
  ListViewSnapshot,
  ItemContextValue,
  SectionContextValue,
  FilterModelOf,
  SortKeyOf,
} from './core/types';
