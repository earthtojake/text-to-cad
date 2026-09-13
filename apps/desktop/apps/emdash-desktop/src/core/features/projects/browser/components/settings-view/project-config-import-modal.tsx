import { err, type Result } from '@emdash/shared';
import { Button, Dialog, Field, RadioGroup, Select } from '@emdash/ui/react/primitives';
import { Check, Loader2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useModalController } from '@core/manifests/browser/modal-api';
import { ConfirmButton } from '@core/primitives/keybindings/browser/confirm-button';
import { defineModal } from '@core/primitives/modals/react';
import type {
  MigrateProjectConfigRequest,
  ProjectConfigMigration,
  ProjectConfigMigrationDestination,
  ProjectConfigMigrationProvider,
} from '@core/primitives/project-settings/api';
import type {
  MigrateProjectConfigResult,
  ProjectSettingsError,
} from '../../../api/project-settings-page';
import { SHAREABLE_FIELD_DESCRIPTOR_BY_ID } from './shareable-project-settings-fields';

type ImportStatus = 'idle' | 'importing' | 'imported' | 'error';

export type ProjectConfigImportModalArgs = {
  migrations: ProjectConfigMigration[];
  migrateProjectConfig: (
    request: MigrateProjectConfigRequest
  ) => Promise<Result<MigrateProjectConfigResult, ProjectSettingsError>>;
};

function unknownErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function fieldLabel(field: ProjectConfigMigration['fields'][number]): string {
  return SHAREABLE_FIELD_DESCRIPTOR_BY_ID[field].modalLabel;
}

function filesLabel(files: string[]): string {
  return files.length === 1 ? files[0] : files.join(', ');
}

export function ProjectConfigImportModal({
  migrations,
  migrateProjectConfig,
}: ProjectConfigImportModalArgs) {
  const modal = useModalController('projectConfigImportModal');
  const [selectedProvider, setSelectedProvider] = useState<ProjectConfigMigrationProvider>(
    migrations[0]?.provider ?? 'conductor'
  );
  const [destination, setDestination] = useState<ProjectConfigMigrationDestination>('local');
  const [status, setStatus] = useState<ImportStatus>('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const selectedMigration = useMemo(
    () => migrations.find((migration) => migration.provider === selectedProvider) ?? migrations[0],
    [migrations, selectedProvider]
  );
  const description =
    migrations.length === 1 && selectedMigration
      ? `Found configuration file from ${selectedMigration.label} that can be imported into Hardcore.`
      : 'Found configuration files that can be imported into Hardcore.';

  const disabled = !selectedMigration || status === 'importing' || status === 'imported';

  async function handleImport() {
    if (!selectedMigration) return;

    setStatus('importing');
    setErrorMessage(null);
    const result = await migrateProjectConfig({
      provider: selectedMigration.provider,
      destination,
    }).catch((error) =>
      err({
        type: 'write-config-failed' as const,
        message: unknownErrorMessage(error),
      })
    );

    if (result.success) {
      setStatus('imported');
      modal.complete(result.data);
      return;
    }

    setErrorMessage(
      result.error.type === 'write-config-failed'
        ? result.error.message
        : 'Failed to import project config.'
    );
    setStatus('error');
  }

  return (
    <>
      <Dialog.Header showCloseButton={false}>
        <Dialog.Title>Import project config</Dialog.Title>
      </Dialog.Header>
      <Dialog.Body className="pt-0">
        <Field.Group>
          <p className="text-sm text-foreground-muted">{description}</p>
          {migrations.length > 1 && (
            <Field.Root>
              <Select.Root
                value={selectedMigration?.provider ?? ''}
                onValueChange={(value) =>
                  setSelectedProvider(value as ProjectConfigMigrationProvider)
                }
              >
                <Select.Trigger className="w-full min-w-0">
                  <span className="min-w-0 truncate">
                    {selectedMigration?.label ?? 'Select config'}
                  </span>
                </Select.Trigger>
                <Select.Content align="start" alignItemWithTrigger={false} sideOffset={6}>
                  {migrations.map((migration) => (
                    <Select.Item key={migration.provider} value={migration.provider}>
                      {migration.label} ({filesLabel(migration.files)})
                    </Select.Item>
                  ))}
                </Select.Content>
              </Select.Root>
            </Field.Root>
          )}

          {selectedMigration ? (
            <div className="space-y-2 text-sm">
              <p>Settings to import</p>
              <ul className="list-disc space-y-1 pl-5 text-foreground-muted">
                {selectedMigration.fields.map((field) => (
                  <li key={field}>{fieldLabel(field)}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="space-y-2 text-sm">
            <p>Save to</p>
            <RadioGroup.Root
              value={destination}
              onValueChange={(value) => setDestination(value as ProjectConfigMigrationDestination)}
              className="grid"
            >
              <label className="flex items-center gap-3 rounded-md text-sm">
                <RadioGroup.Item value="local" className="translate-y-px" />
                <span className="flex min-w-0 flex-row gap-1.5">
                  <p>Personal settings</p>
                  <p className="text-foreground-muted">– stored only on this machine</p>
                </span>
              </label>
              <label className="flex items-center gap-3 rounded-md text-sm">
                <RadioGroup.Item value="shared" className="translate-y-px" />
                <span className="flex min-w-0 flex-row gap-1.5">
                  <p>Legacy project config</p>
                  <p className="text-foreground-muted">– commit to share with team</p>
                </span>
              </label>
            </RadioGroup.Root>
          </div>
          {status === 'error' ? (
            <p className="text-xs text-foreground-error">{errorMessage}</p>
          ) : null}
        </Field.Group>
      </Dialog.Body>
      <Dialog.Footer>
        <Button variant="secondary" onClick={modal.dismiss} disabled={status === 'importing'}>
          {status === 'imported' ? 'Close' : 'Cancel'}
        </Button>
        <ConfirmButton variant="primary" onClick={() => void handleImport()} disabled={disabled}>
          <span className="inline-flex items-center justify-center gap-1.5">
            {status === 'importing' && <Loader2 className="size-4 animate-spin" aria-hidden />}
            {status === 'imported' && <Check className="size-4" aria-hidden />}
            {status === 'importing'
              ? 'Importing...'
              : status === 'imported'
                ? 'Imported'
                : 'Import'}
          </span>
        </ConfirmButton>
      </Dialog.Footer>
    </>
  );
}

export const projectConfigImportModal = defineModal<MigrateProjectConfigResult>()({
  id: 'projectConfigImportModal',
  component: ProjectConfigImportModal,
  size: 'md',
});
