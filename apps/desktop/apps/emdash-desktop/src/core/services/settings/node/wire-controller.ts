import { createController, type Controller } from '@emdash/wire/rpc';
import { appSettingsContract, type AppSettings, type AppSettingsKey } from '../api';
import type { AppSettingsService } from './app-settings-service';

export type SettingsRuntimePort = {
  setKeyboardSettings(settings: AppSettings['keyboard']): void;
  setBrowserSettings(settings: AppSettings['browser']): void;
  setTheme(theme: AppSettings['theme']): void;
};

async function reconcileSettingsRuntimeState(
  service: AppSettingsService,
  runtime: SettingsRuntimePort,
  key: AppSettingsKey
): Promise<void> {
  if (key === 'theme') {
    runtime.setTheme(await service.get('theme'));
  }
  if (key === 'keyboard') {
    runtime.setKeyboardSettings(await service.get('keyboard'));
  }
  if (key === 'browser') {
    runtime.setBrowserSettings(await service.get('browser'));
  }
}

async function updateSetting<K extends AppSettingsKey>(
  service: AppSettingsService,
  key: K,
  value: AppSettings[K]
): Promise<void> {
  await service.update(key, value);
}

async function resetSettingField<K extends AppSettingsKey>(
  service: AppSettingsService,
  key: K,
  field: string
): Promise<void> {
  await service.resetField(key, field as keyof AppSettings[K]);
}

export function createAppSettingsWireController(
  service: AppSettingsService,
  runtime: SettingsRuntimePort
): Controller {
  return createController(appSettingsContract, {
    get: ({ key }) => service.get(key),
    getAll: () => service.getAll(),
    getWithMeta: ({ key }) => service.getWithMeta(key),
    update: async ({ key, value }) => {
      await updateSetting(service, key, value);
      await reconcileSettingsRuntimeState(service, runtime, key);
    },
    reset: async ({ key }) => {
      await service.reset(key);
      await reconcileSettingsRuntimeState(service, runtime, key);
    },
    resetField: async ({ key, field }) => {
      await resetSettingField(service, key, field);
      await reconcileSettingsRuntimeState(service, runtime, key);
    },
  });
}
