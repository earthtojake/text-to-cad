import { forwardRef } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { cn } from '@hardcore/ui/utils';

export const TREE_ROW_HEIGHT = 28;

/** Shared tree geometry and states. Callers own indentation and click semantics. */
export const TreeRowSurface = forwardRef(function TreeRowSurface({
  as: Component = 'div', active = false, cursor = false, className, style, children, ...props
}, ref) {
  return <Component ref={ref} className={cn(
    'flex min-w-0 w-full items-center gap-1.5 rounded-md pr-2 text-left text-xs font-normal transition-colors',
    active ? 'bg-accent text-accent-foreground' : 'text-foreground/80 hover:bg-accent/50',
    cursor && !active && 'bg-accent/30', className
  )} style={{ height: TREE_ROW_HEIGHT, ...style }} {...props}>{children}</Component>;
});

export function TreeRowChevron({ expanded, branch = true }) {
  if (!branch) return <span className="w-3 shrink-0" aria-hidden="true" />;
  const Icon = expanded ? ChevronDown : ChevronRight;
  return <Icon className="size-3 shrink-0 text-muted-foreground" aria-hidden="true" />;
}

export function TreeRowLabel({ children, className }) {
  return <span className={cn('min-w-0 truncate', className)}>{children}</span>;
}
