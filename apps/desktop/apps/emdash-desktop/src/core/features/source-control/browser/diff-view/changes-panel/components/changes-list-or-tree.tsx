import { type ChangesListViewMode } from '@core/primitives/app-settings/api';
import {
  VirtualizedChangesList,
  type VirtualizedChangesListProps,
} from './virtualized-changes-list';
import { VirtualizedChangesTree } from './virtualized-changes-tree';

interface ChangesListOrTreeProps extends VirtualizedChangesListProps {
  viewMode: ChangesListViewMode;
}

export function ChangesListOrTree({ viewMode, ...props }: ChangesListOrTreeProps) {
  if (viewMode === 'tree') return <VirtualizedChangesTree {...props} />;
  return <VirtualizedChangesList {...props} />;
}
