import { Fragment } from "react";
import { TooltipProvider } from "@hardcore/ui/primitives/tooltip";
import { ToolbarButton } from "./ToolbarButton.js";

export const FLOATING_TOOL_BAR_SURFACE_CLASS = "bg-background border border-border text-foreground shadow-sm";

/**
 * One tool of the strip. The strip draws it; whoever hands it over decides what
 * it is, when it exists and what pressing it does.
 *
 * @typedef {object} ViewportTool
 * @property {string} id
 * @property {string} label  The button's accessible name and tooltip.
 * @property {import("react").ReactNode} icon
 * @property {boolean} [active]
 * @property {boolean} [disabled]
 * @property {() => void} onSelect  Every press of the button.
 * @property {string} [description]  `aria-description`.
 * @property {(trigger: import("react").ReactElement) => import("react").ReactNode} [menu]
 *   Wraps the button as its menu's trigger.
 * @property {boolean} [secondPressOpensMenu]  The first press takes up the tool and a
 *   press while it is active is spent on its menu: until it is active a pointer
 *   press never reaches the menu trigger, and Enter, Space and ArrowDown select it.
 * @property {import("react").ReactNode} [subToolbar]  Drawn under the strip, in tool order,
 *   whenever it is given (its owner decides when).
 */

// A plain function, not a component: the strip's own output is the buttons.
function toolButton(tool) {
  const active = tool.active === true;
  const holdForMenu = tool.secondPressOpensMenu === true;
  const button = <ToolbarButton label={tool.label} active={active} disabled={tool.disabled}
    aria-pressed={active} aria-description={tool.description}
    onPointerDown={holdForMenu ? event => { if (!active) event.preventDefault(); } : undefined}
    onKeyDown={holdForMenu ? event => {
      if (!active && ["Enter", " ", "ArrowDown"].includes(event.key)) {
        event.preventDefault(); tool.onSelect();
      }
    } : undefined}
    onClick={() => tool.onSelect()}>
    {tool.icon}
  </ToolbarButton>;
  return tool.menu ? tool.menu(button) : button;
}

/**
 * The interaction tools: a dumb strip at the viewport's corner. It renders the
 * tools it is handed, left to right, then each tool's `subToolbar` beneath. It
 * holds no state and knows no tool by name.
 *
 * @param {{ tools: ViewportTool[], position?: import("react").CSSProperties, label?: string }} props
 */
export default function FloatingToolBar({ tools = [], position, label = "Interaction tools" }) {
  return (<div className="absolute z-20 flex max-w-[calc(100%-28px)] flex-col items-end gap-1"
    data-cad-toolbar="tools" style={position}>
    <TooltipProvider delayDuration={250}>
      <div role="group" aria-label={label} className={`pointer-events-auto inline-flex min-h-8 max-w-full flex-wrap items-center gap-0.5 rounded-md p-1 ${FLOATING_TOOL_BAR_SURFACE_CLASS}`}>
        {tools.map(tool => <Fragment key={tool.id}>{toolButton(tool)}</Fragment>)}
      </div>
    </TooltipProvider>
    {tools.map(tool => (tool.subToolbar ? <Fragment key={tool.id}>{tool.subToolbar}</Fragment> : null))}
  </div>);
}
