import { err, ok, type Result } from '@emdash/shared';
import {
  fetchAppSettingsMeta,
  getAllAppSettingsFromCache,
  getAppSettingsMetaFromCache,
  invalidateAppSettingsKey,
  restoreAppSettingsCache,
  setAppSettingsValueInCache,
  updateAppSettingsRequest,
} from '@core/features/settings/api/browser/app-settings-client';
import type { Theme } from '@core/primitives/app-settings/api';
import { getNextTheme } from '@core/primitives/theme/browser';

export type ToggleThemeError = { message: string };

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export async function toggleAppTheme(): Promise<Result<NonNullable<Theme>, ToggleThemeError>> {
  let theme: Theme;
  try {
    theme = (await fetchAppSettingsMeta('theme')).value;
  } catch (error) {
    return err({
      message: errorMessage(error),
    });
  }

  const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'emdark'
    : 'emlight';
  const next = getNextTheme(theme, systemTheme);
  const previousMeta = getAppSettingsMetaFromCache('theme');
  const previousAll = getAllAppSettingsFromCache();

  setAppSettingsValueInCache('theme', next);

  try {
    await updateAppSettingsRequest('theme', next);
  } catch (error) {
    restoreAppSettingsCache('theme', previousMeta, previousAll);
    return err({
      message: errorMessage(error),
    });
  } finally {
    invalidateAppSettingsKey('theme');
  }

  return ok(next);
}
