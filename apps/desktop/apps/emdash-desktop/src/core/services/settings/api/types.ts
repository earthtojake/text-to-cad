import type {
  AppSettings as ManifestAppSettings,
  AppSettingsKey as ManifestAppSettingsKey,
} from '@core/manifests/shared/settings-contributions';

export type AppSettings = ManifestAppSettings;
export type AppSettingsKey = ManifestAppSettingsKey;

export type SettingsOverrides<T> = T extends object ? Partial<T> : Record<string, never>;

export type SettingsMeta<T> = {
  value: T;
  defaults: T;
  overrides: SettingsOverrides<T>;
};
