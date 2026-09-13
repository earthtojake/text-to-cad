import { app, dialog } from 'electron';
import { initializeFileLogger } from '@main/host/file-logger';
import { showRecoveryWindow } from '@main/host/recovery/recovery-window';
import { log } from '@main/lib/logger';

/*
 * Recovery is the last-resort import path after a failed boot. Keep this module
 * and its transitive static imports independent from the database, desktop
 * workers, Wire gateway, and updater module graph — any failure in those would
 * prevent the recovery window from opening.
 *
 * The updateService is loaded dynamically inside showRecoveryWindow so that a
 * failure in the updater module graph degrades gracefully instead of preventing
 * the window from appearing.
 */

let safeModeQuitHandlerRegistered = false;

export async function enterSafeMode(error: unknown): Promise<void> {
  initializeFileLogger();
  const errorMessage = error instanceof Error ? error.message : String(error);
  log.error('Boot failed; entering recovery mode', { error });
  registerSafeModeQuitHandler();

  await app.whenReady();

  try {
    await showRecoveryWindow({ errorMessage });
  } catch (windowError) {
    log.error('Failed to open recovery window', { error: windowError });
    dialog.showErrorBox(
      'Something went wrong',
      `Hardcore could not start or open recovery mode.\n\n${errorMessage}`
    );
  }
}

function registerSafeModeQuitHandler(): void {
  if (safeModeQuitHandlerRegistered) return;
  safeModeQuitHandlerRegistered = true;
  // Intentionally do not prevent the event. Normal shutdown services were not
  // initialized, and electron-updater must be allowed to install on app quit.
  app.on('before-quit', () => {});
}
