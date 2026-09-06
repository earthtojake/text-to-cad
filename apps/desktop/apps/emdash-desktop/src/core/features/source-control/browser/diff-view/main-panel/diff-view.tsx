import { observer } from 'mobx-react-lite';
import type { DiffTabResource } from '../stores/diff-tab-resource';
import { DiffFileRenderer } from './diff-file-renderer';
import { DiffToolbar } from './diff-toolbar';

interface DiffViewProps {
  tab: DiffTabResource;
}

export const DiffView = observer(function DiffView({ tab }: DiffViewProps) {
  return (
    <div className="flex h-full flex-col">
      <DiffToolbar tab={tab} />
      <div className="min-h-0 flex-1">
        <DiffFileRenderer tab={tab} />
      </div>
    </div>
  );
});
