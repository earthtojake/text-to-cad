import { Fragment } from "react";
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
 * @property {boolean} [menuOnCornerOnly] Reserve main presses for the tool action; only its corner opens options.
 * @property {() => void} [onMenuSelect] Activate options without invoking the main button action.
 * @property {boolean} [secondPressOpensMenu]  The first press takes up the tool and a
 *   press while it is active is spent on its menu. The corner follows the same rule: until it is active a pointer
 *   press never reaches the menu trigger, and Enter, Space and ArrowDown select it.
 * @property {import("react").ReactNode} [subToolbar]  Drawn under the strip, in tool order,
 *   whenever it is given (its owner decides when).
 */

// A plain function, not a component: the strip's own output is the buttons.
function toolButton(tool) {
  const active = tool.active === true;
  const holdForMenu = tool.secondPressOpensMenu === true;
  const cornerOnly = tool.menuOnCornerOnly === true;
  const menuReady = active;
  const cornerPress = event => Boolean(event?.target?.closest?.("[data-tool-menu-corner]"));
  const button = <ToolbarButton className="relative" tooltipSide="top" label={tool.label} active={active} disabled={tool.disabled}
    aria-pressed={active} aria-description={tool.description}
    onPointerDown={holdForMenu ? event => {
      if (!menuReady || (cornerOnly && !cornerPress(event))) event.preventDefault();
      else if (cornerPress(event)) tool.onMenuSelect?.();
    } : undefined}
    onKeyDown={holdForMenu ? event => {
      if (menuReady && cornerOnly && event.key === "ArrowDown") { tool.onMenuSelect?.(); return; }
      if (cornerOnly && ["Enter", " "].includes(event.key)) { event.preventDefault(); tool.onSelect(); return; }
      if (!menuReady && ["Enter", " ", "ArrowDown"].includes(event.key)) {
        event.preventDefault(); tool.onSelect();
      }
    } : undefined}
    onClick={event => {
      // Popovers open on click; dropdowns open on pointer-down. Reserve the first
      // icon press for activating the tool in either kind of options panel.
      if (holdForMenu && (!menuReady || (cornerOnly && !cornerPress(event)))) event?.preventDefault?.();
      if (!menuReady || !cornerPress(event)) tool.onSelect();
    }}>
    {tool.icon}
    {tool.menu && holdForMenu ? <span data-tool-menu-corner="" aria-hidden="true"
      className="absolute bottom-0 right-0 flex size-2 items-center justify-center">
      <svg viewBox="0 0 5 5" className="pointer-events-none size-1" fill="currentColor"><path d="M5 0v5H0Z" /></svg>
    </span> : null}
  </ToolbarButton>;
  return tool.menu ? tool.menu(button) : button;
}

/**
 * The interaction tools: a dumb strip positioned by the viewport shell. It renders the
 * tools it is handed, left to right, then each tool's `subToolbar` beneath. It
 * holds no state and knows no tool by name.
 *
 * @param {{ tools: ViewportTool[], trailing?: import("react").ReactNode }} props  `trailing`: drawn after the
 *   tools, in the same strip (the Display tool's popover trigger).
 */
export default function FloatingToolBar({ tools = [], trailing = null }) {
  return (<div className="relative z-20 flex max-w-full shrink-0 flex-col items-end gap-1" data-cad-toolbar="tools">
      <div role="group" aria-label="Interaction tools" className={`pointer-events-auto inline-flex max-w-full flex-wrap items-center gap-0.5 rounded-md ${tools.length === 1 && !trailing ? "p-0.5" : "min-h-8 p-1"} ${FLOATING_TOOL_BAR_SURFACE_CLASS}`}>
        {tools.map(tool => <Fragment key={tool.id}>{toolButton(tool)}</Fragment>)}
        {trailing}
      </div>
    {tools.map(tool => (tool.subToolbar ? <Fragment key={tool.id}>{tool.subToolbar}</Fragment> : null))}
  </div>);
}
