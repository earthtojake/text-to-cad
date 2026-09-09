import path from 'node:path';
import { resolveDatabasePath } from '@main/db/path';

export function resolveFileSearchDatabasePath(appDatabasePath = resolveDatabasePath()): string {
  const extension = path.extname(appDatabasePath);
  const basename = path.basename(appDatabasePath, extension);
  return path.join(path.dirname(appDatabasePath), `${basename}-file-search${extension || '.db'}`);
}
