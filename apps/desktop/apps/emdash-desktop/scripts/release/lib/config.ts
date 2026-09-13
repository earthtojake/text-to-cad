export {
  APP_ID,
  APP_NAME_LOWER,
  ARTIFACT_PREFIX,
  PRODUCT_NAME,
  UPDATE_CHANNEL,
} from '../../../src/core/primitives/app-identity/api/app-identity.ts';

export const RELEASE_DIR = 'release';
export const NATIVE_MODULES = ['better-sqlite3', 'node-pty', '@parcel/watcher'];
export const GITHUB_OWNER = 'amywork777';
export const GITHUB_REPO = 'hardcore';

export function requireEnv(name: string): string {
  const val = process.env[name];
  if (!val) throw new Error(`Missing required env var: ${name}`);
  return val;
}

export function r2Endpoint(): string {
  return `https://${requireEnv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com/${requireEnv('R2_BUCKET')}`;
}
