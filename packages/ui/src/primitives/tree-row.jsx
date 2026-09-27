import { forwardRef } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { cn } from '@text-to-cad/ui/utils';

export const TREE_ROW_HEIGHT = 28;
// A tree in the viewer's tool stack (Features, Links): the panels' 11px text, 24px rows.
export const TREE_ROW_DENSE_HEIGHT = 24;
/** A dense tree's icon: a row's kind, 12px. */
export const TREE_ROW_DENSE_ICON_CLASS = 'size-3 shrink-0 text-muted-foreground';

/** Shared tree geometry and states. Callers own indentation and click semantics. `dense`: a tool-stack tree. */
export const TreeRowSurface = forwardRef(function TreeRowSurface({
  as: Component = 'div', active = false, cursor = false, dense = false, className, style, children, ...props
}, ref) {
  return <Component ref={ref} className={cn(
    'flex min-w-0 w-full items-center gap-1.5 rounded-md pr-2 text-left font-normal transition-colors', dense ? 'text-tiny' : 'text-xs',
    active ? 'bg-accent text-accent-foreground' : 'text-foreground/80 hover:bg-accent/50',
    cursor && !active && 'bg-accent/30', className
  )} style={{ height: dense ? TREE_ROW_DENSE_HEIGHT : TREE_ROW_HEIGHT, ...style }} {...props}>{children}</Component>;
});

export function TreeRowChevron({ expanded, branch = true, dense = false }) {
  if (!branch) return <span className={dense ? 'w-2.5 shrink-0' : 'w-3 shrink-0'} aria-hidden="true" />;
  const Icon = expanded ? ChevronDown : ChevronRight;
  return <Icon className={cn(dense ? 'size-2.5' : 'size-3', 'shrink-0 text-muted-foreground')} aria-hidden="true" />;
}

export function TreeRowLabel({ children, className }) {
  return <span className={cn('min-w-0 truncate', className)}>{children}</span>;
}
