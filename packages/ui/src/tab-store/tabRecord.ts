import type { JsonValue } from '../file-viewer/types.js';
import { normalizeToolStack } from '../renderers/kit/tools/toolStackLayout.js';
import { normalizeViewportBackground } from '@cad/core/lib/viewportTheme.js';

/**
 * The tab record: everything the viewer keeps, kept for one tab and thrown out with it.
 *
 *   { version, settings, files }
 *
 * `settings` is tab-wide — the tool stack's layout, the appearance, the viewport's background and how
 * the home lays out and sorts its library, with the home's sidebar as the person left it — and replaces every global preference. (The folder the name menu's Files was last
 * in, `explorer`, an earlier release's, is read as nothing: projects replaced the explorer.)
 * `files` is the view of the file on screen (`kit/shell/fileView.js`: its camera, its Display
 * settings, its playback, its renderer's own slices) under `[absolute file path, renderer id]`,
 * and nothing else: a write puts a file last and drops any other (`TAB_FILE_LIMIT`), and a host
 * leaving a file sets its view aside for the page (`files.retain`, which `CadViewer` calls: in the
 * store's memory, never in the record), so a reload brings back the file on screen, and a file left
 * and come back to in the same page opens as it was left.
 *
 * This module is the record's one definition: its shape, its version and its normalization.
 * Reading is forgiving — a record another version wrote is the defaults, a field that is not
 * what it should be is its default — and writing is exact. A new kind of tab-wide state is one
 * more field of `settings` here; a new kind of per-file state is one more slice a renderer
 * hands the shell. Nothing here touches storage: a host supplies that (`tabStore.ts`).
 */
export const TAB_RECORD_VERSION = 2;
/** One: a tab shows one file, and only the file on screen's view is the tab's (the page keeps those it left: `PAGE_FILE_LIMIT`). */
export const TAB_FILE_LIMIT = 1;

export type Appearance = 'system' | 'light' | 'dark';
/** The model area's background, the person's (Display's Background): Light (the default) or Dark; a stored "theme" (the old Follow theme) reads as Light. */
export type ViewportBackground = 'light' | 'dark';
/** How the home lays out its models: a grid of cards, or a list of rows. */
export type LibraryLayout = 'grid' | 'list';
/** How the home orders the documents of the place on screen: by last activity (the default), by name, or by kind. */
export type LibrarySort = 'activity' | 'name' | 'kind';
/**
 * The home's sidebar as the person left it (`library/LibrarySidebar.jsx`), kept as a file's panel is in its view
 * (`file-viewer/filePanel.js`), the home in the file's place: `open`, their choice (opened, `true`, or closed, `false`),
 * which holds at any width, absent until they choose (the home's width then decides); `width`, what they dragged it
 * to. A peek, a phone's sheet and what the home's width does are never written.
 */
export interface LibraryPanelRecord { open?: boolean; width?: number }
export interface ToolStackLayout { panels: Record<string, { width?: number; height?: number }>; collapsed: Record<string, boolean> }
export interface TabSettings {
  /** The tool stack's layout (`kit/tools/toolStackLayout.js`): the resizable panels' sizes and the folded panels (the view's panel is each file's). */
  toolStack: ToolStackLayout;
  /** System, Light or Dark; a new tab follows the OS until the person picks. */
  appearance: Appearance;
  /** The viewport's background in every file and view (`@cad/core/lib/viewportTheme.js`): Light unless the person picks. */
  viewportBackground: ViewportBackground;
  /** The home's library: its models as a grid of cards (the default) or a list, how they are ordered, and its sidebar where the person set it. */
  library: { layout: LibraryLayout; sort: LibrarySort; panel?: LibraryPanelRecord };
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
const LIBRARY_SORTS: readonly LibrarySort[] = ['activity', 'name', 'kind'];
/** The widest a kept panel width is read as, whatever was stored (`filePanel.js`'s bound; the panel draws within its own). */
const PANEL_WIDTH_MAX = 4000;
export function normalizeAppearance(value: unknown): Appearance {
  return APPEARANCES.includes(value as Appearance) ? (value as Appearance) : 'system';
}

function normalizeLibrary(value: unknown): TabSettings['library'] {
  const { layout, sort, panel } = plainObject(value) ? value : {} as Record<string, unknown>;
  // The sidebar's fields that are what they should be, read as a file's panel is (`file-viewer/filePanel.js`'s
  // `readFilePanel`, whose module this one, with no React in it, does not import); a home's has no tab. None, no field.
  const { open, width } = plainObject(panel) ? panel : {} as Record<string, unknown>;
  const kept: LibraryPanelRecord = { ...(typeof open === 'boolean' ? { open } : null),
    ...(typeof width === 'number' && Number.isFinite(width) && width > 0 ? { width: Math.round(Math.min(PANEL_WIDTH_MAX, width)) } : null) };
  return { layout: LIBRARY_LAYOUTS.includes(layout as LibraryLayout) ? (layout as LibraryLayout) : 'grid',
    sort: LIBRARY_SORTS.includes(sort as LibrarySort) ? (sort as LibrarySort) : 'activity',
    ...(Object.keys(kept).length ? { panel: kept } : null) };
}

/** The settings as the tab keeps them, from anything a store handed back. */
export function normalizeTabSettings(value: unknown): TabSettings {
  const record = plainObject(value) ? value : {};
  return {
    toolStack: normalizeToolStack(record.toolStack) as ToolStackLayout,
    appearance: normalizeAppearance(record.appearance),
    viewportBackground: normalizeViewportBackground(record.viewportBackground) as ViewportBackground,
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
