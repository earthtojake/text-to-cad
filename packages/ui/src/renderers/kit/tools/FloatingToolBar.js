import { Fragment } from "react";
import { ToolbarButton } from "@text-to-cad/ui/primitives/toolbar-button";
import { FLOATING_CHROME_SURFACE_CLASS } from "../../../lib/floatingSurface.js";

/**
 * One tool of the strip. The strip draws it; whoever hands it over decides what
 * it is, when it exists and what pressing it does. A press is the tool's only action: a tool
 * has no menu on the strip — what it can be set to is its panel in the tool stack.
 *
 * @typedef {object} ViewportTool
 * @property {string} id
 * @property {string} label  The button's accessible name and tooltip.
 * @property {import("react").ReactNode} icon
 * @property {boolean} [active]
 * @property {boolean} [disabled]
 * @property {() => void} onSelect  Every press of the button.
 * @property {string} [description]  `aria-description`.
 * @property {{ id: string, label: string, startsClosed?: boolean }} [panel]  The panel of the tool's
 *   own that a person can close (Select's tree, by its `id` and its name; `startsClosed` where this
 *   file opens with it closed, as a single part does): while it is closed the frame marks the tool
 *   (`panelClosed`), and a press on the tool while it is up opens the panel again (`RendererShell.jsx`).
 * @property {boolean} [panelClosed]  The tool's panel is closed: a small mark in the button's
 *   bottom-right corner, the flyout corner that says the tool has more to show.
 */

// A plain function, not a component: the strip's own output is the buttons.
function toolButton(tool) {
  const active = tool.active === true;
  return <ToolbarButton className="relative" tooltipSide="top" label={tool.label} active={active} disabled={tool.disabled}
    aria-pressed={active} aria-description={tool.description} onClick={() => tool.onSelect()}>
    {tool.icon}
    {tool.panelClosed ? <span data-tool-panel-closed="" aria-hidden="true" className="pointer-events-none absolute bottom-0 right-0 flex size-2 items-center justify-center">
      <svg viewBox="0 0 5 5" className="size-1" fill="currentColor"><path d="M5 0v5H0Z" /></svg>
    </span> : null}
  </ToolbarButton>;
}

/**
 * The interaction tools: a dumb strip positioned by the viewport shell. It renders the
 * tools it is handed, left to right. It holds no state and knows no tool by name.
 *
 * @param {{ tools: ViewportTool[] }} props
 */
export default function FloatingToolBar({ tools = [] }) {
  // No tools, no strip: an empty bar is never drawn.
  if (!tools.length) return null;
  return (<div className="relative z-20 flex max-w-full shrink-0 flex-col items-end gap-1" data-cad-toolbar="tools">
      <div role="group" aria-label="Interaction tools" className={`pointer-events-auto inline-flex min-h-8 max-w-full flex-wrap items-center gap-0.5 rounded-md p-1 ${FLOATING_CHROME_SURFACE_CLASS}`}>
        {tools.map(tool => <Fragment key={tool.id}>{toolButton(tool)}</Fragment>)}
      </div>
  </div>);
}
