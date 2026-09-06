import { app } from 'electron';
import devIcon from '@/assets/images/hardcore/hardcore-dev.png?asset';
import { initializeFileLogger, registerProcessErrorLogging } from '@main/host/file-logger';
import {
  LIBSECRET_PASSWORD_STORE,
  shouldForceLibsecretBackend,
} from '@main/host/linux-secret-storage';
import { registerAppScheme } from '@main/host/protocol';
import { log } from '@main/lib/logger';
import type { AppConfig } from '../../core/config';
import { step } from '../../core/phase';
import { BootAborted, type BootSignals } from '../types';

export async function prepareElectron(config: AppConfig, signals: BootSignals): Promise<void> {
  if (process.platform === 'linux') {
    app.commandLine.appendSwitch('ozone-platform-hint', 'auto');
    if (
      shouldForceLibsecretBackend(process.env, {
        passwordStoreSwitchPresent: app.commandLine.hasSwitch('password-store'),
      })
    ) {
      app.commandLine.appendSwitch('password-store', LIBSECRET_PASSWORD_STORE);
    }
  }

  registerAppScheme();
  initializeFileLogger();
  registerProcessErrorLogging(log);

  app.on('second-instance', () => {
    if (signals.windowPhaseReady) void showMainWindow();
  });

  if (!config.isDev && !app.requestSingleInstanceLock()) {
    app.quit();
    throw new BootAborted('Another application instance is already running');
  }

  if (config.isDev) {
    try {
      app.dock?.setIcon(devIcon);
    } catch (error) {
      log.warn('Failed to set dock icon:', error);
    }
  }

  app.on('activate', () => {
    if (signals.windowPhaseReady) void showMainWindow();
  });

  // Hardcore remains available from the tray when its main window is destroyed.
  // Explicit quit requests are coordinated through the before-quit handler.
  app.on('window-all-closed', () => {});

  await step('electron-app-ready', () => app.whenReady());
}

async function showMainWindow(): Promise<void> {
  const windowModule = await import('@main/host/window');
  windowModule.showMainWindow();
}
