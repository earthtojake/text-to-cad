import { Eye, EyeOff } from "lucide-react";
import { Button } from "@text-to-cad/ui/primitives/button";
import { ROW_NAME_UNDER_ACTIONS, treeRowActionsClass } from "@text-to-cad/ui/primitives/tree-row";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";

/** The room the eye takes at a row's right end: the row's `--row-actions`. */
const TREE_ROW_EYE_WIDTH = "1.5rem";

/**
 * What the eye does, and what it says while it is off and on:
 *  - `hide`: off, the row is drawn and the eye hides it; on, the row is hidden, its eye crossed out,
 *    and it reveals it.
 *  - `isolate`: off, the eye isolates the row, everything else stepping back; on, the row is
 *    isolated, its eye lit, and it lets everything back.
 */
const KINDS = Object.freeze({
  hide: Object.freeze({ off: "Hide", on: "Reveal" }),
  isolate: Object.freeze({ off: "Isolate", on: "Exit isolate" }),
});

/**
 * The style a row with an eye takes: the room the eye floats over, and its name fading out under
 * the eye, always while it is on, otherwise on hover (`ROW_NAME_UNDER_ACTIONS`).
 * @param {boolean} on
 */
export function treeRowEyeLayout(on) {
  return { style: { "--row-actions": TREE_ROW_EYE_WIDTH }, name: on ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover };
}

/**
 * A tree row's eye, as an assembly row's is (`settings-ui.md`): it floats over the row's right end,
 * shows on hover or keyboard focus, and stays while it is on, so what is hidden or isolated reads down
 * the tree without hovering. A press is the eye's alone: it never selects the row.
 *
 * @param {{ on: boolean, label: string, onToggle: () => void, kind?: "hide" | "isolate" }} props
 */
export default function TreeRowEye({ on, label, onToggle, kind = "hide" }) {
  const action = KINDS[kind][on ? "on" : "off"];
  const crossed = kind === "hide" && on;
  return <div data-row-actions="" className={treeRowActionsClass(on)}>
    <TooltipHint content={action}>
      <Button type="button" variant="ghost" size="icon-xs" aria-label={`${action} ${label}`}
        aria-pressed={kind === "isolate" ? on : undefined}
        className={cn("h-5 w-4", kind === "isolate" && on ? "text-foreground" : "text-muted-foreground")}
        onClick={event => { event.stopPropagation(); onToggle(); }}>
        {crossed ? <EyeOff className="size-3" aria-hidden="true"/> : <Eye className="size-3" aria-hidden="true"/>}
      </Button>
    </TooltipHint>
  </div>;
}
