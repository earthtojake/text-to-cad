import { formatConfigError, parseConfig } from '@emdash/shared/config';
import { z } from 'zod';
import {
  APP_ID,
  IS_CANARY,
  PRODUCT_NAME,
  UPDATE_CHANNEL,
  USER_DATA_DIR_NAME,
} from '@core/primitives/app-identity/api/app-identity';

export type AppIdentityConfig = {
  appId: string;
  productName: string;
  userDataDirName: string;
  updateChannel: string;
  isCanary: boolean;
};

export type AppConfig = {
  identity: AppIdentityConfig;
  isDev: boolean;
  dbFile: string | undefined;
  userDataDir: string | undefined;
  disableNativeDb: boolean;
  telemetryEnabled: boolean;
  installSource: string | undefined;
  forceBootFailure: boolean;
};

const flagIsOne = z
  .string()
  .optional()
  .transform((value) => value === '1');

const telemetryEnabled = z
  .string()
  .optional()
  .transform((value) => {
    const normalized = (value ?? 'true').toLowerCase();
    return normalized !== 'false' && normalized !== '0' && normalized !== 'no';
  });

const rawAppConfigSchema = z
  .object({
    emdashDbFile: z.string().trim().min(1, 'Database path cannot be empty').optional(),
    emdashUserDataDir: z.string().trim().min(1, 'User data directory cannot be empty').optional(),
    emdashDisableNativeDb: flagIsOne,
    telemetryEnabled,
    installSource: z.string().trim().min(1, 'Install source cannot be empty').optional(),
    emdashForceBootFailure: flagIsOne,
  })
  .transform(
    (config): Omit<AppConfig, 'identity' | 'isDev'> => ({
      dbFile: config.emdashDbFile,
      userDataDir: config.emdashUserDataDir,
      disableNativeDb: config.emdashDisableNativeDb,
      telemetryEnabled: config.telemetryEnabled,
      installSource: config.installSource,
      forceBootFailure: config.emdashForceBootFailure,
    })
  );

let appConfig: AppConfig | undefined;
let userDataConfigured = false;

export function loadAppConfig(env: NodeJS.ProcessEnv = process.env): AppConfig {
  const parsed = parseConfig({
    schema: rawAppConfigSchema,
    argv: [],
    env,
  });
  if (!parsed.success) {
    throw new Error(formatConfigError(parsed.error));
  }

  return {
    identity: {
      appId: APP_ID,
      productName: PRODUCT_NAME,
      userDataDirName: USER_DATA_DIR_NAME,
      updateChannel: UPDATE_CHANNEL,
      isCanary: IS_CANARY,
    },
    isDev: import.meta.env.DEV,
    ...parsed.data,
  };
}

export function setAppConfig(config: AppConfig): void {
  if (appConfig !== undefined) {
    throw new Error('App config has already been set');
  }
  appConfig = config;
}

export function getAppConfig(): AppConfig {
  if (appConfig === undefined) {
    throw new Error('App config has not been initialized');
  }
  return appConfig;
}

export function markUserDataConfigured(): void {
  userDataConfigured = true;
}

export function assertUserDataConfigured(): void {
  const processType = (process as NodeJS.Process & { type?: string }).type;
  const isElectronMain = Boolean(process.versions.electron) && processType === 'browser';
  if (isElectronMain && !userDataConfigured) {
    throw new Error(
      'The database path was resolved before the Electron userData path was configured.'
    );
  }
}
