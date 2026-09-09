import { clipboard, webContents } from 'electron';
import {
  browserProfilePartition,
  DEFAULT_BROWSER_PROFILE_ID,
  isBrowserDataClearKind,
  isBrowsingDataKind,
  type BrowserDataClearKind,
} from '@core/primitives/browser/api';
import { getAppSettingsService } from '@main/bootstrap/core/service-instances';
import { configureBrowserProfileSession } from '@main/host/browser/browser-profile-session';
import { browserWebContentsRegistry } from '@main/host/browser/browser-webcontents-registry';
import { isBrowserPartition } from '@main/host/browser/webview-security';
import { listCadArtifacts } from '@main/host/cad/cad-artifact-scan';
import { createCadDrawing } from '@main/host/cad/cad-drawing-service';
import { rebuildCadModel, validateCadModel } from '@main/host/cad/cad-validation-service';
import { ensureCadViewer } from '@main/host/cad/cad-viewer-service';

export const browserOperations = {
  registerSession: (args: { browserId: string; partition: string }) => {
    if (!args.browserId.trim() || !isBrowserPartition(args.partition)) {
      return { success: false as const, error: 'Invalid browser session' };
    }
    configureBrowserProfileSession(args.partition);
    browserWebContentsRegistry.registerSession(args);
    return { success: true as const };
  },

  unregisterSession: (browserId: string) => {
    browserWebContentsRegistry.unregisterSession(browserId);
    return { success: true as const };
  },

  releaseWebContents: (browserId: string) => ({
    success: browserWebContentsRegistry.releaseWebContents(browserId),
  }),

  bindWebContents: (args: { browserId: string; webContentsId: number }) => {
    const target = webContents.fromId(args.webContentsId);
    if (!target || target.isDestroyed()) {
      return { success: false as const };
    }
    return { success: browserWebContentsRegistry.bindWebContents(args.browserId, target) };
  },

  setActiveBrowser: (browserId: string | null) => {
    browserWebContentsRegistry.setActiveBrowser(browserId);
    return { success: true as const };
  },

  ensureCadViewer,

  validateCadModel,

  rebuildCadModel,

  createCadDrawing,

  listCadArtifacts,

  openDevTools: (browserId: string) => ({
    success: import.meta.env.DEV && browserWebContentsRegistry.openDevTools(browserId),
  }),

  captureScreenshot: async (browserId: string) => ({
    success: await browserWebContentsRegistry.captureScreenshotToClipboard(browserId),
  }),

  captureScreenshotForChat: async (browserId: string) => {
    const image = await browserWebContentsRegistry.captureScreenshot(browserId);
    if (!image) return { success: false as const, error: 'CAD viewport is not ready.' };
    const data = image.toPNG();
    if (data.byteLength === 0) return { success: false as const, error: 'Screenshot was empty.' };
    clipboard.writeImage(image);
    return { success: true as const, dataUrl: `data:image/png;base64,${data.toString('base64')}` };
  },

  clearData: async (browserId: string, kind: BrowserDataClearKind) => {
    if (!isBrowserDataClearKind(kind)) {
      return { success: false as const, error: 'Invalid browser data clear kind' };
    }
    return { success: await browserWebContentsRegistry.clearData(browserId, kind) };
  },

  clearProfileStorage: async (profileId: string) => ({
    success: await browserWebContentsRegistry.clearProfileStorage(profileId),
  }),

  clearBrowsingData: async (kind: string) => {
    if (!isBrowsingDataKind(kind)) {
      return { success: false as const, error: 'Invalid browsing data kind' };
    }
    const partitions = await collectBrowserPartitions();
    return { success: await browserWebContentsRegistry.clearBrowsingData(kind, partitions) };
  },
};

// Every persistent profile partition (default + named) plus any partitions with
// live sessions, so clearing browsing data covers isolated-per-task tabs too.
async function collectBrowserPartitions(): Promise<string[]> {
  const browserSettings = await getAppSettingsService().get('browser');
  const partitions = new Set<string>([browserProfilePartition(DEFAULT_BROWSER_PROFILE_ID)]);
  for (const profile of browserSettings.profiles) {
    partitions.add(browserProfilePartition(profile.id));
  }
  for (const partition of browserWebContentsRegistry.registeredPartitions) {
    partitions.add(partition);
  }
  return [...partitions];
}
