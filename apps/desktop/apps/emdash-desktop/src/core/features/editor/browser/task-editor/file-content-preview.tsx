import { observer } from 'mobx-react-lite';
import type { FileTabResource } from '@core/features/editor/api/browser/task-editor/stores/file-tab-resource';
import { FILE_CONTENT_TYPES } from './file-content-types';

interface FileContentPreviewProps {
  tab: FileTabResource;
}

/**
 * Renders the preview for a file tab by routing on tab.fileKind via FILE_CONTENT_TYPES.
 *
 * Only mounted when the container (FileContent) determines showPreview is true, which
 * means this component's wrapper div never covers Monaco in source mode — fixing the
 * pointer-events bug from the old always-mounted overlay approach.
 */
export const FileContentPreview = observer(function FileContentPreview({
  tab,
}: FileContentPreviewProps) {
  const def = FILE_CONTENT_TYPES[tab.fileKind];
  if (!def.Preview) return null;
  const { Preview } = def;
  return <Preview tab={tab} />;
});
