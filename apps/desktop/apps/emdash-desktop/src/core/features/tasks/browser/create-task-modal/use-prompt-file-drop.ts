import { useCallback, useRef, useState } from 'react';
import { resolveDroppedFile } from '@core/features/terminals/api/browser/pty/terminal-image-injection';
import { formatTerminalImagePaths } from '@core/features/terminals/api/browser/pty/terminal-image-paths';
import { getHostClient } from '@core/primitives/desktop-host/browser/host-client';
import {
  getDraggedWorkspaceFile,
  hasDraggedFiles,
  hasDraggedWorkspaceFile,
} from '@core/primitives/drag-files/browser/drag-files';
import { log } from '@core/primitives/logging/browser/logger';

/**
 * Drag-and-drop file support for prompt textareas: dropping OS files or
 * in-app file tree rows appends their paths (escaped like terminal drops)
 * to the prompt via `onDropText`.
 */
export function usePromptFileDrop({
  disableLocalFiles = false,
  onDropText,
  workspaceId,
}: {
  /** Reject OS file drops, e.g. for SSH projects where local paths would not exist remotely. */
  disableLocalFiles?: boolean;
  onDropText: (text: string) => void;
  workspaceId?: string;
}) {
  const [isDragOver, setIsDragOver] = useState(false);
  const dragCounter = useRef(0);

  const accepts = useCallback(
    (dataTransfer: DataTransfer) => {
      if (hasDraggedWorkspaceFile(dataTransfer)) {
        const workspaceFile = getDraggedWorkspaceFile(dataTransfer);
        return Boolean(workspaceId && workspaceFile?.workspaceId === workspaceId);
      }

      return !disableLocalFiles && hasDraggedFiles(dataTransfer);
    },
    [disableLocalFiles, workspaceId]
  );

  const onDragOver = useCallback(
    (e: React.DragEvent) => {
      if (!accepts(e.dataTransfer)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
    },
    [accepts]
  );

  const onDragEnter = useCallback(
    (e: React.DragEvent) => {
      if (!accepts(e.dataTransfer)) return;
      e.preventDefault();
      dragCounter.current++;
      setIsDragOver(true);
    },
    [accepts]
  );

  const onDragLeave = useCallback(
    (e: React.DragEvent) => {
      if (!accepts(e.dataTransfer)) return;
      e.preventDefault();
      dragCounter.current--;
      if (dragCounter.current <= 0) {
        dragCounter.current = 0;
        setIsDragOver(false);
      }
    },
    [accepts]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      if (!accepts(e.dataTransfer)) return;
      e.preventDefault();
      dragCounter.current = 0;
      setIsDragOver(false);

      const workspaceFile = getDraggedWorkspaceFile(e.dataTransfer);
      if (workspaceFile && workspaceFile.workspaceId !== workspaceId) return;

      const files = workspaceFile ? [] : Array.from(e.dataTransfer.files);
      if (!workspaceFile && files.length === 0) return;

      void (async () => {
        try {
          const platform =
            workspaceFile?.targetPlatform ?? (await (await getHostClient()).getPlatform());
          if (workspaceFile) {
            onDropText(formatTerminalImagePaths(workspaceFile.targetPaths, platform));
            return;
          }
          const resolved = await Promise.all(files.map((file) => resolveDroppedFile(file)));
          const paths = resolved.filter((path): path is string => Boolean(path));
          if (paths.length === 0) return;
          onDropText(formatTerminalImagePaths(paths, platform));
        } catch (error) {
          log.warn('Prompt file drop failed', { error });
        }
      })();
    },
    [accepts, onDropText, workspaceId]
  );

  return { isDragOver, dropHandlers: { onDragOver, onDragEnter, onDragLeave, onDrop } };
}
