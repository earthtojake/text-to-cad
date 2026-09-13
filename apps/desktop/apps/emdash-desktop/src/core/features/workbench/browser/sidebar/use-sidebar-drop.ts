import { useToast } from '@emdash/ui/react/primitives';
import { useCallback, useRef, useState } from 'react';
import { getProjectsWireClient } from '@core/features/projects/api/browser/client';
import { getProjectManagerStore } from '@core/features/projects/api/browser/stores/project-selectors';
import { projectViewDef } from '@core/features/projects/contributions/views';
import {
  getDraggedFilePaths,
  hasDraggedFiles,
} from '@core/primitives/drag-files/browser/drag-files';
import { log } from '@core/primitives/logging/browser/logger';
import { useNavigate } from '@core/primitives/navigation/browser/navigation-hooks';
import { basenameFromAnyPath } from '@core/primitives/path-name/api';

export function useSidebarDrop() {
  const [isDragOver, setIsDragOver] = useState(false);
  const dragCounter = useRef(0);
  const { navigate } = useNavigate();
  const { toast } = useToast();

  const onDragOver = useCallback((e: React.DragEvent) => {
    if (!hasDraggedFiles(e.dataTransfer)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  }, []);

  const onDragEnter = useCallback((e: React.DragEvent) => {
    if (!hasDraggedFiles(e.dataTransfer)) return;
    e.preventDefault();
    dragCounter.current++;
    setIsDragOver(true);
  }, []);

  const onDragLeave = useCallback((e: React.DragEvent) => {
    if (!hasDraggedFiles(e.dataTransfer)) return;
    e.preventDefault();
    dragCounter.current--;
    if (dragCounter.current <= 0) {
      dragCounter.current = 0;
      setIsDragOver(false);
    }
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      dragCounter.current = 0;
      setIsDragOver(false);

      const filePaths = getDraggedFilePaths(e.dataTransfer);
      if (filePaths.length === 0) return;

      const projectManager = getProjectManagerStore();

      void Promise.allSettled(
        filePaths.map(async (filePath) => {
          try {
            const status = await (
              await getProjectsWireClient()
            ).inspectProjectPath({
              type: 'local',
              path: filePath,
            });
            if (status.error) {
              toast.error('Cannot add project', {
                description: `Could not inspect ${basenameFromAnyPath(filePath)}: ${status.error.message}`,
              });
              return null;
            }
            if (!status.isDirectory) {
              toast.error('Cannot add project', {
                description: 'Drop a folder to add it as a project.',
              });
              return null;
            }
            const name = basenameFromAnyPath(filePath);
            return await projectManager.createProject(
              { type: 'local' },
              {
                mode: 'pick',
                name,
                path: filePath,
                initGitRepository: false,
              }
            );
          } catch (err) {
            log.error('Failed to add dropped project:', err);
            toast.error('Cannot add project', {
              description: `Failed to add ${basenameFromAnyPath(filePath)} as a project.`,
            });
            return null;
          }
        })
      ).then((results) => {
        const projectIds = results.flatMap((r) =>
          r.status === 'fulfilled' && r.value != null ? [r.value] : []
        );
        const firstProjectId = projectIds[0];

        if (firstProjectId) {
          navigate(projectViewDef({ projectId: firstProjectId }));
        }

        if (projectIds.length > 1) {
          toast('Projects added', { description: `${projectIds.length} projects added.` });
        }
      });
    },
    [navigate, toast]
  );

  return { isDragOver, onDragOver, onDragEnter, onDragLeave, onDrop };
}
