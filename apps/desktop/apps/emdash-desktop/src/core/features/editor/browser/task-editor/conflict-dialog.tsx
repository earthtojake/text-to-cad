import { Button, Dialog } from '@emdash/ui/react/primitives';
import { useEffect } from 'react';
import { useModalController } from '@core/manifests/browser/modal-api';
import { defineModal } from '@core/primitives/modals/react';

export type ConflictDialogArgs = {
  filePath: string;
};

export function ConflictDialog({ filePath }: ConflictDialogArgs) {
  const { complete, setCloseGuard } = useModalController('conflictDialog');
  const shortPath = filePath.split('/').slice(-2).join('/');

  useEffect(() => {
    setCloseGuard(true);
    return () => setCloseGuard(false);
  }, [setCloseGuard]);

  return (
    <>
      <Dialog.Header showCloseButton={false}>
        <Dialog.Title>File Modified Externally</Dialog.Title>
        <Dialog.Description>
          <code className="rounded bg-background-2 px-1 py-0.5 text-xs">{shortPath}</code> was
          changed outside the editor while you have unsaved edits. What would you like to do?
        </Dialog.Description>
      </Dialog.Header>
      <Dialog.Footer className="gap-2">
        <Button variant="secondary" onClick={() => complete(false)}>
          Keep Mine
        </Button>
        <Button variant="primary" onClick={() => complete(true)}>
          Accept Incoming
        </Button>
      </Dialog.Footer>
    </>
  );
}

export const conflictDialog = defineModal<boolean>()({
  id: 'conflictDialog',
  component: ConflictDialog,
  size: 'sm',
});
