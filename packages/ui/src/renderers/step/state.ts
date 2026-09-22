import type { JsonValue } from '../../file-viewer/types.js';
import * as state from './workbench/state.js';

export type CadStateObject = { [key: string]: JsonValue };

// What a HOST needs of the STEP renderer's stored state, and nothing more. The per-file
// record itself is the shell's (`kit/shell/shellState.js`) and a host treats it as opaque
// JSON, so the session schema that used to be published here went with the surface that
// wrote it. What is left is the two things a host really does own: the orbit preference,
// which is a preference rather than per-file state, and the width of the Inspector sheet,
// which the host lays out.
export const cadWorkspaceDefaultFileSheetWidthForViewport =
  state.cadWorkspaceDefaultFileSheetWidthForViewport as (width: number) => number;
export const fileSheetWidthPxForSessionState =
  state.fileSheetWidthPxForSessionState as (value: unknown, defaultWidth?: number) => number | null;
export { CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH, CAD_WORKSPACE_COMPACT_TAB_TOOLS_WIDTH } from './workbench/state.js';

export { ORBIT_STORAGE_KEY, readOrbit, writeOrbit, normalizeOrbit } from "../kit/tools/fullscreen/orbitPreferences.js";
