import { Button, Dialog, ModalLayout } from '@emdash/ui/react/primitives';
import { ArrowLeftIcon } from 'lucide-react';
import { useModalController } from '@core/manifests/browser/modal-api';
import { defineModal } from '@core/primitives/modals/react';
import type { SshConfig } from '@core/primitives/ssh/api';
import { MachineFormActions, MachineFormFields, useMachineForm } from './machine-form';

export interface AddMachineModalProps {
  initialConfig?: SshConfig;
  dismissControl?: 'back' | 'close';
}

const MACHINE_MODAL_FORM_ID = 'add-ssh-conn-form';

export function AddMachineModal({ initialConfig, dismissControl = 'back' }: AddMachineModalProps) {
  const modal = useModalController('addSshConnModal');
  const showBackButton = dismissControl === 'back';
  const controller = useMachineForm({
    initialConfig,
    onSaved: (connectionId) => modal.complete({ connectionId }),
  });

  return (
    <ModalLayout
      header={
        <Dialog.Header
          showCloseButton={!showBackButton}
          className="-mt-2 w-full flex-row items-center justify-between gap-2"
        >
          <div className={`flex items-center gap-2 ${showBackButton ? '-ml-2' : ''}`}>
            {showBackButton && (
              <Button variant="ghost" size="xs" icon onClick={modal.dismiss}>
                <ArrowLeftIcon className="h-4 w-4" />
              </Button>
            )}
            <Dialog.Title>
              {controller.isEditing ? 'Edit SSH Connection' : 'Add SSH Connection'}
            </Dialog.Title>
          </div>
        </Dialog.Header>
      }
      footer={
        <Dialog.Footer>
          <MachineFormActions
            controller={controller}
            formId={MACHINE_MODAL_FORM_ID}
            cancelAction={
              !showBackButton ? (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={modal.dismiss}
                  disabled={controller.isSubmitting}
                >
                  Cancel
                </Button>
              ) : undefined
            }
          />
        </Dialog.Footer>
      }
    >
      <Dialog.Body className="max-h-[calc(100dvh-10rem)] overflow-y-auto">
        <MachineFormFields controller={controller} formId={MACHINE_MODAL_FORM_ID} />
      </Dialog.Body>
    </ModalLayout>
  );
}

export const addMachineModal = defineModal<{ connectionId: string }>()({
  id: 'addSshConnModal',
  component: AddMachineModal,
});
