import { copyFileSync, cpSync, existsSync, mkdirSync, readdirSync } from 'node:fs';
import { basename, join } from 'node:path';

const LEGACY_DATABASE_PREFIX = 'emdash4';
const HARDCORE_DATABASE_PREFIX = 'hardcore4';

export function migrateLegacyUserData(appDataPath: string, userDataPath: string): void {
  const legacyName = legacyUserDataName(basename(userDataPath));
  const legacyPath = join(appDataPath, legacyName);

  if (!existsSync(userDataPath) && existsSync(legacyPath)) {
    cpSync(legacyPath, userDataPath, { recursive: true, preserveTimestamps: true });
  }
  if (!existsSync(userDataPath)) return;

  mkdirSync(userDataPath, { recursive: true });
  for (const filename of readdirSync(userDataPath)) {
    if (!filename.startsWith(LEGACY_DATABASE_PREFIX)) continue;
    const destination = join(
      userDataPath,
      `${HARDCORE_DATABASE_PREFIX}${filename.slice(LEGACY_DATABASE_PREFIX.length)}`
    );
    if (!existsSync(destination)) copyFileSync(join(userDataPath, filename), destination);
  }
}

function legacyUserDataName(hardcoreName: string): string {
  if (hardcoreName === 'hardcore-dev') return 'emdash-dev';
  if (hardcoreName === 'hardcore-canary') return 'emdash-canary';
  return 'emdash';
}
