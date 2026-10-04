import type { JsonValue } from '../file-viewer/types.js';
import { normalizeToolStack } from '../renderers/kit/tools/toolStackLayout.js';

/**
 * The tab record: everything the viewer keeps, kept for one tab and thrown out with it.
 *
 *   { version, settings, files }
 *
 * `settings` is tab-wide — the tool stack's layout, the appearance and how the home lays out its
 * library — and replaces every global preference.
 * `files` is the view of the file on screen (`kit/shell/fileView.js`: its camera, its Display
 * settings, its playback, its renderer's own slices) under `[absolute file path, renderer id]`,
 * and nothing else: a write puts a file last and drops any other (`TAB_FILE_LIMIT`), and a host
 * leaving a file drops its view (`files.retain`, which `CadViewer` calls), so a reload brings back
 * the file on screen and a file left starts over.
 *
 * This module is the record's one definition: its shape, its version and its normalization.
 * Reading is forgiving — a record another version wrote is the defaults, a field that is not
 * what it should be is its default — and writing is exact. A new kind of tab-wide state is one
 * more field of `settings` here; a new kind of per-file state is one more slice a renderer
 * hands the shell. Nothing here touches storage: a host supplies that (`tabStore.ts`).
 */
export const TAB_RECORD_VERSION = 2;
/** One: a tab shows one file, and only the file on screen keeps its view. */
export const TAB_FILE_LIMIT = 1;

export type Appearance = 'system' | 'light' | 'dark';
/** How the home lays out its models: a grid of cards, or a list of rows. */
export type LibraryLayout = 'grid' | 'list';
export interface ToolStackLayout { panels: Record<string, { width?: number; height?: number }>; collapsed: Record<string, boolean>; closed: Record<string, boolean> }
export interface TabSettings {
  /** The tool stack's layout (`kit/tools/toolStackLayout.js`): the resizable panels' sizes, the folded panels and the closed ones. */
  toolStack: ToolStackLayout;
  /** System, Light or Dark; a new tab follows the OS until the person picks. */
  appearance: Appearance;
  /** The home's library: its models as a grid of cards (the default) or a list. */
  library: { layout: LibraryLayout };
}
export interface TabRecord {
  version: typeof TAB_RECORD_VERSION;
  settings: TabSettings;
  /** File views under `tabFileKey(path, rendererId)`, oldest first. */
  files: Record<string, JsonValue>;
}

const plainObject = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value);
const APPEARANCES: readonly Appearance[] = ['system', 'light', 'dark'];
const LIBRARY_LAYOUTS: readonly LibraryLayout[] = ['grid', 'list'];
export function normalizeAppearance(value: unknown): Appearance {
  return APPEARANCES.includes(value as Appearance) ? (value as Appearance) : 'system';
}

function normalizeLibrary(value: unknown): TabSettings['library'] {
  const layout = plainObject(value) ? value.layout : undefined;
  return { layout: LIBRARY_LAYOUTS.includes(layout as LibraryLayout) ? (layout as LibraryLayout) : 'grid' };
}

/** The settings as the tab keeps them, from anything a store handed back. */
export function normalizeTabSettings(value: unknown): TabSettings {
  const record = plainObject(value) ? value : {};
  return {
    toolStack: normalizeToolStack(record.toolStack) as ToolStackLayout,
    appearance: normalizeAppearance(record.appearance),
    library: normalizeLibrary(record.library),
  };
}

/** A file view's key: the same as `FileViewerState.renderers`' — `[absolute file path, renderer id]`. */
export const tabFileKey = (path: string, rendererId: string): string => JSON.stringify([path, rendererId]);
export function parseTabFileKey(key: string): { path: string; rendererId: string } | null {
  try {
    const parsed: unknown = JSON.parse(key);
    return Array.isArray(parsed) && parsed.length === 2 && parsed.every(part => typeof part === 'string')
      ? { path: parsed[0], rendererId: parsed[1] } : null;
  } catch { return null; }
}

/** The file views as the tab keeps them: well-keyed, plain objects, the last `TAB_FILE_LIMIT` of them. */
export function normalizeTabFiles(value: unknown): TabRecord['files'] {
  const files: TabRecord['files'] = {};
  const entries = Object.entries(plainObject(value) ? value : {}).filter(([key, view]) => parseTabFileKey(key) && plainObject(view));
  for (const [key, view] of entries.slice(-TAB_FILE_LIMIT)) files[key] = view as JsonValue;
  return files;
}

/** The files with `key` written last, and the oldest gone once there are more than the limit. */
export function writeTabFile(files: TabRecord['files'], key: string, view: JsonValue): TabRecord['files'] {
  const next: TabRecord['files'] = {};
  for (const [other, stored] of Object.entries(files)) if (other !== key) next[other] = stored;
  next[key] = view;
  const keys = Object.keys(next);
  for (const stale of keys.slice(0, Math.max(0, keys.length - TAB_FILE_LIMIT))) delete next[stale];
  return next;
}

export function defaultTabRecord(): TabRecord {
  return { version: TAB_RECORD_VERSION, settings: normalizeTabSettings({}), files: {} };
}

/** The record as the tab keeps it, from anything a store handed back: another version's is the defaults. */
export function readTabRecord(raw: unknown): TabRecord {
  if (!plainObject(raw) || raw.version !== TAB_RECORD_VERSION) return defaultTabRecord();
  return { version: TAB_RECORD_VERSION, settings: normalizeTabSettings(raw.settings), files: normalizeTabFiles(raw.files) };
}
