import { homedir } from 'node:os';
import { join } from 'node:path';

export const PREVIOUS_DB_FILENAME = 'hardcore3.db';
export const CURRENT_DB_FILENAME = 'hardcore4.db';
const USER_DATA_DIR_NAME = 'hardcore';

/**
 * Returns the platform-specific default userData directory without requiring
 * the Electron `app` module. This is pinned to the shared `hardcore` directory
 * regardless of product identity.
 *
 * Pass this result as `userDataPath` to `resolveDatabasePath()` when running
 * outside of Electron (e.g. drizzle-kit CLI).
 */
export function resolveDefaultUserDataPath(): string {
  const home = process.env.HOME ?? homedir();
  const platform = process.platform;

  if (platform === 'darwin') {
    return join(home, 'Library', 'Application Support', USER_DATA_DIR_NAME);
  }

  if (platform === 'win32') {
    const appData = process.env.APPDATA ?? join(home, 'AppData', 'Roaming');
    return join(appData, USER_DATA_DIR_NAME);
  }

  const xdgConfig = process.env.XDG_CONFIG_HOME ?? join(home, '.config');
  return join(xdgConfig, USER_DATA_DIR_NAME);
}

/**
 * Returns the default database file path given a resolved userData directory.
 * Does not check for file existence or perform any migration — suitable for
 * contexts that only need a path (e.g. drizzle-kit config).
 */
export function defaultDbFilePath(userDataPath: string): string {
  return join(userDataPath, CURRENT_DB_FILENAME);
}
