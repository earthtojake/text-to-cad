import { createToolModes } from "../tools/toolModes.js";
import { SHELL_TOOL } from "./useRendererShell.js";

/**
 * Tool modes for a file with nothing to pick: `shell.tools.orbit`, then Draw, then
 * Animate when the file can have routines. Orbit is the tool a file opens in and
 * the only one a saved tab records: Draw is a session that ends when its tool is
 * asked for again, and Animate's routine is released on leaving, so coming back
 * always starts from rest.
 *
 * @param {{ animate?: boolean }} [options]  `animate`: the family can carry routines.
 */
export function createViewToolModes({ animate = false } = {}) {
  return createToolModes({
    defaultMode: SHELL_TOOL.ORBIT,
    modes: {
      [SHELL_TOOL.ORBIT]: { persists: true },
      [SHELL_TOOL.DRAW]: { toggles: true },
      ...(animate ? { [SHELL_TOOL.ANIMATE]: {} } : {})
    }
  });
}
