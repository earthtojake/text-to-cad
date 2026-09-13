import { normalizeExclusionPatterns } from '@emdash/core/primitives/exclusion-policy/api';
import { SettingsCard } from '@emdash/ui/react/patterns';
import { Field, Input, Separator, Switch, Textarea, toast } from '@emdash/ui/react/primitives';
import { observer } from 'mobx-react-lite';
import { useEffect, useState } from 'react';
import { getMachinesStore } from '../../contributions/app-stores';
import { useHostSettings } from '../use-host-settings';

/**
 * Per-host defaults (host-settings runtime): shellSetup, worktree root, tmux, and
 * watcher exclusions, plus the desktop-side "Sync local settings" toggle for
 * remote machines. Text fields commit on blur; switches commit immediately.
 * External edits to the host's settings file stream in through the live model
 * while a field is not focused.
 */
export const HostSettingsCard = observer(function HostSettingsCard({
  machineId,
  enabled = true,
}: {
  machineId?: string;
  enabled?: boolean;
}) {
  const { settings, parseError, isLoading, update } = useHostSettings(machineId, enabled);
  const machinesStore = getMachinesStore();
  const machine = machineId
    ? machinesStore.connections.find((connection) => connection.id === machineId)
    : undefined;
  const syncLocalSettings = machine?.syncLocalSettings ?? false;
  const [shellSetup, setShellSetup] = useState('');
  const [worktreeRoot, setWorktreeRoot] = useState('');
  const [watcherExclude, setWatcherExclude] = useState('');
  const [editing, setEditing] = useState<'shellSetup' | 'worktreeRoot' | 'watcherExclude' | null>(
    null
  );

  const watcherExcludeStored = settings?.watcherExclude?.join('\n') ?? '';
  useEffect(() => {
    if (editing !== 'shellSetup') setShellSetup(settings?.shellSetup ?? '');
  }, [settings?.shellSetup, editing]);
  useEffect(() => {
    if (editing !== 'worktreeRoot') setWorktreeRoot(settings?.worktreeRoot ?? '');
  }, [settings?.worktreeRoot, editing]);
  useEffect(() => {
    if (editing !== 'watcherExclude') setWatcherExclude(watcherExcludeStored);
  }, [watcherExcludeStored, editing]);

  const commit = async (patch: Parameters<typeof update>[0]) => {
    try {
      await update(patch);
    } catch (error) {
      toast.error('Failed to save host settings', {
        description: error instanceof Error ? error.message : String(error),
      });
    }
  };

  const commitText = (field: 'shellSetup' | 'worktreeRoot', value: string) => {
    setEditing(null);
    const trimmed = value.trim();
    if (trimmed === (settings?.[field] ?? '')) return;
    void commit({ [field]: trimmed || null });
  };

  const commitWatcherExclude = (value: string) => {
    setEditing(null);
    const normalized = normalizeExclusionPatterns(value.split(/\r?\n/u));
    if (normalized.join('\n') === watcherExcludeStored) {
      setWatcherExclude(watcherExcludeStored);
      return;
    }
    // Empty clears back to "unset" so the host falls back to the default excludes.
    void commit({ watcherExclude: normalized.length > 0 ? normalized : null });
  };

  const toggleSyncLocalSettings = async (checked: boolean) => {
    if (!machineId) return;
    try {
      await machinesStore.setSyncLocalSettings(machineId, checked);
    } catch (error) {
      toast.error('Failed to update sync setting', {
        description: error instanceof Error ? error.message : String(error),
      });
    }
  };

  const disabled = isLoading || settings === undefined;

  return (
    <SettingsCard>
      <Field.Root>
        <Field.Label>Host defaults</Field.Label>
        <Field.Description>
          Machine-level defaults applied to workspaces on this host. Stored in the host&apos;s
          Hardcore data directory; edits made to the file directly show up here live.
        </Field.Description>
      </Field.Root>
      <div className="mt-4 flex flex-col gap-4">
        {parseError ? (
          <div className="text-sm text-foreground-error">
            The host settings file could not be parsed; defaults are in effect until it is fixed.
          </div>
        ) : null}

        <Field.Root>
          <Field.Label>Shell setup</Field.Label>
          <Field.Description className="text-foreground-muted">
            Shell commands prepended to every lifecycle script and terminal session on this host
            (nvm, mise, …). A workspace&apos;s .hardcore.json shellSetup overrides this.
          </Field.Description>
          <Textarea
            placeholder={'nvm use\nsource .envrc'}
            value={shellSetup}
            disabled={disabled}
            onFocus={() => setEditing('shellSetup')}
            onChange={(event) => setShellSetup(event.target.value)}
            onBlur={(event) => commitText('shellSetup', event.target.value)}
          />
        </Field.Root>

        <Separator />

        <Field.Root>
          <Field.Label>Worktree root</Field.Label>
          <Field.Description className="text-foreground-muted">
            Default directory new worktrees are created under on this host. Project settings can
            override it per project.
          </Field.Description>
          <Input
            placeholder="~/hardcore/worktrees"
            value={worktreeRoot}
            disabled={disabled}
            onFocus={() => setEditing('worktreeRoot')}
            onChange={(event) => setWorktreeRoot(event.target.value)}
            onBlur={(event) => commitText('worktreeRoot', event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') event.currentTarget.blur();
            }}
          />
        </Field.Root>

        <Separator />

        <Field.Root orientation="horizontal">
          <div className="flex flex-1 flex-col gap-1">
            <Field.Label>Enable tmux by default</Field.Label>
            <Field.Description className="text-foreground-muted">
              Default tmux preference for sessions on this host. Project settings can override it
              per project.
            </Field.Description>
          </div>
          <Switch
            checked={settings?.tmux ?? false}
            disabled={disabled}
            onCheckedChange={(checked) => void commit({ tmux: checked })}
          />
        </Field.Root>

        {machineId ? (
          <>
            <Separator />

            <Field.Root orientation="horizontal">
              <div className="flex flex-1 flex-col gap-1">
                <Field.Label>Sync local settings</Field.Label>
                <Field.Description className="text-foreground-muted">
                  Mirror this machine&apos;s local settings to this host (currently watcher
                  exclusions). While on, the host&apos;s values follow this machine&apos;s; the last
                  synced values remain when turned off.
                </Field.Description>
              </div>
              <Switch
                checked={syncLocalSettings}
                disabled={disabled || machine === undefined}
                onCheckedChange={(checked) => void toggleSyncLocalSettings(checked)}
              />
            </Field.Root>

            <Separator />

            <Field.Root>
              <Field.Label>Watcher exclusions</Field.Label>
              <Field.Description className="text-foreground-muted">
                {syncLocalSettings
                  ? 'Synced from this machine\u2019s local settings. '
                  : 'Reduce file-watcher work for noisy folders on this host, one pattern per line. Leave empty to use the default exclusions. '}
                Changes apply the next time the workspace server restarts.
              </Field.Description>
              <Textarea
                placeholder="One pattern per line (defaults apply when empty)"
                rows={4}
                spellCheck={false}
                className="font-mono text-xs"
                value={watcherExclude}
                disabled={disabled}
                readOnly={syncLocalSettings}
                onFocus={() => {
                  if (!syncLocalSettings) setEditing('watcherExclude');
                }}
                onChange={(event) => {
                  if (!syncLocalSettings) setWatcherExclude(event.target.value);
                }}
                onBlur={(event) => {
                  if (!syncLocalSettings) commitWatcherExclude(event.target.value);
                }}
              />
            </Field.Root>
          </>
        ) : null}
      </div>
    </SettingsCard>
  );
});
