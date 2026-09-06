import { ExpandableImage } from '@emdash/ui/react/components';
import { observer } from 'mobx-react-lite';
import { useMemo } from 'react';
import type { FileTabResource } from '@core/features/editor/api/browser/task-editor/stores/file-tab-resource';

interface SvgRendererProps {
  tab: FileTabResource;
}

/**
 * Renders an SVG file as an image preview.
 * The source/preview toggle lives in the FileContent container above this component.
 */
export const SvgRenderer = observer(function SvgRenderer({ tab }: SvgRendererProps) {
  // Touch bufferVersion so this observer re-renders when the buffer is first
  // populated — otherwise the preview can stick on an empty src.
  void tab.bufferVersion;
  const content = tab.bufferText();
  const svgUrl = useMemo(
    () => (content ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent(content)}` : ''),
    [content]
  );
  const fileName = tab.path.split('/').pop() ?? tab.path;

  return (
    <div className="flex h-full items-center justify-center overflow-auto p-4">
      {svgUrl ? (
        <ExpandableImage
          src={svgUrl}
          alt={fileName}
          containerClassName="max-h-full max-w-full"
          className="max-h-full max-w-full"
        />
      ) : (
        <div className="text-xs text-foreground-passive">Empty file</div>
      )}
    </div>
  );
});
