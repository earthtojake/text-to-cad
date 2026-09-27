import type { JsonValue } from '../file-viewer/types.js';
import { clampPanelWidth, PANEL_DEFAULT_WIDTH } from '../file-viewer/navigation/panelWidth.js';
import { normalizeToolStack } from '../renderers/kit/tools/toolStackLayout.js';

/**
 * The tab record: everything the viewer keeps, kept for one tab and thrown out with it.
 *
 *   { version, settings, files }
 *
 * `settings` is tab-wide — the file tree's width and expansion (by root), the tool stack's
 * layout and the appearance — and replaces every global preference. `files` is each opened
 * file's view (`kit/shell/fileView.js`: its camera, its Display settings, its playback, its
 * renderer's own slices) under `[root id, file path, renderer id]`, the
 * fifty most recently written of them: a write puts a file last, and the first goes once there
 * are more than that.
 *
 * This module is the record's one definition: its shape, its version and its normalization.
 * Reading is forgiving — a record another version wrote is the defaults, a field that is not
 * what it should be is its default — and writing is exact. A new kind of tab-wide state is one
 * more field of `settings` here; a new kind of per-file state is one more slice a renderer
 * hands the shell. Nothing here touches storage: a host supplies that (`tabStore.ts`).
 */
export const TAB_RECORD_VERSION = 1;
export const TAB_FILE_LIMIT = 50;

export type Appearance = 'system' | 'light' | 'dark';
export interface ToolStackLayout { panels: Record<string, { width?: number; height?: number }>; collapsed: Record<string, boolean> }
export interface TabSettings {
  /** The host's file tree: its column's width, and the folders open under each root. */
  fileTree: { width: number; expanded: Record<string, string[]> };
  /** The tool stack's layout (`kit/tools/toolStackLayout.js`): the resizable panels' sizes and the folded panels. */
  toolStack: ToolStackLayout;
  /** System, Light or Dark; a new tab follows the OS until the person picks. */
  appearance: Appearance;
}
export interface TabRecord {
  version: typeof TAB_RECORD_VERSION;
  settings: TabSettings;
  /** File views under `tabFileKey(rootId, path, rendererId)`, oldest first. */
  files: Record<string, JsonValue>;
}

const plainObject = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === 'object' && !Array.isArray(value);
const APPEARANCES: readonly Appearance[] = ['system', 'light', 'dark'];
const MAX_EXPANDED_ROOTS = 64;

function normalizeFileTree(value: unknown): TabSettings['fileTree'] {
  const record = plainObject(value) ? value : {};
  const expanded: Record<string, string[]> = {};
  for (const [root, folders] of Object.entries(plainObject(record.expanded) ? record.expanded : {}).slice(0, MAX_EXPANDED_ROOTS)) {
    if (!Array.isArray(folders)) continue;
    expanded[root] = [...new Set(folders.filter((folder): folder is string => typeof folder === 'string'))];
  }
  return { width: typeof record.width === 'number' && Number.isFinite(record.width) ? clampPanelWidth(record.width) : PANEL_DEFAULT_WIDTH, expanded };
}

export function normalizeAppearance(value: unknown): Appearance {
  return APPEARANCES.includes(value as Appearance) ? (value as Appearance) : 'system';
}

/** The settings as the tab keeps them, from anything a store handed back. */
export function normalizeTabSettings(value: unknown): TabSettings {
  const record = plainObject(value) ? value : {};
  return {
    fileTree: normalizeFileTree(record.fileTree),
    toolStack: normalizeToolStack(record.toolStack) as ToolStackLayout,
    appearance: normalizeAppearance(record.appearance),
  };
}

export const tabFileKey = (rootId: string, path: string, rendererId: string): string => JSON.stringify([rootId, path, rendererId]);
export function parseTabFileKey(key: string): { rootId: string; path: string; rendererId: string } | null {
  try {
    const parsed: unknown = JSON.parse(key);
    return Array.isArray(parsed) && parsed.length === 3 && parsed.every(part => typeof part === 'string')
      ? { rootId: parsed[0], path: parsed[1], rendererId: parsed[2] } : null;
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
