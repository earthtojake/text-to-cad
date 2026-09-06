import { requestWirePort, type WindowLike } from '@emdash/wire/rpc';
import { contextBridge, ipcRenderer, webUtils } from 'electron';

// Preload is typechecked by the node program (no DOM lib), but runs in the
// renderer where `window` exists; declare it with the structural type wire needs.
declare const window: WindowLike;

// Expose protected methods that allow the renderer process to use
contextBridge.exposeInMainWorld('electronAPI', {
  getPathForFile: (file: File) => {
    try {
      return webUtils.getPathForFile(file);
    } catch {
      return '';
    }
  },
  requestWirePort: (channel: string) => requestWirePort({ ipcRenderer, window }, { channel }),
  // Boot-watchdog escape hatch. This cannot ride the wire: a hung backend
  // means the wire gateway may never register controllers, so the loading
  // state needs a direct channel to learn the boot is stuck.
  onBootStuck: (callback: (payload: { stuckPhase: string }) => void) => {
    const listener = (_event: unknown, payload: { stuckPhase: string }) => callback(payload);
    ipcRenderer.on('emdash:boot-stuck', listener);
    return () => {
      ipcRenderer.removeListener('emdash:boot-stuck', listener);
    };
  },
  requestBootEscape: (action: 'restart' | 'open-recovery') =>
    ipcRenderer.invoke('emdash:boot-escape', action),
  // Boot report: the splash gate settled, i.e. the usable-workspace moment.
  // The arrival time in main is the measurement.
  reportBootUsable: () => {
    ipcRenderer.send('emdash:boot-usable-workspace');
  },
});
