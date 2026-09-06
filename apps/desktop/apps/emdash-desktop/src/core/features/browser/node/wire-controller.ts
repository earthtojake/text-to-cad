import { createController, type Controller } from '@emdash/wire/rpc';
import type { BrowserDataClearKind, BrowsingDataKind } from '@core/primitives/browser/api';
import {
  browserContract,
  type CadArtifactScanResult,
  type CadDrawingResult,
  type CadValidationResult,
  type BrowserScreenshotResult,
} from '../api';
import { browserEvents } from './event-host';

export type BrowserOperations = {
  registerSession(input: { browserId: string; partition: string }): BrowserActionResult;
  unregisterSession(browserId: string): BrowserActionResult;
  releaseWebContents(browserId: string): BrowserActionResult;
  bindWebContents(input: { browserId: string; webContentsId: number }): BrowserActionResult;
  setActiveBrowser(browserId: string | null): BrowserActionResult;
  ensureCadViewer(input: {
    workspacePath: string;
    filePath: string;
  }): Promise<{ success: true; url: string } | { success: false; error: string }>;
  validateCadModel(input: {
    workspacePath: string;
    filePath: string;
    sourcePath?: string;
  }): Promise<CadValidationResult>;
  rebuildCadModel(input: { workspacePath: string; filePath: string }): Promise<CadValidationResult>;
  createCadDrawing(input: {
    workspacePath: string;
    filePath: string;
  }): Promise<CadDrawingResult> | CadDrawingResult;
  listCadArtifacts(input: {
    workspacePath: string;
    sinceMs: number;
  }): Promise<CadArtifactScanResult> | CadArtifactScanResult;
  openDevTools(browserId: string): BrowserActionResult;
  captureScreenshot(browserId: string): Promise<BrowserActionResult>;
  captureScreenshotForChat(browserId: string): Promise<BrowserScreenshotResult>;
  clearData(browserId: string, kind: BrowserDataClearKind): Promise<BrowserActionResult>;
  clearProfileStorage(profileId: string): Promise<BrowserActionResult>;
  clearBrowsingData(kind: BrowsingDataKind): Promise<BrowserActionResult>;
};

type BrowserActionResult = { success: boolean; error?: string };

export function createBrowserWireController(browserOperations: BrowserOperations): Controller {
  return createController(browserContract, {
    registerSession: (input) => browserOperations.registerSession(input),
    unregisterSession: ({ browserId }) => browserOperations.unregisterSession(browserId),
    releaseWebContents: ({ browserId }) => browserOperations.releaseWebContents(browserId),
    bindWebContents: (input) => browserOperations.bindWebContents(input),
    setActiveBrowser: ({ browserId }) => browserOperations.setActiveBrowser(browserId),
    ensureCadViewer: (input) => browserOperations.ensureCadViewer(input),
    validateCadModel: (input) => browserOperations.validateCadModel(input),
    rebuildCadModel: (input) => browserOperations.rebuildCadModel(input),
    createCadDrawing: (input) => browserOperations.createCadDrawing(input),
    listCadArtifacts: (input) => browserOperations.listCadArtifacts(input),
    openDevTools: ({ browserId }) => browserOperations.openDevTools(browserId),
    captureScreenshot: ({ browserId }) => browserOperations.captureScreenshot(browserId),
    captureScreenshotForChat: ({ browserId }) =>
      browserOperations.captureScreenshotForChat(browserId),
    clearData: ({ browserId, kind }) => browserOperations.clearData(browserId, kind),
    clearProfileStorage: ({ profileId }) => browserOperations.clearProfileStorage(profileId),
    clearBrowsingData: ({ kind }) => browserOperations.clearBrowsingData(kind),
    events: browserEvents,
  });
}
