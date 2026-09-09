import { ComboboxPopover } from '@emdash/ui/react/components';
import { Button, Dialog, Field, ModalLayout, toast } from '@emdash/ui/react/primitives';
import { observer } from 'mobx-react-lite';
import { useId, useState } from 'react';
import { getMachinesStore } from '@core/features/machines/contributions/app-stores';
import { getProjectManagerStore } from '@core/features/projects/api/browser/stores/project-selectors';
import { useModalController } from '@core/manifests/browser/modal-api';
import { ConfirmButton } from '@core/primitives/keybindings/browser/confirm-button';
import { defineModal } from '@core/primitives/modals/react';
import type { SshConfig } from '@core/primitives/ssh/api';

type MachineOption = SshConfig & { id: string };

export const RelinkProjectModal = observer(function RelinkProjectModal({
  projectId,
}: {
  projectId: string;
}) {
  const modal = useModalController('relinkProjectModal');
  const machineFieldId = useId();
  const machines = getMachinesStore().connections.filter(
    (connection): connection is MachineOption => connection.id !== undefined
  );
  const [connectionId, setConnectionId] = useState<string | null>(null);
  const [isRelinking, setIsRelinking] = useState(false);
  const selectedConnectionId = connectionId ?? machines[0]?.id ?? null;

  const relink = async () => {
    if (!selectedConnectionId || isRelinking) return;
    setIsRelinking(true);
    try {
      await getProjectManagerStore().updateProjectConnection(projectId, selectedConnectionId);
      modal.complete();
    } catch (error) {
      toast.error('Failed to relink Project', {
        description: error instanceof Error ? error.message : String(error),
      });
      setIsRelinking(false);
    }
  };

  return (
    <ModalLayout
      header={
        <Dialog.Header>
          <Dialog.Title>Relink Project</Dialog.Title>
          <Dialog.Description>
            Choose the Machine that hosts this Project&apos;s repository.
          </Dialog.Description>
        </Dialog.Header>
      }
      footer={
        <Dialog.Footer>
          <Button type="button" variant="secondary" disabled={isRelinking} onClick={modal.dismiss}>
            Cancel
          </Button>
          <ConfirmButton
            type="button"
            variant="primary"
            disabled={!selectedConnectionId || isRelinking}
            onClick={() => void relink()}
          >
            {isRelinking ? 'Relinking…' : 'Relink'}
          </ConfirmButton>
        </Dialog.Footer>
      }
    >
      <Dialog.Body>
        <Field.Root>
          <Field.Label htmlFor={machineFieldId}>Machine</Field.Label>
          {machines.length > 0 ? (
            <ComboboxPopover
              items={machines}
              value={selectedConnectionId}
              onValueChange={setConnectionId}
              itemToKey={(machine) => machine.id}
              itemToLabel={(machine) => machine.name}
              renderTrigger={(machine) => machine?.name ?? 'Select a Machine'}
              renderItem={(machine) => machine.name}
              triggerId={machineFieldId}
              triggerTitle={(machine) =>
                machine ? `Relink to ${machine.name}` : 'Select a Machine'
              }
              searchPlaceholder="Search Machines…"
              appearance="input"
              contentWidth="trigger"
            />
          ) : (
            <p role="status" className="text-sm text-foreground-muted">
              Add a Machine before relinking this Project.
            </p>
          )}
        </Field.Root>
      </Dialog.Body>
    </ModalLayout>
  );
});

export const relinkProjectModal = defineModal<void>()({
  id: 'relinkProjectModal',
  component: RelinkProjectModal,
  size: 'sm',
});
