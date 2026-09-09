import { SettingsCard, SettingsSection } from '@emdash/ui/react/patterns';
import {
  Button,
  DropdownMenu,
  Input,
  Select,
  SeparatedList,
  Switch,
  toast,
} from '@emdash/ui/react/primitives';
import { Check, ChevronDown, Ellipsis, Eraser, Pencil, Plus, Trash2, X } from 'lucide-react';
import { useRef, useState } from 'react';
import { browserControlsRegistry } from '@core/features/browser/api/browser/browser-controls-registry';
import { browserSessionStore } from '@core/features/browser/api/browser/browser-session-store';
import { getBrowserClient } from '@core/features/browser/api/browser/client';
import { useAppSettingsKey } from '@core/features/settings/api/browser/use-app-settings-key';
import { useOpenModal } from '@core/manifests/browser/modal-api';
import {
  BROWSER_ISOLATED_PROFILE_ID,
  DEFAULT_BROWSER_PROFILE_ID,
  DEFAULT_BROWSER_PROFILES,
  browserProfileLabel,
  isNamedBrowserProfileId,
  normalizeBrowserProfileSelection,
  type BrowserProfile,
  type BrowsingDataKind,
} from '@core/primitives/browser/api';
import { cn } from '@core/primitives/styling/browser/cn';
import { SettingRow } from './SettingRow';

export function BrowserSettingsCard() {
  const {
    value: browserSettings,
    update,
    updateAsync,
    isLoading,
    isSaving,
  } = useAppSettingsKey('browser');
  const openConfirm = useOpenModal('confirmActionModal');
  const [editingProfileId, setEditingProfileId] = useState<string | null>(null);
  const [isAdding, setIsAdding] = useState(false);
  const [isBrowsingDataExpanded, setIsBrowsingDataExpanded] = useState(false);
  const [isClearingBrowsingData, setIsClearingBrowsingData] = useState(false);
  const addInputRef = useRef<HTMLInputElement>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);

  const profiles = browserSettings?.profiles ?? DEFAULT_BROWSER_PROFILES;
  const selectedDefault = normalizeBrowserProfileSelection(
    browserSettings?.defaultProfileId,
    profiles
  );
  const disabled = isLoading || isSaving;

  const addProfile = (name: string) => {
    setIsAdding(false);
    const nextName = name.trim();
    if (!nextName) return;
    const profile: BrowserProfile = { id: makeProfileId(nextName, profiles), name: nextName };
    update({ profiles: [...profiles, profile] });
  };

  const renameProfile = (profileId: string, name: string) => {
    setEditingProfileId(null);
    const nextName = name.trim();
    if (!nextName) return;
    update({
      profiles: profiles.map((profile) =>
        profile.id === profileId ? { ...profile, name: nextName } : profile
      ),
    });
  };

  const clearProfileStorage = (profile: BrowserProfile) => {
    void openConfirm({
      title: `Clear ${profile.name} browser storage?`,
      description:
        'This clears cookies, local storage, IndexedDB, and cache for this profile. Browser tabs using it will be signed out.',
      confirmLabel: 'Clear Storage',
      variant: 'destructive',
    }).then((outcome) => {
      if (outcome.success) void clearProfileStorageAndReload(profile.id);
    });
  };

  const runClearBrowsingData = async (kind: BrowsingDataKind, label: string) => {
    setIsClearingBrowsingData(true);
    try {
      const result = await (await getBrowserClient()).clearBrowsingData({ kind });
      if (!result.success) {
        toast.error('Could not clear browsing data', {
          description: 'Try again, or reload the browser view manually.',
        });
        return;
      }
      reloadAllBrowserSessions();
      toast(`${label} cleared`);
    } catch (error) {
      toast.error('Could not clear browsing data', { description: errorMessage(error) });
    } finally {
      setIsClearingBrowsingData(false);
    }
  };

  const clearBrowsingData = (kind: BrowsingDataKind, label: string) => {
    void openConfirm({
      ...BROWSING_DATA_CONFIRMATIONS[kind],
      variant: 'destructive',
    }).then((outcome) => {
      if (outcome.success) void runClearBrowsingData(kind, label);
    });
  };

  const deleteProfile = (profile: BrowserProfile) => {
    if (profiles.length <= 1) return;
    void openConfirm({
      title: `Delete ${profile.name} browser profile?`,
      description:
        'This removes the profile and clears its cookies, local storage, IndexedDB, and cache.',
      confirmLabel: 'Delete Profile',
      variant: 'destructive',
    }).then((outcome) => {
      if (!outcome.success) return;
      const nextProfiles = profiles.filter((candidate) => candidate.id !== profile.id);
      const replacementProfileId =
        selectedDefault === profile.id
          ? (nextProfiles[0]?.id ?? DEFAULT_BROWSER_PROFILE_ID)
          : selectedDefault;
      void deleteProfileAfterStorageClear({
        deletedProfileId: profile.id,
        replacementProfileId,
        nextProfiles,
        updateAsync,
      });
    });
  };

  return (
    <div className="flex flex-col gap-8">
      <SettingsCard>
        <SeparatedList gap="1rem" direction="column">
          <SettingRow
            title="Default browser profile"
            description="New browser tabs open with this profile. You can switch an individual tab's profile from its toolbar menu."
            control={
              <Select.Root
                value={selectedDefault}
                onValueChange={(next) => {
                  if (next) update({ defaultProfileId: next });
                }}
                disabled={disabled}
              >
                <Select.Trigger className="w-[190px] shrink-0 gap-2">
                  <Select.Value>{browserProfileLabel(selectedDefault, profiles)}</Select.Value>
                </Select.Trigger>
                <Select.Content align="end">
                  {profiles.map((profile) => (
                    <Select.Item key={profile.id} value={profile.id}>
                      {profile.name}
                    </Select.Item>
                  ))}
                  <Select.Item value={BROWSER_ISOLATED_PROFILE_ID}>Isolated per task</Select.Item>
                </Select.Content>
              </Select.Root>
            }
          />

          <SettingRow
            title="Disable CORS for localhost"
            description="Allows pages opened from localhost in Hardcore browser tabs to call APIs that do not send matching CORS headers."
            control={
              <Switch
                checked={browserSettings?.relaxCorsForLocalhost ?? false}
                disabled={disabled}
                onCheckedChange={(next) => update({ relaxCorsForLocalhost: next })}
              />
            }
          />
        </SeparatedList>
      </SettingsCard>

      <SettingsSection title="Browser profiles" bare>
        <SettingsCard>
          <div className="text-xs text-foreground-passive">
            Each profile keeps its own cookies and logins, shared across tasks. Profiles do not
            import anything from your system browser.
          </div>

          <div className="mt-2 flex flex-col divide-y divide-border/40">
            {profiles.map((profile) => (
              <div key={profile.id} className="flex h-9 items-center gap-2">
                {editingProfileId === profile.id ? (
                  <>
                    <Input
                      ref={renameInputRef}
                      autoFocus
                      defaultValue={profile.name}
                      disabled={disabled}
                      aria-label={`Rename ${profile.name} browser profile`}
                      className="h-7 min-w-0 flex-1"
                      onFocus={(event) => event.currentTarget.select()}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter')
                          renameProfile(profile.id, event.currentTarget.value);
                        if (event.key === 'Escape') setEditingProfileId(null);
                      }}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      icon
                      className="size-7 shrink-0 text-foreground-muted"
                      disabled={disabled}
                      aria-label={`Save ${profile.name} browser profile name`}
                      onClick={() => renameProfile(profile.id, renameInputRef.current?.value ?? '')}
                    >
                      <Check className="size-4" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      icon
                      className="size-7 shrink-0 text-foreground-muted"
                      disabled={disabled}
                      aria-label={`Cancel renaming ${profile.name} browser profile`}
                      onClick={() => setEditingProfileId(null)}
                    >
                      <X className="size-4" />
                    </Button>
                  </>
                ) : (
                  <>
                    <span className="min-w-0 flex-1 truncate text-sm text-foreground">
                      {profile.name}
                    </span>
                    <DropdownMenu.Root>
                      <DropdownMenu.Trigger
                        render={
                          <Button
                            type="button"
                            variant="ghost"
                            icon
                            className="size-7 shrink-0 text-foreground-muted"
                            disabled={disabled}
                            aria-label={`${profile.name} browser profile actions`}
                          />
                        }
                      >
                        <Ellipsis className="size-4" />
                      </DropdownMenu.Trigger>
                      <DropdownMenu.Content
                        align="end"
                        className="min-w-40"
                        finalFocus={renameInputRef}
                      >
                        <DropdownMenu.Item onClick={() => setEditingProfileId(profile.id)}>
                          <Pencil className="size-4" />
                          Rename
                        </DropdownMenu.Item>
                        <DropdownMenu.Item onClick={() => clearProfileStorage(profile)}>
                          <Eraser className="size-4" />
                          Clear storage
                        </DropdownMenu.Item>
                        <DropdownMenu.Separator />
                        <DropdownMenu.Item
                          variant="destructive"
                          disabled={profiles.length <= 1}
                          onClick={() => deleteProfile(profile)}
                        >
                          <Trash2 className="size-4" />
                          Delete
                        </DropdownMenu.Item>
                      </DropdownMenu.Content>
                    </DropdownMenu.Root>
                  </>
                )}
              </div>
            ))}
          </div>

          <div className="mt-2 flex h-7 items-center">
            {isAdding ? (
              <div className="flex w-full items-center gap-2">
                <Input
                  ref={addInputRef}
                  autoFocus
                  disabled={disabled}
                  placeholder="Profile name"
                  aria-label="New browser profile name"
                  className="h-7 min-w-0 flex-1"
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') addProfile(event.currentTarget.value);
                    if (event.key === 'Escape') setIsAdding(false);
                  }}
                />
                <Button
                  type="button"
                  variant="ghost"
                  icon
                  className="size-7 shrink-0 text-foreground-muted"
                  disabled={disabled}
                  aria-label="Save new browser profile"
                  onClick={() => addProfile(addInputRef.current?.value ?? '')}
                >
                  <Check className="size-4" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  icon
                  className="size-7 shrink-0 text-foreground-muted"
                  disabled={disabled}
                  aria-label="Cancel adding profile"
                  onClick={() => setIsAdding(false)}
                >
                  <X className="size-4" />
                </Button>
              </div>
            ) : (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="text-foreground-muted"
                disabled={disabled}
                onClick={() => setIsAdding(true)}
              >
                <Plus className="size-4" />
                Add profile
              </Button>
            )}
          </div>
        </SettingsCard>
      </SettingsSection>

      <SettingsSection title="Browsing data" bare>
        <SettingsCard>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <div className="flex min-w-0 flex-1 basis-64 flex-col gap-0.5">
              <div className="text-xs text-foreground-passive">
                Clear cookies, cached files, and site data from the in-app browser.
              </div>
            </div>
            <div className="ml-auto flex shrink-0 items-center gap-1">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="text-foreground-muted"
                disabled={disabled || isClearingBrowsingData}
                onClick={() => clearBrowsingData('all', 'All browsing data')}
              >
                Clear all browsing data
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                icon
                className="shrink-0 text-foreground-muted"
                aria-expanded={isBrowsingDataExpanded}
                aria-label={
                  isBrowsingDataExpanded
                    ? 'Hide individual browsing data options'
                    : 'Show individual browsing data options'
                }
                onClick={() => setIsBrowsingDataExpanded((expanded) => !expanded)}
              >
                <ChevronDown
                  className={cn(
                    'size-4 transition-transform',
                    isBrowsingDataExpanded && 'rotate-180'
                  )}
                />
              </Button>
            </div>
          </div>

          {isBrowsingDataExpanded && (
            <div className="mt-2 flex flex-col divide-y divide-border/40">
              {BROWSING_DATA_CATEGORIES.map((category) => (
                <div key={category.kind} className="flex h-9 items-center gap-2">
                  <span className="min-w-0 flex-1 truncate text-sm text-foreground">
                    {category.label}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="shrink-0 text-foreground-muted"
                    disabled={disabled || isClearingBrowsingData}
                    onClick={() => clearBrowsingData(category.kind, category.label)}
                  >
                    {category.actionLabel}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </SettingsCard>
      </SettingsSection>
    </div>
  );
}

const BROWSING_DATA_CATEGORIES: ReadonlyArray<{
  kind: Exclude<BrowsingDataKind, 'all'>;
  label: string;
  actionLabel: string;
}> = [
  { kind: 'cookies', label: 'Cookies', actionLabel: 'Delete cookies' },
  { kind: 'siteData', label: 'Site data', actionLabel: 'Delete site data' },
  {
    kind: 'cache',
    label: 'Cached images and files',
    actionLabel: 'Delete cached images and files',
  },
];

const BROWSING_DATA_CONFIRMATIONS: Record<
  BrowsingDataKind,
  { title: string; description: string; confirmLabel: string }
> = {
  all: {
    title: 'Clear all browsing data?',
    description:
      'This deletes cookies, cached files, and site data for every in-app browser profile. Open browser tabs will be signed out.',
    confirmLabel: 'Clear all data',
  },
  cookies: {
    title: 'Delete cookies?',
    description:
      'This deletes cookies for every in-app browser profile. Open browser tabs will be signed out.',
    confirmLabel: 'Delete cookies',
  },
  siteData: {
    title: 'Delete site data?',
    description:
      'This deletes local storage, IndexedDB, service workers, and other site data for every in-app browser profile. Open browser tabs may be signed out.',
    confirmLabel: 'Delete site data',
  },
  cache: {
    title: 'Delete cached images and files?',
    description:
      'This deletes cached images and files for every in-app browser profile. Pages may load more slowly the next time you open them.',
    confirmLabel: 'Delete cached files',
  },
};

function reloadAllBrowserSessions(): void {
  for (const session of browserSessionStore.activeSessions) {
    browserControlsRegistry.get(session.browserId)?.adapter?.reload();
  }
}

async function clearProfileStorageAndReload(profileId: string): Promise<void> {
  try {
    const result = await (await getBrowserClient()).clearProfileStorage({ profileId });
    if (!result.success) {
      toast.error('Could not clear browser storage', {
        description: 'The browser profile no longer exists or could not be cleared.',
      });
      return;
    }
    reloadBrowserSessionsForProfile(profileId);
  } catch (error) {
    toast.error('Could not clear browser storage', { description: errorMessage(error) });
  }
}

async function deleteProfileAfterStorageClear({
  deletedProfileId,
  replacementProfileId,
  nextProfiles,
  updateAsync,
}: {
  deletedProfileId: string;
  replacementProfileId: string;
  nextProfiles: BrowserProfile[];
  updateAsync: (partial: { profiles: BrowserProfile[]; defaultProfileId: string }) => Promise<void>;
}): Promise<void> {
  let storageCleared = false;
  try {
    const clearResult = await (
      await getBrowserClient()
    ).clearProfileStorage({
      profileId: deletedProfileId,
    });
    if (!clearResult.success) {
      toast.error('Could not delete browser profile', {
        description: 'The profile storage could not be cleared, so the profile was kept.',
      });
      return;
    }

    storageCleared = true;
    await updateAsync({
      profiles: nextProfiles,
      defaultProfileId: replacementProfileId,
    });
    browserSessionStore.migrateProfileSessions(
      deletedProfileId,
      replacementProfileId,
      nextProfiles
    );
  } catch (error) {
    if (storageCleared) reloadBrowserSessionsForProfile(deletedProfileId);
    toast.error('Could not delete browser profile', {
      description: storageCleared
        ? `Storage was cleared, but the profile is still listed. ${errorMessage(error)}`
        : errorMessage(error),
    });
  }
}

function reloadBrowserSessionsForProfile(profileId: string): void {
  for (const session of browserSessionStore.activeSessions) {
    if (session.profileId !== profileId) continue;
    browserControlsRegistry.get(session.browserId)?.adapter?.reload();
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function makeProfileId(name: string, profiles: readonly BrowserProfile[]): string {
  const existingIds = new Set(profiles.map((profile) => profile.id));
  const base = slugifyProfileName(name) || 'profile';
  let candidate = base;
  let suffix = 2;
  while (existingIds.has(candidate) || !isNamedBrowserProfileId(candidate)) {
    const suffixText = String(suffix);
    const prefixLength = Math.max(1, 63 - suffixText.length);
    candidate = `${base.slice(0, prefixLength)}-${suffixText}`;
    suffix += 1;
  }
  return candidate;
}

function slugifyProfileName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)
    .replace(/-+$/g, '');
}
