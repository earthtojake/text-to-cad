import { SettingsCard } from '@emdash/ui/react/patterns';
import { SeparatedList, Switch } from '@emdash/ui/react/primitives';
import React from 'react';
import { useAppSettingsKey } from '@core/features/settings/api/browser/use-app-settings-key';
import { ResetToDefaultButton } from './ResetToDefaultButton';
import { SettingRow } from './SettingRow';

const InterfaceSettingsCard: React.FC = () => {
  const {
    value: interfaceSettings,
    update,
    isLoading: loading,
    isSaving: saving,
    isFieldOverridden,
    resetField,
  } = useAppSettingsKey('interface');

  const hideContextBar = interfaceSettings?.hideContextBar ?? false;

  return (
    <SettingsCard>
      <SeparatedList gap="1rem" direction="column">
        <SettingRow
          title="Context bar"
          description="Hide the on-screen context trigger. The keyboard shortcut still works."
          control={
            <>
              <ResetToDefaultButton
                visible={isFieldOverridden('hideContextBar')}
                defaultLabel="shown"
                onReset={() => resetField('hideContextBar')}
                disabled={loading || saving}
              />
              <Switch
                checked={hideContextBar}
                disabled={loading || saving}
                onCheckedChange={(checked) => update({ hideContextBar: checked })}
              />
            </>
          }
        />
      </SeparatedList>
    </SettingsCard>
  );
};

export default InterfaceSettingsCard;
