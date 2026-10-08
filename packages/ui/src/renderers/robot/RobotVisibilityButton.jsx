import { Eye, EyeOff } from "lucide-react";
import { Button } from "@text-to-cad/ui/primitives/button";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";

export default function RobotVisibilityButton({ state, label, onChange }) {
  if (!state.ids.length || typeof onChange !== "function") return null;
  const action = state.allHidden ? "Reveal" : "Hide";
  return <TooltipHint content={state.someHidden ? "Hide remaining visuals" : action}>
    <Button type="button" variant="ghost" size="icon-xs" aria-label={`${action} ${label}`}
      className={cn("mr-1 h-5 w-4 shrink-0 text-muted-foreground",
        !state.allHidden && !state.someHidden && "opacity-0 group-hover/row:opacity-100 focus-visible:opacity-100")}
      onClick={event => { event.stopPropagation(); onChange(state.ids, state.allHidden); }}>
      {state.allHidden ? <EyeOff className="size-3" aria-hidden="true"/> : <Eye className="size-3" aria-hidden="true"/>}
    </Button>
  </TooltipHint>;
}
