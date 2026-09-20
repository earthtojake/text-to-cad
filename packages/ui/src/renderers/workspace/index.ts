// What the viewer renderers share that is neither the kit nor core: the backend
// connection a file is prepared against, and the host's viewer preferences.
// Renderers import this and the kit; they never import each other.
export { prepareWorkspaceEntry } from './prepare.js';
export type { PreparedWorkspaceEntry, WorkspaceClientOption } from './prepare.js';
export { createCadPreferences, CAD_LEGACY_PREFERENCE_KEYS } from './preferences.js';
export type { CadPreferences, CadPreferenceSource } from './preferences.js';
