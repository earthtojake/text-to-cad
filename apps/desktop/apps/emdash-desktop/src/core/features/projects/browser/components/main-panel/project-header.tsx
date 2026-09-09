import { StatusIcon } from '@emdash/ui/react/components';
import { EntityHeader } from '@emdash/ui/react/patterns';
import { Button, DropdownMenu, Heading } from '@emdash/ui/react/primitives';
import { EllipsisIcon, FolderInput, FolderOpen, Trash2 } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import {
  getProjectStore,
  projectDisplayName,
} from '@core/features/projects/api/browser/stores/project-selectors';
import { useConfirmDeleteProject } from '@core/features/projects/contributions/browser/use-confirm-delete-project';

export const ProjectHeader = observer(function ProjectHeader({ projectId }: { projectId: string }) {
  const store = getProjectStore(projectId);
  const project = store?.data;
  const displayName = projectDisplayName(store) ?? 'this project';
  const confirmDeleteProject = useConfirmDeleteProject();

  if (!project) return null;

  const ProjectIcon = project.type === 'ssh' ? FolderInput : FolderOpen;

  return (
    <EntityHeader
      icon={
        <StatusIcon
          aria-hidden
          severity="neutral"
          size="lg"
          icon={<ProjectIcon aria-hidden size={20} />}
        />
      }
      title={
        <Heading level={1} tone="default" className="min-w-0 flex-1 truncate">
          {displayName}
        </Heading>
      }
      actions={
        <DropdownMenu.Root>
          <DropdownMenu.Trigger
            render={
              <Button
                type="button"
                variant="secondary"
                size="xs"
                icon
                aria-label="Project actions"
              />
            }
          >
            <EllipsisIcon />
          </DropdownMenu.Trigger>
          <DropdownMenu.Content align="end">
            <DropdownMenu.Item
              variant="destructive"
              onClick={() => {
                void confirmDeleteProject({ projectId, projectLabel: displayName });
              }}
            >
              <Trash2 />
              Remove project
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Root>
      }
    />
  );
});
