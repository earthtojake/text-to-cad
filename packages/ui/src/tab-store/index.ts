// The tab store: everything the viewer keeps, kept for one tab and thrown out with it. The
// host supplies where the record lives (`TabRecordStorage`); this package defines the record
// (`tabRecord.ts`), its versioning and its normalization, and hands hosts the pieces:
// `settings` for the renderers' preferences, `files` for the file views, and one hook that
// turns both into `FileViewer`'s controlled state.
export { createTabStore, memoryTabRecord } from './tabStore.js';
export type { SettingsSource, TabRecordStorage, TabStore } from './tabStore.js';
export { TAB_FILE_LIMIT, TAB_RECORD_VERSION, defaultTabRecord, normalizeAppearance, normalizeTabSettings, parseTabFileKey, readTabRecord, tabFileKey } from './tabRecord.js';
export type { Appearance, TabRecord, TabSettings, ToolStackLayout } from './tabRecord.js';
export { useTabViewerState } from './useTabViewerState.js';
