import { Dialog, ModalLayout } from '@emdash/ui/react/primitives';
import { FilePlus2, FolderOpen, Loader2 } from 'lucide-react';
import type { ReactNode } from 'react';
import { useModalController } from '@core/manifests/browser/modal-api';
import { defineModal } from '@core/primitives/modals/react';
import { cn } from '@core/primitives/styling/browser/cn';
import { useOpenProjectFolder, type OpenProjectFolderMode } from '../../open-project-folder';

export type Strategy = 'local' | 'ssh';
export type Mode = 'pick' | 'new' | 'clone';

export interface AddProjectModalProps {
  strategy?: Strategy;
  mode?: Mode;
  connectionId?: string;
}

/** Command-palette fallback for the same two choices shown in AddProjectMenu. */
export function AddProjectModal(_props: AddProjectModalProps) {
  const modal = useModalController('addProjectModal');
  const projectFolder = useOpenProjectFolder();

  const choose = async (mode: OpenProjectFolderMode) => {
    const projectId = await projectFolder.open(mode);
    if (projectId) modal.dismiss();
  };

  return (
    <ModalLayout
      header={
        <Dialog.Header showCloseButton={!projectFolder.busy}>
          <Dialog.Title>Add project</Dialog.Title>
        </Dialog.Header>
      }
      footer={null}
    >
      <Dialog.Body className="gap-1 p-2">
        <ProjectChoice
          title="Start from scratch"
          description="Create a new local project folder."
          icon={projectFolder.busy ? <Loader2 className="animate-spin" /> : <FilePlus2 />}
          disabled={projectFolder.busy}
          onClick={() => void choose('scratch')}
        />
        <ProjectChoice
          title="Use an existing folder"
          description="Open a folder that already contains your engineering files."
          icon={<FolderOpen />}
          disabled={projectFolder.busy}
          onClick={() => void choose('existing')}
        />
      </Dialog.Body>
    </ModalLayout>
  );
}

function ProjectChoice({
  title,
  description,
  icon,
  disabled,
  onClick,
}: {
  title: string;
  description: string;
  icon: ReactNode;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      className={cn(
        'flex w-full items-start gap-3 rounded-lg px-3 py-3 text-left transition-colors',
        'hover:bg-background-secondary focus-visible:bg-background-secondary focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring',
        disabled && 'cursor-not-allowed opacity-50'
      )}
      onClick={onClick}
    >
      <span className="mt-0.5 shrink-0 text-foreground-muted [&>svg]:size-4">{icon}</span>
      <span className="min-w-0">
        <span className="block text-sm font-medium text-foreground">{title}</span>
        <span className="mt-0.5 block text-xs text-foreground-muted">{description}</span>
      </span>
    </button>
  );
}

export const addProjectModal = defineModal<void>()({
  id: 'addProjectModal',
  component: AddProjectModal,
});
