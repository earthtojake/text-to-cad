import { app, shell } from 'electron';
import type { UpdateOperations } from '@core/features/updates/node/wire-controller';
import { HARDCORE_RELEASES_URL } from '@core/primitives/urls/api/urls';
import { updateService } from './update-service';
import { formatUpdaterError } from './utils';

export const updateOperations: UpdateOperations = {
  checkForUpdates: () => updateService.checkForUpdates(),
  downloadUpdate: () => updateService.downloadUpdate(),
  quitAndInstall: () => updateService.quitAndInstall(),
  async openLatestRelease() {
    await shell.openExternal(HARDCORE_RELEASES_URL);
    setTimeout(() => {
      try {
        app.quit();
      } catch {}
    }, 500);
  },
  getState: () => updateService.getState(),
  fetchReleaseNotes: () => updateService.fetchReleaseNotes(),
  formatError: formatUpdaterError,
};
