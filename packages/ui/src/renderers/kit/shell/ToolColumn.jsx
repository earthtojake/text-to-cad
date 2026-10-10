import { useMemo } from "react";
import FloatingToolBar from "../tools/FloatingToolBar.js";
import ToolStack from "../tools/ToolStack.jsx";
import { toolPanelClosed } from "../tools/toolStackLayout.js";
import { VIEWPORT_INSET_PX, VIEWPORT_STACK_BOTTOM } from "./viewportLayout.js";

const INSET = `${VIEWPORT_INSET_PX}px`;
// The strip and its stack stop short of Quick Edit's button at the top-right.
export const TOOL_COLUMN_POSITION = Object.freeze({ top: INSET, left: INSET, bottom: VIEWPORT_STACK_BOTTOM, maxWidth: "calc(100% - 3.5rem)" });

/**
 * The tool strip at a view's top-left corner and the tool stack under it, in one column inset from
 * the viewer's top and left edges and stopping above the cube in the bottom-left corner: the column
 * is exactly the height the stack may take, so however many panels are up, it never runs past the
 * viewer or under the cube (`ToolPanel.jsx` decides which of them gives way).
 * The 3D views (`RendererShell.jsx`) and the flat ones (a KiCad board's or schematic's) draw the same column.
 *
 * Every tool's panel but Select's has an X that puts the tool down, back to Select (the default
 * tool, which cannot be put down). Select's tree has an X of its own that closes the tree alone:
 * the tool it belongs to then carries the strip's corner mark, and a press on that tool while it is
 * up opens the tree again; from another tool, a press only takes it up, the tree still closed.
 * Until the person has closed or opened it, the tree starts as the tool says this file starts it
 * (`panel.startsClosed`: a single part's) and closed on a phone.
 *
 * @param {{ tools: import("../tools/FloatingToolBar.js").ViewportTool[], layout: object,
 *   onLayoutChange(patch: object | ((layout: object) => object)): void, mobile?: boolean, hidden?: boolean,
 *   children?: import("react").ReactNode }} props
 *   `layout`: the tab's tool stack (`CadPreferences.toolStack`). `hidden`: the stack is put away (preview).
 */
export default function ToolColumn({ tools, layout, onLayoutChange, mobile = false, hidden = false, children }) {
  // One object while those starts stay the same: the stack's panels read it.
  const panelStarts = JSON.stringify(tools.filter(tool => tool.panel).map(tool => [tool.panel.id, Boolean(tool.panel.startsClosed)]));
  const startsClosed = useMemo(() => Object.fromEntries(JSON.parse(panelStarts)), [panelStarts]);
  const stripTools = tools.map(tool => {
    if (!tool.panel || !toolPanelClosed(layout, tool.panel.id, { mobile, startsClosed: startsClosed[tool.panel.id] })) return tool;
    const reopen = () => onLayoutChange(current => ({ closed: { ...current.closed, [tool.panel.id]: false } }));
    return { ...tool, panelClosed: true, description: tool.description || `${tool.panel.label} closed`,
      onSelect: () => { if (tool.active) reopen(); tool.onSelect(); } };
  });
  return <div className="group/tool-stack pointer-events-none absolute z-20 flex flex-col items-start gap-2" style={TOOL_COLUMN_POSITION}
    data-mobile={mobile ? "" : undefined} data-cad-tool-groups="">
    <FloatingToolBar tools={stripTools} />
    <ToolStack hidden={hidden} mobile={mobile} startsClosed={startsClosed} layout={layout} onLayoutChange={onLayoutChange}>{children}</ToolStack>
  </div>;
}
