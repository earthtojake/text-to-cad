import { err, type Result } from '@emdash/shared';
import { ComboboxPopover } from '@emdash/ui/react/components';
import { Button, Checkbox, Dialog, Field } from '@emdash/ui/react/primitives';
import { Check, Loader2 } from 'lucide-react';
import { useState } from 'react';
import { useModalController } from '@core/manifests/browser/modal-api';
import { ConfirmButton } from '@core/primitives/keybindings/browser/confirm-button';
import { defineModal } from '@core/primitives/modals/react';
import type {
  ProjectSettingsWriteTarget,
  ProjectSettingsWriteTargetOption,
  ShareableProjectSettingsWriteField,
  WriteProjectConfigRequest,
} from '@core/primitives/project-settings/api';
import type { ProjectSettingsError, ProjectSettingsPage } from '../../../api/project-settings-page';
import { SHAREABLE_FIELD_DESCRIPTOR_BY_ID } from './shareable-project-settings-fields';

type WriteStatus = 'idle' | 'writing' | 'written' | 'error';

export type ShareProjectConfigModalArgs = {
  availableFields: ShareableProjectSettingsWriteField[];
  defaultFields: ShareableProjectSettingsWriteField[];
  initialTarget: string;
  targets: ProjectSettingsWriteTargetOption[];
  writeConfigToRepo: (
    request: WriteProjectConfigRequest
  ) => Promise<Result<ProjectSettingsPage, ProjectSettingsError>>;
};

type ShareProjectConfigModalResult = {
  fields: ShareableProjectSettingsWriteField[];
  page: ProjectSettingsPage;
};

export function projectConfigTargetValue(target: ProjectSettingsWriteTargetOption): string {
  if (target.type === 'project') return 'project:repository';
  if (target.type === 'task') return `task:${target.taskId}`;
  return `workspace:${target.workspaceId}`;
}

function parseTargetValue(
  target: ProjectSettingsWriteTargetOption | null
): ProjectSettingsWriteTarget | null {
  if (!target) return null;
  if (target.type === 'project') return { type: 'project' };
  if (target.type === 'task') return { type: 'task', taskId: target.taskId };
  return { type: 'workspace', workspaceId: target.workspaceId };
}

export function projectConfigWriteFieldLabel(field: ShareableProjectSettingsWriteField): string {
  return SHAREABLE_FIELD_DESCRIPTOR_BY_ID[field].modalLabel;
}

function unknownErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function ShareProjectConfigModal({
  availableFields,
  defaultFields,
  initialTarget,
  targets,
  writeConfigToRepo,
}: ShareProjectConfigModalArgs) {
  const modal = useModalController('shareProjectConfigModal');
  const firstTarget = targets[0] ?? null;
  const initialTargetOption = targets.find(
    (target) => projectConfigTargetValue(target) === initialTarget
  );
  const [selectedTarget, setSelectedTarget] = useState<ProjectSettingsWriteTargetOption | null>(
    initialTargetOption ?? firstTarget
  );
  const [selectedFields, setSelectedFields] =
    useState<ShareableProjectSettingsWriteField[]>(defaultFields);
  const [status, setStatus] = useState<WriteStatus>('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const selectedTargetValue = selectedTarget ? projectConfigTargetValue(selectedTarget) : '';
  const selectedTargetLabel = selectedTarget?.label ?? 'Select a working copy';

  const disabled = status === 'writing' || selectedFields.length === 0 || !selectedTarget;

  function toggleField(field: ShareableProjectSettingsWriteField, checked: boolean) {
    setStatus((current) => (current === 'idle' ? current : 'idle'));
    setErrorMessage(null);
    setSelectedFields((current) =>
      checked ? [...current, field] : current.filter((candidate) => candidate !== field)
    );
  }

  async function handleWrite() {
    const target = parseTargetValue(selectedTarget);
    if (!target) return;

    setStatus('writing');
    setErrorMessage(null);
    const fields = selectedFields;
    const result = await writeConfigToRepo({
      target,
      fields,
    }).catch((error) =>
      err({
        type: 'write-config-failed' as const,
        message: unknownErrorMessage(error),
      })
    );

    if (result.success) {
      setStatus('written');
      modal.complete({ fields, page: result.data });
      return;
    }

    setErrorMessage(
      result.error.type === 'write-config-failed' ? result.error.message : 'Failed to write config.'
    );
    setStatus('error');
  }

  return (
    <>
      <Dialog.Header showCloseButton={false}>
        <Dialog.Title>Share settings with your team</Dialog.Title>
      </Dialog.Header>
      <Dialog.Body className="pt-0">
        <Field.Group>
          <p className="text-sm text-foreground-muted">
            This copies the selected personal settings from this machine to .hardcore.json in the
            chosen working directory. Commit that file so teammates get the same project defaults
            after pulling.
          </p>
          <Field.Root>
            <Field.Label>Write to</Field.Label>
            <ComboboxPopover
              items={targets}
              value={selectedTargetValue}
              onValueChange={(value) => {
                setSelectedTarget(
                  targets.find((target) => projectConfigTargetValue(target) === value) ?? null
                );
              }}
              itemToKey={projectConfigTargetValue}
              itemToLabel={(target) => target.label}
              filter={(target, query) => {
                const normalizedQuery = query.toLowerCase();
                return (
                  target.label.toLowerCase().includes(normalizedQuery) ||
                  target.path.toLowerCase().includes(normalizedQuery)
                );
              }}
              appearance="input"
              className="w-full min-w-0"
              contentWidth="trigger"
              searchPlaceholder="Search working copies..."
              renderTrigger={() => (
                <div className="flex min-w-0 flex-1 items-center gap-2 text-left">
                  <span className="min-w-0 truncate">{selectedTargetLabel}</span>
                </div>
              )}
              renderItem={(target) => (
                <div
                  className="flex min-w-0 flex-1 flex-col gap-0.5"
                  title={`${target.label} ${target.path}`}
                >
                  <span className="min-w-0 truncate">{target.label}</span>
                  <span className="min-w-0 truncate text-xs text-foreground-muted">
                    {target.path}
                  </span>
                </div>
              )}
            />
          </Field.Root>

          <Field.Root>
            <Field.Label>Settings to share</Field.Label>
            <div className="grid grid-cols-2 gap-2">
              {availableFields.map((field) => (
                <label key={field} className="flex items-center gap-2 rounded-md py-2 text-sm">
                  <Checkbox
                    checked={selectedFields.includes(field)}
                    onCheckedChange={(checked) => toggleField(field, checked === true)}
                  />
                  <span>{projectConfigWriteFieldLabel(field)}</span>
                </label>
              ))}
            </div>
          </Field.Root>
          {status === 'error' ? (
            <p className="text-xs text-foreground-error">{errorMessage}</p>
          ) : null}
        </Field.Group>
      </Dialog.Body>
      <Dialog.Footer>
        <Button variant="secondary" onClick={modal.dismiss} disabled={status === 'writing'}>
          Cancel
        </Button>
        <ConfirmButton variant="primary" onClick={() => void handleWrite()} disabled={disabled}>
          <span className="inline-flex min-w-20 items-center justify-center gap-1.5">
            {status === 'writing' && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
            {status === 'written' && <Check className="size-4" aria-hidden="true" />}
            {status === 'writing'
              ? 'Writing...'
              : status === 'written'
                ? 'Wrote .hardcore.json'
                : 'Write .hardcore.json'}
          </span>
        </ConfirmButton>
      </Dialog.Footer>
    </>
  );
}

export const shareProjectConfigModal = defineModal<ShareProjectConfigModalResult>()({
  id: 'shareProjectConfigModal',
  component: ShareProjectConfigModal,
  size: 'md',
});
