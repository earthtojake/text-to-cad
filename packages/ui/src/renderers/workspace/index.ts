// What the viewer renderers share that is neither the kit nor core: the backend
// connection a file is prepared against, and the tab's viewer preferences.
// Renderers import this and the kit; they never import each other.
export { prepareWorkspaceEntry } from './prepare.js';
export type { PreparedWorkspaceEntry, WorkspaceClientOption } from './prepare.js';
export { createCadPreferences } from './preferences.js';
export type { CadPreferences, CadPreferenceSource, ToolStackLayout } from './preferences.js';
export type { ViewerCommands, ViewerCommandSource } from './commands.js';
