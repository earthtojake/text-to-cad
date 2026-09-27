import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { Eye, EyeOff, Focus } from 'lucide-react';
import { Button } from '@text-to-cad/ui/primitives/button';
import { cn } from '@text-to-cad/ui/utils';

// A row's actions show on hover (or keyboard focus) and stay shown while they are ON: an
// isolated row keeps its lit Isolate, a hidden row its crossed-out eye, so what is isolated
// or hidden can be read down the tree without hovering. Isolate is an assembly's; a single
// part has nothing to isolate it from.
const REVEAL_ON_HOVER = 'opacity-0 group-hover/row:opacity-100 focus-visible:opacity-100';

/**
 * Whether a row's actions are showing without a hover — an isolated row's lit Isolate, a hidden
 * row's crossed-out eye — and how much of the row's right end they take: the row's name fades out
 * under them (`ROW_NAME_UNDER_ACTIONS`), never a backing drawn behind them.
 */
export function rowActionsLayout(node, controls) {
  const { focusedNodeIds = [], isAssemblyView, onFocusTreeNode } = controls;
  const focused = focusedNodeIds.includes(node.selectionId);
  const hidden = node.leafPartIds?.length > 0 && node.leafPartIds.every(id => controls.hiddenPartIds?.includes(id));
  const canIsolate = isAssemblyView && typeof onFocusTreeNode === 'function';
  return { shown: Boolean(node.selectionId) && (focused || hidden), width: canIsolate ? '2.5rem' : '1.5rem' };
}

// The name's fade under the actions: full strength up to half a rem before them, gone where they
// begin, so the row's own colour shows through, hover or not. `--row-actions` is the actions'
// width. Spelled out in full: Tailwind generates only class names it finds written whole.
export const ROW_NAME_UNDER_ACTIONS = {
  hover: 'group-hover/row:[mask-image:linear-gradient(to_right,#000_calc(100%-var(--row-actions)-0.5rem),transparent_calc(100%-var(--row-actions)))] group-focus-within/row:[mask-image:linear-gradient(to_right,#000_calc(100%-var(--row-actions)-0.5rem),transparent_calc(100%-var(--row-actions)))]',
  shown: '[mask-image:linear-gradient(to_right,#000_calc(100%-var(--row-actions)-0.5rem),transparent_calc(100%-var(--row-actions)))]',
};

export default function ModelPartActions({ node, controls, disabled }) {
  const {focusedNodeIds=[], onTogglePartVisibility, onFocusTreeNode, onUnfocusTreeNode, isAssemblyView} = controls;
  const focused = focusedNodeIds.includes(node.selectionId);
  const hidden = node.leafPartIds?.length > 0 && node.leafPartIds.every(id => controls.hiddenPartIds?.includes(id));
  const canIsolate = isAssemblyView && typeof onFocusTreeNode === 'function';
  const isolateLabel = `${focused ? 'Exit isolate' : 'Isolate'} ${node.label}`;
  // The actions float over the row's right end rather than taking width from it: the name runs the
  // row's full width and fades out under them (`ROW_NAME_UNDER_ACTIONS`), with nothing drawn behind
  // the buttons, so the row reads in its own (hover) colour throughout.
  const persistent = focused || hidden;
  return <div data-row-actions="" className={cn(
    "absolute inset-y-0 right-0 flex items-center pl-0.5 pr-1 transition-opacity",
    persistent ? "opacity-100" : "opacity-0 group-hover/row:opacity-100 focus-within:opacity-100")}>
    {canIsolate && <TooltipHint content={focused ? "Exit isolate" : "Isolate"}><Button variant="ghost" size="icon-xs" disabled={disabled || hidden} aria-label={isolateLabel} aria-pressed={focused}
      className={cn('h-5 w-4', focused ? 'text-foreground' : cn('text-muted-foreground', REVEAL_ON_HOVER))}
      onClick={() => focused ? onUnfocusTreeNode?.(node.selectionId) : onFocusTreeNode(node.selectionId)}>
      <Focus className="size-3"/>
    </Button></TooltipHint>}
    <TooltipHint content={hidden ? "Reveal" : "Hide"}><Button variant="ghost" size="icon-xs" disabled={disabled || focused} aria-label={`${hidden ? 'Reveal' : 'Hide'} ${node.label}`}
      className={cn('h-5 w-4 text-muted-foreground', !hidden && REVEAL_ON_HOVER)}
      onClick={() => onTogglePartVisibility?.(node.selectionId)}>
      {hidden ? <EyeOff className="size-3"/> : <Eye className="size-3"/>}
    </Button></TooltipHint>
  </div>;
}
