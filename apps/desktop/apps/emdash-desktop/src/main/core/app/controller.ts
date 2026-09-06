import type { OpenInAppId } from '@core/primitives/open-in-apps/api/open-in-apps';
import {
  ackShutdownFlush,
  markShutdownReady,
  resolveQuitConfirmation,
} from '@main/bootstrap/shutdown';
import {
  cleanupExpiredDroppedBlobs,
  persistClipboardImagePath,
  persistDroppedBlobBytes,
} from '@main/core/app/persist-terminal-attachment';
import { setApplicationMenuKeybindings } from '@main/host/menu';
import { log } from '@main/lib/logger';
import { telemetryService } from '@main/lib/telemetry';
import { appService } from './service';

void cleanupExpiredDroppedBlobs().catch((error) => {
  log.warn('app:cleanupExpiredDroppedBlobs failed', { error });
});

export const appOperations = {
  openExternal: async (url: string) => {
    try {
      await appService.openExternal(url);
      telemetryService.capture('open_in_external', { app: 'browser' });
      return { success: true };
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  },
  openPath: async (path: string) => {
    try {
      await appService.openPath(path);
      return { success: true };
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  },
  showWorkspaceItemInFolder: async (args: { workspaceId: string; relativePath: string }) => {
    const result = await appService.showWorkspaceItemInFolder(args);
    if (result.success) return { success: true };
    return {
      success: false,
      error: 'message' in result.error ? result.error.message : result.error.type,
    };
  },
  clipboardWriteText: async (text: string) => {
    try {
      appService.clipboardWriteText(text);
      return { success: true };
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  },
  persistDroppedBlob: async (args: { bytes: Uint8Array; name?: string; mimeType?: string }) => {
    try {
      const path = await persistDroppedBlobBytes(args);
      return { success: true as const, path };
    } catch (error) {
      log.error('app:persistDroppedBlob failed', {
        error: error instanceof Error ? error.message : String(error),
      });
      return {
        success: false as const,
        error: error instanceof Error ? error.message : String(error),
      };
    }
  },
  persistClipboardImage: async () => {
    try {
      const path = await persistClipboardImagePath();
      return { success: true as const, path };
    } catch (error) {
      log.error('app:persistClipboardImage failed', {
        error: error instanceof Error ? error.message : String(error),
      });
      return {
        success: false as const,
        error: error instanceof Error ? error.message : String(error),
      };
    }
  },
  showTerminalContextMenu: async (args: {
    requestId: string;
    selectionText?: string | null;
    linkText?: string | null;
    x: number;
    y: number;
  }) => {
    try {
      appService.showTerminalContextMenu(args);
      return { success: true };
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  },
  setMenuKeybindings: setApplicationMenuKeybindings,
  quit: () => {
    try {
      appService.quit();
      return { success: true };
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  },
  resolveQuitConfirmation: (args: { requestId: string; confirmed: boolean }) => {
    resolveQuitConfirmation(args.requestId, args.confirmed);
  },
  ackShutdownFlush,
  shutdownReady: markShutdownReady,
  openIn: async (args: {
    app: OpenInAppId;
    path: string;
    isRemote?: boolean;
    sshConnectionId?: string | null;
  }) => {
    try {
      await appService.openIn(args);
      telemetryService.capture('open_in_external', { app: args.app });
      return { success: true };
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  },
  checkInstalledApps: () => appService.checkInstalledApps(),
  listInstalledFonts: async (args?: { refresh?: boolean }) => {
    const { fonts, cached, error } = await appService.listInstalledFonts(args?.refresh);
    return { success: !error, fonts, cached, ...(error ? { error } : {}) };
  },
  openSelectDirectoryDialog: (args: { title: string; message: string; defaultPath?: string }) =>
    appService.openSelectDirectoryDialog(args),
  openSelectAudioFileDialog: (args: { title: string; message: string }) =>
    appService.openSelectAudioFileDialog(args),
  saveTextFile: async (args: { title: string; defaultPath: string; content: string }) => {
    try {
      return { success: true as const, path: await appService.saveTextFile(args) };
    } catch (error) {
      return {
        success: false as const,
        error: error instanceof Error ? error.message : String(error),
      };
    }
  },
  readAudioFileDataUrl: async (filePath: string) => {
    try {
      return { success: true, dataUrl: await appService.readAudioFileDataUrl(filePath) };
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  },
  minimizeWindow: () => {
    appService.minimizeWindow();
    return { success: true };
  },
  toggleMaximizeWindow: () => {
    appService.toggleMaximizeWindow();
    return { success: true };
  },
  closeWindow: () => {
    appService.closeWindow();
    return { success: true };
  },
  isWindowMaximized: () => appService.isWindowMaximized(),
  getAppVersion: () => appService.getCachedAppVersion(),
  getElectronVersion: () => process.versions.electron,
  getPlatform: () => process.platform,
};
