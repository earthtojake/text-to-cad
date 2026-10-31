import { Eye, EyeOff } from "lucide-react";
import { Button } from "@text-to-cad/ui/primitives/button";
import { treeRowActionsClass } from "@text-to-cad/ui/primitives/tree-row";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { useControlUsage } from "../../usage/controls.js";
import { useI18n } from "@text-to-cad/ui/i18n";

/** The room the eye takes at a row's right end: the row's `--row-actions`. */
export const ROBOT_ROW_ACTIONS_WIDTH = "1.5rem";

/**
 * A link's or a visual's Hide/Reveal eye, as an assembly row's is (`settings-ui.md`): it floats
 * over the row's right end, shows on hover or keyboard focus, and stays while everything the row
 * draws is hidden. A partly hidden link hides the rest. A row that draws nothing has no eye.
 */
export default function RobotVisibilityButton({ state, label, onChange }) {
  const usage = useControlUsage();
  const { t } = useI18n();
  if (!state.ids.length || typeof onChange !== "function") return null;
  const action = state.allHidden ? t("tree.reveal") : t("tree.hide");
  return <div data-row-actions="" className={treeRowActionsClass(state.allHidden)}>
    <TooltipHint content={action}>
      <Button type="button" variant="ghost" size="icon-xs" aria-label={t(state.allHidden ? "tree.revealNamed" : "tree.hideNamed", { name: label })} className="h-5 w-4 text-muted-foreground"
        onClick={event => { event.stopPropagation(); usage.used("tree_visibility"); onChange(state.ids, state.allHidden); }}>
        {state.allHidden ? <EyeOff className="size-3" aria-hidden="true"/> : <Eye className="size-3" aria-hidden="true"/>}
      </Button>
    </TooltipHint>
  </div>;
}
