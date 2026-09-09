import type { CadEntry } from '@hardcore/core/client';
import type { JsonValue } from '../../file-viewer/types.js';
import * as state from './workbench/state.js';
import * as sessions from './workbench/fileSessionState.js';
import * as tabs from './workbench/fileSheetTabLayout.js';

export type CadStateObject = { [key: string]: JsonValue };
export interface CadThemeState {
  themeId: string;
  custom: CadStateObject | null;
  settings: CadStateObject;
}
export interface CadFileSessionState {
  version: number;
  fileKey: string;
  signatures: { [key: string]: string };
  slices: { [key: string]: JsonValue };
}
export interface CadFileSessionOptions {
  fileKey?: string;
  entry?: CadEntry | null;
  currentSignatures?: { [key: string]: string };
  skipSignatureCheck?: boolean;
}
export interface CadSessionStorage {
  getItem(key: string): string | null;
}
export const readFileSheetTabLayoutStore = tabs.readFileSheetTabLayoutStore as (storage: CadSessionStorage | null) => CadStateObject;
export const writeFileSheetTabLayoutStore = tabs.writeFileSheetTabLayoutStore as (storage: { setItem(key: string, value: string): void } | null, store: CadStateObject | undefined) => void;
export { FILE_SHEET_TAB_LAYOUT_STORAGE_KEY } from './workbench/fileSheetTabLayout.js';

// These adapters publish the existing schemas without duplicating their rules.
// Storage is always supplied by the host; importing this module reads nothing.
export const createThemeState = state.createThemeState as unknown as (
  themeId?: string, custom?: unknown, options?: { prefersDark?: boolean }
) => CadThemeState;
export const createTabSnapshot = state.createTabSnapshot as (overrides?: unknown) => CadStateObject;
export const cloneTabSnapshot = state.cloneTabSnapshot as (snapshot?: unknown) => CadStateObject;
export const tabSnapshotEqual = state.tabSnapshotEqual as (left: unknown, right: unknown) => boolean;
export const createTabRecord = state.createTabRecord as (key: string, overrides?: unknown) => CadStateObject & { key: string };
export const normalizeFileSessionState = sessions.normalizeFileSessionState as (
  value: unknown, options?: CadFileSessionOptions
) => CadFileSessionState | null;
export const createFileSessionSnapshot = sessions.createFileSessionSnapshot as (
  options?: { fileKey?: string; entry?: CadEntry | null; slices?: CadStateObject }
) => CadFileSessionState | null;
export const readFileSessionState = sessions.readFileSessionState as (
  namespace: string, fileKey: string, entry: CadEntry | null, options: { storage: CadSessionStorage }
) => CadFileSessionState | null;
export const fileSessionStorageKey = sessions.fileSessionStorageKey as (namespace: string, fileKey: string) => string;
export const fileSessionIndexStorageKey = sessions.fileSessionIndexStorageKey as (namespace: string) => string;
export const fileSessionSignaturesForEntry = sessions.fileSessionSignaturesForEntry as (entry: CadEntry) => CadFileSessionState['signatures'];
export const cadWorkspaceDefaultFileSheetWidthForViewport = state.cadWorkspaceDefaultFileSheetWidthForViewport as (width: number) => number;
export const fileSheetWidthPxForSessionState = state.fileSheetWidthPxForSessionState as (value: unknown, defaultWidth?: number) => number | null;
export { THEME_STORAGE_VERSION, CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH, CAD_WORKSPACE_COMPACT_TAB_TOOLS_WIDTH } from './workbench/state.js';
export { FILE_SESSION_STORAGE_VERSION } from './workbench/fileSessionState.js';
