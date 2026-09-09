import { getProjectManagerStore } from '@core/features/projects/api/browser/stores/project-selectors';
import { useOpenModal } from '@core/manifests/browser/modal-api';

export function useConfirmDeleteProject() {
  const openConfirmDeleteProject = useOpenModal('confirmActionModal');

  return async ({
    projectId,
    projectLabel,
    onDeleted,
  }: {
    projectId: string;
    projectLabel: string;
    onDeleted?: () => void;
  }) => {
    const outcome = await openConfirmDeleteProject({
      title: 'Remove project',
      description: `"${projectLabel}" will be removed from Hardcore. The project folder and model files will stay on the filesystem.`,
      confirmLabel: 'Remove',
    });
    if (!outcome.success) return;
    void getProjectManagerStore().deleteProject(projectId);
    onDeleted?.();
  };
}
