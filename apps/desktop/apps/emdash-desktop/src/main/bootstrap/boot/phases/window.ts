import { join } from 'node:path';
import { app } from 'electron';
import { installDesktopWire } from '@main/gateway/desktop-wire';
import { setupApplicationMenu } from '@main/host/menu';
import { setupAppProtocol } from '@main/host/protocol';
import { initializeTray } from '@main/host/tray';
import { createMainWindow } from '@main/host/window';
import { registerQuitHandler } from '../../shutdown';
import type { BootSignals } from '../types';

export function bootWindow(
  signals: BootSignals,
  renderer: { failed(error: Error): void; loaded(): void }
): void {
  setupAppProtocol(join(app.getAppPath(), 'out', 'renderer'));
  setupApplicationMenu();
  // The renderer requests its wire port as soon as it boots, which under the
  // window-first boot happens long before controllers exist. The port handler
  // must be live before loadURL; traffic queues until controllers register.
  installDesktopWire();
  createMainWindow({ onRendererFailure: renderer.failed, onRendererLoaded: renderer.loaded });
  initializeTray();
  registerQuitHandler();
  signals.windowPhaseReady = true;
}
