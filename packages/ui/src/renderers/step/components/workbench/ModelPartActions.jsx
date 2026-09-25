import { TooltipHint } from "@hardcore/ui/primitives/tooltip";
import { Eye, EyeOff } from 'lucide-react';
import { Button } from '@hardcore/ui/primitives/button';

export default function ModelPartActions({ node, controls, disabled }) {
  const {focusedNodeIds=[], onTogglePartVisibility} = controls;
  const focused = focusedNodeIds.includes(node.selectionId);
  const hidden = node.leafPartIds?.length > 0 && node.leafPartIds.every(id => controls.hiddenPartIds?.includes(id));
  // The row itself has no right padding (its select button runs to the edge), so the eye brings its own.
  return <div className="flex shrink-0 items-center pr-1">
    <TooltipHint content={hidden ? 'Reveal' : 'Hide'}><Button variant="ghost" size="icon-xs" className="size-5 text-muted-foreground" disabled={disabled || focused} aria-label={`${hidden ? 'Reveal' : 'Hide'} ${node.label}`}
       onClick={() => onTogglePartVisibility?.(node.selectionId)}>
      {hidden ? <EyeOff className="size-3"/> : <Eye className="size-3"/>}
    </Button></TooltipHint>
  </div>;
}
