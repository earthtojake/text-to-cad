import { MicroLabel, ToggleGroup } from '@emdash/ui/react/primitives';
import { AlignJustify, Columns2 } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { useTaskComposition } from '@core/features/workbench/api/browser/task-composition-context';
import type { DiffTabResource } from '../stores/diff-tab-resource';

interface DiffToolbarProps {
  tab: DiffTabResource;
}

export const DiffToolbar = observer(function DiffToolbar({ tab }: DiffToolbarProps) {
  const diffView = useTaskComposition().diffView;
  const diffStyle = diffView?.diffStyle;
  const canPreview = tab.renderer.kind === 'text' && tab.renderer.previewKind !== undefined;

  const diffSourceLabel = (() => {
    if (tab.diffGroup === 'staged') return 'Staged';
    if (tab.diffGroup === 'disk') return 'Changed';
    if (tab.diffGroup === 'pr') return 'PR';
    if (tab.diffGroup === 'git') return 'Git';
    return undefined;
  })();

  if (!diffView || !diffStyle) return null;

  return (
    <div className="flex h-[41px] items-center justify-between gap-2 border-b border-border bg-(--em-surface) px-2">
      <div className="flex items-center gap-3">
        {diffSourceLabel && <MicroLabel>{diffSourceLabel}</MicroLabel>}
      </div>
      <div className="flex items-center gap-2">
        {canPreview && (
          <ToggleGroup.Root
            multiple={false}
            value={[tab.viewMode]}
            onValueChange={([value]) => {
              if (value === 'diff' || value === 'preview') tab.setViewMode(value);
            }}
          >
            <ToggleGroup.Item size="sm" value="diff" className="text-xs">
              Diff
            </ToggleGroup.Item>
            <ToggleGroup.Item size="sm" value="preview" className="text-xs">
              Preview
            </ToggleGroup.Item>
          </ToggleGroup.Root>
        )}
        {tab.viewMode === 'diff' && (
          <ToggleGroup.Root
            multiple={false}
            value={[diffStyle]}
            onValueChange={([value]) => {
              if (value) {
                diffView.setDiffStyle(value as 'unified' | 'split');
              }
            }}
          >
            <ToggleGroup.Item size="sm" icon value="unified" aria-label="Unified diff">
              <AlignJustify className="h-3.5 w-3.5" />
            </ToggleGroup.Item>
            <ToggleGroup.Item size="sm" icon value="split" aria-label="Split diff">
              <Columns2 className="h-3.5 w-3.5" />
            </ToggleGroup.Item>
          </ToggleGroup.Root>
        )}
      </div>
    </div>
  );
});
