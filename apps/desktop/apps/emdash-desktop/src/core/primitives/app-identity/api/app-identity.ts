type ImportMetaWithEnv = ImportMeta & { env?: { DEV?: boolean; VITE_BUILD?: string } };

const env = (import.meta as ImportMetaWithEnv).env;
const isDev = env?.DEV === true;
const isCanary = env?.VITE_BUILD === 'canary';

export const APP_ID = isCanary ? 'com.amywork777.hardcore.canary' : 'com.amywork777.hardcore';
export const PRODUCT_NAME = isCanary ? 'Hardcore Canary' : 'Hardcore';
export const APP_NAME_LOWER = isCanary ? 'hardcore-canary' : 'hardcore';
export const USER_DATA_DIR_NAME = isDev
  ? 'hardcore-dev'
  : isCanary
    ? 'hardcore-canary'
    : 'hardcore';
export const UPDATE_CHANNEL = isCanary ? 'v1-canary' : 'v1-stable';
export const ARTIFACT_PREFIX = isCanary ? 'hardcore-canary' : 'hardcore';
export const IS_CANARY = isCanary;
