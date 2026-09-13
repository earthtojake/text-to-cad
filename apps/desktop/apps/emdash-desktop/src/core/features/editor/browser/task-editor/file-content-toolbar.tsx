import { ToggleGroup } from '@emdash/ui/react/primitives';
import { observer } from 'mobx-react-lite';
import type { FileTabResource } from '@core/features/editor/api/browser/task-editor/stores/file-tab-resource';
import { useWorkspace } from '@core/features/workbench/api/browser/task-composition-context';
import { relativeToWorkspace } from '@core/features/workspaces/api/browser/workspace-path';

interface FileContentToolbarProps {
  tab: FileTabResource;
  canToggle: boolean;
}

/** Top bar shown on every file tab: file path on the left, Raw/Preview tabs on the right. */
export const FileContentToolbar = observer(function FileContentToolbar({
  tab,
  canToggle,
}: FileContentToolbarProps) {
  const workspace = useWorkspace();
  const displayPath = tab.inWorkspace
    ? relativeToWorkspace(workspace.path, tab.path)
    : tab.displayPath;
  return (
    <div className="flex h-[41px] shrink-0 items-center justify-between gap-2 border-b border-border bg-(--em-surface) px-2">
      <span
        className="min-w-0 flex-1 truncate text-xs text-foreground-passive"
        title={tab.displayPath}
      >
        {displayPath}
      </span>
      {canToggle && (
        <ToggleGroup.Root
          multiple={false}
          value={[tab.viewMode]}
          onValueChange={([value]) => {
            if (value === 'preview' || value === 'source') tab.setViewMode(value);
          }}
        >
          <ToggleGroup.Item size="sm" value="source" className="text-xs">
            Raw
          </ToggleGroup.Item>
          <ToggleGroup.Item size="sm" value="preview" className="text-xs">
            Preview
          </ToggleGroup.Item>
        </ToggleGroup.Root>
      )}
    </div>
  );
});
