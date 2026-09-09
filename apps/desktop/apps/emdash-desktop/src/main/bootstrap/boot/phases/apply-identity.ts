import { join } from 'node:path';
import { app } from 'electron';
import type { AppConfig } from '../../core/config';
import { markUserDataConfigured } from '../../core/config';
import { migrateLegacyUserData } from '../user-data-migration';

export function applyIdentity(config: AppConfig): void {
  app.setName(config.identity.productName);
  // A user-data override redirects the whole profile (DB, logs, mementos) to an
  // isolated directory — used by the boot-measurement harness and scratch profiles.
  const userDataPath =
    config.userDataDir ?? join(app.getPath('appData'), config.identity.userDataDirName);
  if (!config.userDataDir) migrateLegacyUserData(app.getPath('appData'), userDataPath);
  app.setPath('userData', userDataPath);
  markUserDataConfigured();
}
