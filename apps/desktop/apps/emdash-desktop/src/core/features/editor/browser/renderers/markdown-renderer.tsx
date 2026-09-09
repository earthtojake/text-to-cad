import { Markdown } from '@emdash/ui/react/components';
import { observer } from 'mobx-react-lite';
import { useCallback } from 'react';
import { resolveWorkspaceResourcePath } from '@core/features/editor/api/browser/renderers/workspace-resource-path';
import type { FileTabResource } from '@core/features/editor/api/browser/task-editor/stores/file-tab-resource';
import { readImageFile } from '@core/features/files/api/browser/file-content';
import { useWorkspace } from '@core/features/workbench/api/browser/task-composition-context';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';
import { useMarkdownLinkOpener } from '@core/primitives/external-links/browser';
import { usePaneContext } from '@core/primitives/workbench-shell/browser/tabs/pane-context';

interface MarkdownEditorRendererProps {
  tab: FileTabResource;
}

/**
 * Renders a markdown file as a formatted preview.
 * The source/preview toggle lives in the FileContent container above this component.
 */
export const MarkdownEditorRenderer = observer(function MarkdownEditorRenderer({
  tab,
}: MarkdownEditorRendererProps) {
  const workspace = useWorkspace();
  const workspacePath = workspace.path;
  const { pane } = usePaneContext();

  // Reading bufferVersion creates a MobX tracking dependency so this observer
  // component re-renders whenever the buffer content changes or is first populated.
  void tab.bufferVersion;
  const content = tab.bufferText();

  const resolveImage = useCallback(
    async (src: string): Promise<string | null> => {
      const imagePath = resolveWorkspaceResourcePath({
        workspacePath,
        containingFilePath: tab.path,
        resourcePath: src,
      });
      if (!imagePath) return null;
      const result = await readImageFile(
        hostFileRefFromNativePath(imagePath, workspace.sshConnectionId)
      );
      return result.success && !result.data.truncated ? result.data.dataUrl : null;
    },
    [workspace.sshConnectionId, workspacePath, tab.path]
  );

  const openWorkspaceLink = useCallback(
    (href: string): boolean => {
      const target = resolveWorkspaceResourcePath({
        workspacePath,
        containingFilePath: tab.path,
        resourcePath: href,
      });
      if (!target) return false;
      pane.open('file', { path: target }, { preview: false });
      return true;
    },
    [workspacePath, tab.path, pane]
  );

  const openLink = useMarkdownLinkOpener(openWorkspaceLink);

  return (
    <div className="relative h-full overflow-y-auto bg-(--em-surface)">
      <Markdown
        content={content}
        variant="full"
        className="w-full max-w-3xl px-8 py-8"
        resolveImage={resolveImage}
        onOpenLink={openLink}
      />
    </div>
  );
});
