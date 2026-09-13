import { SettingsCard } from '@emdash/ui/react/patterns';
import { Input, SeparatedList, Switch } from '@emdash/ui/react/primitives';
import React from 'react';
import { useAppSettingsKey } from '@core/features/settings/api/browser/use-app-settings-key';
import { normalizeBranchPrefix } from '@core/primitives/tasks/api';
import { ResetToDefaultButton } from './ResetToDefaultButton';
import { SettingRow } from './SettingRow';

const RepositorySettingsCard: React.FC = () => {
  const {
    value: project,
    update: updateProject,
    isLoading: projectLoading,
    isSaving: projectSaving,
    isFieldOverridden: isProjectFieldOverridden,
    resetField: resetProjectField,
  } = useAppSettingsKey('project');
  const branchPrefix = project?.branchPrefix ?? '';
  const appendRandomBranchSuffix = project?.appendRandomBranchSuffix ?? true;
  const pushOnCreate = project?.pushOnCreate ?? true;
  const projectBusy = projectLoading || projectSaving;

  return (
    <SettingsCard>
      <SeparatedList gap="1rem" direction="column">
        <div className="grid gap-2">
          <div className="flex items-center gap-2">
            <Input
              key={branchPrefix}
              defaultValue={branchPrefix}
              onBlur={(e) => {
                const next = normalizeBranchPrefix(e.currentTarget.value);
                e.currentTarget.value = next;
                if (next !== branchPrefix) {
                  updateProject({ branchPrefix: next });
                }
              }}
              placeholder="Branch prefix"
              aria-label="Branch prefix"
              disabled={projectBusy}
              className="flex-1"
            />
            <ResetToDefaultButton
              visible={isProjectFieldOverridden('branchPrefix')}
              defaultLabel="hardcore"
              onReset={() => resetProjectField('branchPrefix')}
              disabled={projectBusy}
            />
          </div>
          <div className="text-xs text-foreground-passive">
            Leave empty to create branches without a prefix.
          </div>
        </div>
        <SettingRow
          title="Random branch suffix"
          description="Add a random suffix to branch names."
          control={
            <>
              <ResetToDefaultButton
                visible={isProjectFieldOverridden('appendRandomBranchSuffix')}
                defaultLabel="on"
                onReset={() => resetProjectField('appendRandomBranchSuffix')}
                disabled={projectBusy}
              />
              <Switch
                checked={appendRandomBranchSuffix}
                onCheckedChange={(checked) => updateProject({ appendRandomBranchSuffix: checked })}
                disabled={projectBusy}
                aria-label="Append random branch suffix"
              />
            </>
          }
        />
        <SettingRow
          title="Auto-push on create"
          description="Push the new branch to the selected project remote and set upstream after creation."
          control={
            <>
              <ResetToDefaultButton
                visible={isProjectFieldOverridden('pushOnCreate')}
                defaultLabel="on"
                onReset={() => resetProjectField('pushOnCreate')}
                disabled={projectBusy}
              />
              <Switch
                checked={pushOnCreate}
                onCheckedChange={(checked) => updateProject({ pushOnCreate: checked })}
                disabled={projectBusy}
                aria-label="Enable automatic push on create"
              />
            </>
          }
        />
      </SeparatedList>
    </SettingsCard>
  );
};

export default RepositorySettingsCard;
