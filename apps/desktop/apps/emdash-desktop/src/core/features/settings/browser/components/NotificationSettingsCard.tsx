import { SettingsCard } from '@emdash/ui/react/patterns';
import { Button, Select, SeparatedList, Switch, Tooltip } from '@emdash/ui/react/primitives';
import { FolderOpen, Play } from 'lucide-react';
import React from 'react';
import { useAppSettingsKey } from '@core/features/settings/api/browser/use-app-settings-key';
import { configureSoundPlayer, soundPlayer } from '@core/features/settings/browser/sound-player';
import type { NotificationSettings } from '@core/primitives/app-settings/api';
import { getHostClient } from '@core/primitives/desktop-host/browser/host-client';
import { cn } from '@core/primitives/styling/browser/cn';
import { ResetToDefaultButton } from './ResetToDefaultButton';
import { SettingRow } from './SettingRow';

const getFileName = (path: string): string => {
  const trimmed = path.trim();
  if (!trimmed) return '';
  const parts = trimmed.split(/[/\\]/);
  return parts[parts.length - 1] || trimmed;
};

function PreviewSoundButton({
  path,
  disabled,
}: {
  path: string;
  disabled?: boolean;
}): React.JSX.Element {
  return (
    <Tooltip.Provider delay={150}>
      <Tooltip.Root>
        <Tooltip.Trigger
          render={
            <Button
              type="button"
              variant="ghost"
              size="sm"
              icon
              className="text-foreground-muted hover:text-foreground"
              disabled={disabled}
              onClick={() => soundPlayer.preview(path)}
              aria-label="Preview sound"
            >
              <Play className="size-3.5" />
            </Button>
          }
        />
        <Tooltip.Content side="top">Preview</Tooltip.Content>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}

const NotificationSettingsCard: React.FC = () => {
  const {
    value: notifications,
    update,
    isLoading: loading,
    isFieldOverridden,
    resetField,
  } = useAppSettingsKey('notifications');

  const currentNotifications: NotificationSettings = notifications ?? {
    enabled: true,
    sound: true,
    customSoundPath: '',
    osNotifications: true,
    soundFocusMode: 'always',
  };
  const customSoundPath = currentNotifications.customSoundPath?.trim() ?? '';

  const updateNotifications = (partial: Partial<NotificationSettings>) => {
    configureSoundPlayer({ ...currentNotifications, ...partial });
    update(partial);
  };

  const resetNotificationField = <K extends keyof NotificationSettings>(
    field: K,
    value: NotificationSettings[K]
  ) => {
    configureSoundPlayer({ ...currentNotifications, [field]: value });
    resetField(field);
  };

  const chooseCustomSound = async () => {
    const result = await (
      await getHostClient()
    ).openSelectAudioFileDialog({
      title: 'Choose custom sound',
      message: 'Select an audio file to play for agent events',
    });
    if (result) updateNotifications({ customSoundPath: result });
  };

  return (
    <SettingsCard>
      <SeparatedList gap="0.75rem" direction="column">
        <SettingRow
          title="Notifications"
          description="Get notified when agents need your attention."
          control={
            <>
              <ResetToDefaultButton
                visible={isFieldOverridden('enabled')}
                defaultLabel="on"
                onReset={() => resetField('enabled')}
                disabled={loading}
              />
              <Switch
                checked={notifications?.enabled ?? true}
                disabled={loading}
                onCheckedChange={(next) => updateNotifications({ enabled: next })}
              />
            </>
          }
        />
        <div
          className={cn(
            'flex flex-col gap-3',
            !notifications?.enabled && 'pointer-events-none opacity-33'
          )}
        >
          <SeparatedList gap="0.75rem" direction="column">
            <SettingRow
              title="Sound"
              description="Play audio cues for agent events."
              control={
                <>
                  <ResetToDefaultButton
                    visible={isFieldOverridden('sound')}
                    defaultLabel="on"
                    onReset={() => resetNotificationField('sound', true)}
                    disabled={loading}
                  />
                  {!customSoundPath && <PreviewSoundButton path="" disabled={loading} />}
                  <Switch
                    checked={notifications?.sound ?? true}
                    disabled={loading}
                    onCheckedChange={(next) => updateNotifications({ sound: next })}
                  />
                </>
              }
            />

            <SettingRow
              title="Custom sound"
              description="Use an audio file instead of the built-in cue."
              control={
                <>
                  <ResetToDefaultButton
                    visible={isFieldOverridden('customSoundPath')}
                    defaultLabel="built-in"
                    onReset={() => resetNotificationField('customSoundPath', '')}
                    disabled={loading}
                  />
                  {customSoundPath && (
                    <PreviewSoundButton path={customSoundPath} disabled={loading} />
                  )}
                  <Tooltip.Provider delay={150}>
                    <Tooltip.Root>
                      <Tooltip.Trigger
                        render={
                          <Button
                            type="button"
                            variant="secondary"
                            className="max-w-56 bg-transparent font-normal text-foreground-muted"
                            disabled={loading}
                            onClick={chooseCustomSound}
                            aria-label={
                              customSoundPath ? 'Change custom sound' : 'Choose custom sound'
                            }
                          >
                            <FolderOpen className="size-3.5 shrink-0" />
                            <span className="truncate">
                              {customSoundPath ? getFileName(customSoundPath) : 'Choose file…'}
                            </span>
                          </Button>
                        }
                      />
                      {customSoundPath && (
                        <Tooltip.Content side="top" className="break-all">
                          {customSoundPath}
                        </Tooltip.Content>
                      )}
                    </Tooltip.Root>
                  </Tooltip.Provider>
                </>
              }
            />

            <SettingRow
              title="Sound timing"
              description="When to play sounds."
              control={
                <>
                  <ResetToDefaultButton
                    visible={isFieldOverridden('soundFocusMode')}
                    defaultLabel="always"
                    onReset={() => resetNotificationField('soundFocusMode', 'always')}
                    disabled={loading}
                  />
                  <Select.Root
                    value={notifications?.soundFocusMode ?? 'always'}
                    onValueChange={(next) =>
                      updateNotifications({ soundFocusMode: next as 'always' | 'unfocused' })
                    }
                  >
                    <Select.Trigger className="w-auto shrink-0 gap-2 capitalize [&>span]:line-clamp-none">
                      <Select.Value />
                    </Select.Trigger>
                    <Select.Content className="min-w-max">
                      <Select.Item value="always">Always</Select.Item>
                      <Select.Item value="unfocused">Only when unfocused</Select.Item>
                    </Select.Content>
                  </Select.Root>
                </>
              }
            />

            <SettingRow
              title="OS notifications"
              description="Show system banners when agents need attention or finish (while Hardcore is unfocused)."
              control={
                <>
                  <ResetToDefaultButton
                    visible={isFieldOverridden('osNotifications')}
                    defaultLabel="on"
                    onReset={() => resetNotificationField('osNotifications', true)}
                    disabled={loading}
                  />
                  <Switch
                    checked={notifications?.osNotifications ?? true}
                    disabled={loading}
                    onCheckedChange={(next) => updateNotifications({ osNotifications: next })}
                  />
                </>
              }
            />
          </SeparatedList>
        </div>
      </SeparatedList>
    </SettingsCard>
  );
};

export default NotificationSettingsCard;
