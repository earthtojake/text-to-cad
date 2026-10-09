import { Eye, EyeOff } from "lucide-react";
import { Button } from "@text-to-cad/ui/primitives/button";
import { treeRowActionsClass } from "@text-to-cad/ui/primitives/tree-row";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";

/** The room the eye takes at a row's right end: the row's `--row-actions`. */
export const ROBOT_ROW_ACTIONS_WIDTH = "1.5rem";

/**
 * A link's or a visual's Hide/Reveal eye, as an assembly row's is (`settings-ui.md`): it floats
 * over the row's right end, shows on hover or keyboard focus, and stays while everything the row
 * draws is hidden. A partly hidden link hides the rest. A row that draws nothing has no eye.
 */
export default function RobotVisibilityButton({ state, label, onChange }) {
  if (!state.ids.length || typeof onChange !== "function") return null;
  const action = state.allHidden ? "Reveal" : "Hide";
  return <div data-row-actions="" className={treeRowActionsClass(state.allHidden)}>
    <TooltipHint content={action}>
      <Button type="button" variant="ghost" size="icon-xs" aria-label={`${action} ${label}`} className="h-5 w-4 text-muted-foreground"
        onClick={event => { event.stopPropagation(); onChange(state.ids, state.allHidden); }}>
        {state.allHidden ? <EyeOff className="size-3" aria-hidden="true"/> : <Eye className="size-3" aria-hidden="true"/>}
      </Button>
    </TooltipHint>
  </div>;
}
