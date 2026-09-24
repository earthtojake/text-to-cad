import { Eye, EyeOff, Focus } from 'lucide-react';
import { Button } from '@hardcore/ui/primitives/button';
import { cn } from '@hardcore/ui/utils';

// A row's actions show on hover (or keyboard focus) and stay shown while they are ON: an
// isolated row keeps its lit Isolate, a hidden row its crossed-out eye, so what is isolated
// or hidden can be read down the tree without hovering. Isolate is an assembly's; a single
// part has nothing to isolate it from.
const REVEAL_ON_HOVER = 'opacity-0 group-hover/row:opacity-100 focus-visible:opacity-100';

export default function ModelPartActions({ node, controls, disabled }) {
  const {focusedNodeIds=[], onTogglePartVisibility, onFocusTreeNode, onUnfocusTreeNode, isAssemblyView} = controls;
  const focused = focusedNodeIds.includes(node.selectionId);
  const hidden = node.leafPartIds?.length > 0 && node.leafPartIds.every(id => controls.hiddenPartIds?.includes(id));
  const canIsolate = isAssemblyView && typeof onFocusTreeNode === 'function';
  const isolateLabel = `${focused ? 'Exit isolate' : 'Isolate'} ${node.label}`;
  // The row itself has no right padding (its select button runs to the edge), so the actions bring their own.
  return <div className="flex shrink-0 items-center gap-0.5 pr-1">
    {canIsolate && <Button variant="ghost" size="icon-xs" disabled={disabled || hidden} aria-label={isolateLabel} aria-pressed={focused}
      title={focused ? 'Exit isolate' : 'Isolate'}
      className={cn('size-5', focused ? 'text-foreground' : cn('text-muted-foreground', REVEAL_ON_HOVER))}
      onClick={() => focused ? onUnfocusTreeNode?.(node.selectionId) : onFocusTreeNode(node.selectionId)}>
      <Focus className="size-3"/>
    </Button>}
    <Button variant="ghost" size="icon-xs" disabled={disabled || focused} aria-label={`${hidden ? 'Reveal' : 'Hide'} ${node.label}`}
      title={hidden ? 'Reveal' : 'Hide'} className={cn('size-5 text-muted-foreground', !hidden && REVEAL_ON_HOVER)}
      onClick={() => onTogglePartVisibility?.(node.selectionId)}>
      {hidden ? <EyeOff className="size-3"/> : <Eye className="size-3"/>}
    </Button>
  </div>;
}
