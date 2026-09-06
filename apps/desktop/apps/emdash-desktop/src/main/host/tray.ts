import { readFileSync } from 'node:fs';
import { app, Menu, nativeImage, Tray } from 'electron';
import canaryIcon from '@/assets/images/hardcore/hardcore-canary.png?asset';
import devIcon from '@/assets/images/hardcore/hardcore-dev.png?asset';
import stableIcon from '@/assets/images/hardcore/hardcore.png?asset';
import trayTemplate1x from '@/assets/images/hardcore/trayTemplate.png?asset';
import trayTemplate2x from '@/assets/images/hardcore/trayTemplate@2x.png?asset';
import { IS_CANARY, PRODUCT_NAME } from '@core/primitives/app-identity/api/app-identity';
import { showMainWindow } from './window';

let tray: Tray | null = null;

// macOS menu bar icons are template images: black glyph + alpha, rendered by
// the OS for light/dark menu bars. Both DPI representations are added
// explicitly because production asset filenames are hashed, which breaks
// Electron's automatic `@2x` sibling lookup.
function createMacTrayIcon(): Electron.NativeImage {
  const icon = nativeImage.createEmpty();
  icon.addRepresentation({ scaleFactor: 1, buffer: readFileSync(trayTemplate1x) });
  icon.addRepresentation({ scaleFactor: 2, buffer: readFileSync(trayTemplate2x) });
  icon.setTemplateImage(true);
  return icon;
}

function createTrayIcon(): Electron.NativeImage {
  if (process.platform === 'darwin') return createMacTrayIcon();
  const iconPath = import.meta.env.DEV ? devIcon : IS_CANARY ? canaryIcon : stableIcon;
  return nativeImage.createFromPath(iconPath).resize({ width: 20, height: 20 });
}

export function initializeTray(): Tray {
  if (tray && !tray.isDestroyed()) return tray;

  tray = new Tray(createTrayIcon());
  tray.setToolTip(PRODUCT_NAME);
  tray.setContextMenu(
    Menu.buildFromTemplate([
      {
        label: `Open ${PRODUCT_NAME}`,
        click: () => showMainWindow(),
      },
      { type: 'separator' },
      {
        label: `Quit ${PRODUCT_NAME}`,
        click: () => app.quit(),
      },
    ])
  );

  if (process.platform !== 'darwin') {
    tray.on('click', () => showMainWindow());
  }

  return tray;
}

export function destroyTray(): void {
  if (tray && !tray.isDestroyed()) tray.destroy();
  tray = null;
}
