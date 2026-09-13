import { Button, Checkbox, Dialog } from '@emdash/ui/react/primitives';
import { useState, type ReactNode } from 'react';
import { useModalController } from '@core/manifests/browser/modal-api';
import { ConfirmButton } from '@core/primitives/keybindings/browser/confirm-button';
import { defineModal } from '@core/primitives/modals/react';

export type ConfirmActionDialogArgs = {
  title: string;
  description: ReactNode;
  confirmLabel?: string;
  variant?: 'destructive' | 'default';
  /** Optional secondary choice surfaced with the confirmation. */
  checkbox?: { label: string; defaultChecked?: boolean };
};

export type ConfirmActionDialogResult = { checked: boolean } | undefined;

export function ConfirmActionDialog({
  title,
  description,
  confirmLabel = 'Confirm',
  variant = 'destructive',
  checkbox,
}: ConfirmActionDialogArgs) {
  const controller = useModalController('confirmActionModal');
  const [checked, setChecked] = useState(checkbox?.defaultChecked ?? false);

  return (
    <>
      <Dialog.Header showCloseButton={false}>
        <Dialog.Title>{title}</Dialog.Title>
      </Dialog.Header>
      <Dialog.Body className="flex flex-col gap-3 pt-0">
        {typeof description === 'string' ? <p>{description}</p> : description}
        {checkbox && (
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <Checkbox checked={checked} onCheckedChange={(value) => setChecked(Boolean(value))} />
            {checkbox.label}
          </label>
        )}
      </Dialog.Body>
      <Dialog.Footer>
        <Button variant="secondary" onClick={controller.dismiss}>
          Cancel
        </Button>
        <ConfirmButton
          variant={variant === 'default' ? 'primary' : variant}
          onClick={() => controller.complete(checkbox ? { checked } : undefined)}
        >
          {confirmLabel}
        </ConfirmButton>
      </Dialog.Footer>
    </>
  );
}

export const confirmActionModal = defineModal<ConfirmActionDialogResult>()({
  id: 'confirmActionModal',
  component: ConfirmActionDialog,
  size: 'xs',
});
