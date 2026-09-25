import { TooltipHint } from "@hardcore/ui/primitives/tooltip";
import { Eye, EyeOff } from 'lucide-react';
import { Button } from '@hardcore/ui/primitives/button';
import { cn } from '@hardcore/ui/utils';

// A row's one action, Hide, shows on hover (or keyboard focus) and stays shown while it is
// ON: a hidden row keeps its crossed-out eye, so what is hidden can be read down the tree
// without hovering. Isolation is not a row action: a double-click on a component or
// subassembly isolates it, and the isolation bar at the top of the tree ends it.
const REVEAL_ON_HOVER = 'opacity-0 group-hover/row:opacity-100 focus-visible:opacity-100';

export default function ModelPartActions({ node, controls, disabled }) {
  const {focusedNodeIds=[], onTogglePartVisibility} = controls;
  const focused = focusedNodeIds.includes(node.selectionId);
  const hidden = node.leafPartIds?.length > 0 && node.leafPartIds.every(id => controls.hiddenPartIds?.includes(id));
  // The row itself has no right padding (its select button runs to the edge), so the eye brings its own.
  return <div className="flex shrink-0 items-center pr-1">
    <TooltipHint content={hidden ? "Reveal" : "Hide"}><Button variant="ghost" size="icon-xs" disabled={disabled || focused} aria-label={`${hidden ? 'Reveal' : 'Hide'} ${node.label}`}
      className={cn('size-5 text-muted-foreground', !hidden && REVEAL_ON_HOVER)}
      onClick={() => onTogglePartVisibility?.(node.selectionId)}>
      {hidden ? <EyeOff className="size-3"/> : <Eye className="size-3"/>}
    </Button></TooltipHint>
  </div>;
}
