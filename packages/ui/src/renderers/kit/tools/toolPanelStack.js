import { createContext, useContext } from "react";

/**
 * The stack of kept tool panels under the tool strip (a renderer's retained effects): a tool's
 * menu and the Display sheet open BESIDE it, never over the panels a person is keeping.
 * The shell provides the stack's element as a ref.
 */
export const ToolPanelStackContext = createContext(null);
export const useToolPanelStack = () => useContext(ToolPanelStackContext);

const GAP_PX = 8;

/**
 * Where a menu anchored on `trigger` opens while the stack shows a panel: aligned to the
 * trigger's start and pushed right until it clears the stack. `null` while the stack is empty:
 * the menu keeps its own placement. Read when the menu opens, so a panel kept or closed
 * afterwards moves nothing under the pointer. The menu passes `sticky="always"` with it: the
 * default keeps a menu overlapping its trigger, which would pull it back over the panels.
 * @param {HTMLElement | null | undefined} stack
 * @param {HTMLElement | null | undefined} trigger
 * @returns {{ align: "start", alignOffset: number } | null}
 */
export function placementBesidePanels(stack, trigger) {
  if (!stack || !trigger) return null;
  const panels = [...stack.children].map(child => child.getBoundingClientRect()).filter(rect => rect.width > 0 && rect.height > 0);
  if (!panels.length) return null;
  const right = Math.max(...panels.map(rect => rect.right));
  return { align: "start", alignOffset: Math.max(0, Math.ceil(right + GAP_PX - trigger.getBoundingClientRect().left)) };
}
