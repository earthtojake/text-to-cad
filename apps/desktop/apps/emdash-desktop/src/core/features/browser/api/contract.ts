import { defineContract, eventStream, procedure } from '@emdash/wire/rpc';
import { z } from 'zod';
import type {
  BrowserDataClearKind,
  BrowserEvent,
  BrowsingDataKind,
} from '@core/primitives/browser/api';

type BrowserActionResult = { success: boolean; error?: string };

export type CadValidationResult =
  | {
      success: true;
      artifact: {
        revisionId: string;
        modelPath: string;
        modelHash: string;
        sourcePath?: string;
        sourceHash?: string;
      };
      facts: {
        occurrenceCount?: number;
        faceCount?: number;
        size?: [number, number, number];
      };
      validation: Record<string, unknown>;
    }
  | { success: false; error: string };

export type CadDrawingResult =
  | {
      success: true;
      revisionId: string;
      drawing: {
        svgPath: string;
        pdfPath: string;
        dxfPath: string;
        manifestPath: string;
      };
    }
  | { success: false; error: string };

export type CadArtifactScanResult =
  | {
      success: true;
      /** Workspace-relative model artifacts written since the requested time, oldest first. */
      artifacts: Array<{ path: string; mtimeMs: number }>;
      /** True when the walk stopped early because the workspace is too large. */
      truncated: boolean;
    }
  | { success: false; error: string };

export const browserDomain = 'browser' as const;

export const browserContract = defineContract({
  registerSession: procedure({
    input: z.object({ browserId: z.string(), partition: z.string() }),
    output: z.custom<BrowserActionResult>(),
  }),
  unregisterSession: procedure({
    input: z.object({ browserId: z.string() }),
    output: z.custom<BrowserActionResult>(),
  }),
  releaseWebContents: procedure({
    input: z.object({ browserId: z.string() }),
    output: z.custom<BrowserActionResult>(),
  }),
  bindWebContents: procedure({
    input: z.object({ browserId: z.string(), webContentsId: z.number() }),
    output: z.custom<BrowserActionResult>(),
  }),
  setActiveBrowser: procedure({
    input: z.object({ browserId: z.string().nullable() }),
    output: z.custom<BrowserActionResult>(),
  }),
  ensureCadViewer: procedure({
    input: z.object({ workspacePath: z.string(), filePath: z.string() }),
    output: z.custom<{ success: true; url: string } | { success: false; error: string }>(),
  }),
  validateCadModel: procedure({
    input: z.object({
      workspacePath: z.string(),
      filePath: z.string(),
      sourcePath: z.string().optional(),
    }),
    output: z.custom<CadValidationResult>(),
  }),
  rebuildCadModel: procedure({
    input: z.object({ workspacePath: z.string(), filePath: z.string() }),
    output: z.custom<CadValidationResult>(),
  }),
  createCadDrawing: procedure({
    input: z.object({ workspacePath: z.string(), filePath: z.string() }),
    output: z.custom<CadDrawingResult>(),
  }),
  listCadArtifacts: procedure({
    input: z.object({ workspacePath: z.string(), sinceMs: z.number() }),
    output: z.custom<CadArtifactScanResult>(),
  }),
  openDevTools: procedure({
    input: z.object({ browserId: z.string() }),
    output: z.custom<BrowserActionResult>(),
  }),
  captureScreenshot: procedure({
    input: z.object({ browserId: z.string() }),
    output: z.custom<BrowserActionResult>(),
  }),
  captureScreenshotForChat: procedure({
    input: z.object({ browserId: z.string() }),
    output: z.custom<BrowserScreenshotResult>(),
  }),
  clearData: procedure({
    input: z.object({ browserId: z.string(), kind: z.custom<BrowserDataClearKind>() }),
    output: z.custom<BrowserActionResult>(),
  }),
  clearProfileStorage: procedure({
    input: z.object({ profileId: z.string() }),
    output: z.custom<BrowserActionResult>(),
  }),
  clearBrowsingData: procedure({
    input: z.object({ kind: z.custom<BrowsingDataKind>() }),
    output: z.custom<BrowserActionResult>(),
  }),
  events: eventStream({ key: z.void(), event: z.custom<BrowserEvent>() }),
});
export type BrowserScreenshotResult =
  | { success: true; dataUrl: string }
  | { success: false; error?: string };
