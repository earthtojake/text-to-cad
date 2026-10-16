import { DrawingToolbar } from "../../../../drawing/toolbar.jsx";
import ToolPanel, { ToolPanelFooterButton } from "../ToolPanel.jsx";

/**
 * Draw's panel, which leads the tool stack while Draw is up: the drawing tools, colour and history,
 * and once there is ink, Copy Drawing (the view with its ink) at its foot. Every view that offers
 * Draw draws this one.
 *
 * @param {{ drawing: import("../../../../drawing/session.js").DrawingSession, onCopy: () => unknown,
 *   copyShortcut?: string, disabled?: boolean }} props
 */
export default function DrawingPanel({ drawing, onCopy, copyShortcut = "", disabled = false }) {
  return <ToolPanel id="drawing" label="Drawing controls" collapsible={false}
    footer={drawing.hasContent ? <ToolPanelFooterButton label="Copy Drawing" shortcut={copyShortcut} disabled={disabled} onClick={onCopy} /> : null}>
    <DrawingToolbar drawing={drawing} layout="panel" className="p-1" />
  </ToolPanel>;
}
