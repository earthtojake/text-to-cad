import { forwardRef } from 'react';
import { ChevronRight } from 'lucide-react';
import { cn } from '@text-to-cad/ui/utils';

// Every tree's row is one compact 24px line: the explorer's in 12px text, a tree in the viewer's
// tool stack (Features, Links) in the panels' 11px text (`dense`).
export const TREE_ROW_HEIGHT = 24;
export const TREE_ROW_DENSE_HEIGHT = 24;
/** What each level of a tree adds to a row's indent: little, its rows hung from a faint line (`TreeRowGuides`). */
export const TREE_INDENT_PX = 10;
/** A row's glyph — its disclosure chevron, its kind's icon — small and light, 12px. */
export const TREE_GLYPH_CLASS = 'size-3 shrink-0 text-muted-foreground/70';
/** A kind icon's line: lighter than lucide's own, so the names carry the tree. */
export const TREE_GLYPH_STROKE = 1.5;
/** A dense tree's icon: a row's kind, the one glyph every tree draws. */
export const TREE_ROW_DENSE_ICON_CLASS = TREE_GLYPH_CLASS;

/** Shared tree geometry and states. Callers own indentation and click semantics. `dense`: a tool-stack tree. */
export const TreeRowSurface = forwardRef(function TreeRowSurface({
  as: Component = 'div', active = false, cursor = false, dense = false, className, style, children, ...props
}, ref) {
  return <Component ref={ref} className={cn(
    'relative flex min-w-0 w-full items-center gap-1.5 rounded-md pr-2 text-left font-normal transition-colors', dense ? 'text-tiny' : 'text-xs',
    active ? 'bg-accent text-accent-foreground' : 'text-foreground/80 hover:bg-accent/50',
    cursor && !active && 'bg-accent/30', className
  )} style={{ height: dense ? TREE_ROW_DENSE_HEIGHT : TREE_ROW_HEIGHT, ...style }} {...props}>{children}</Component>;
});

/** A branch's disclosure: one light chevron, turned down while it is open. A leaf keeps its place. */
export function TreeRowChevron({ expanded, branch = true }) {
  if (!branch) return <span className='w-3 shrink-0' aria-hidden='true' />;
  return <ChevronRight className={cn(TREE_GLYPH_CLASS, 'transition-transform duration-100', expanded && 'rotate-90')} aria-hidden='true' />;
}

/**
 * The faint lines a row `depth` levels down hangs from: one under each of its owners' chevrons, the
 * row's full height, so the rows under an open branch draw its line unbroken. `inset` is where the
 * row's first level starts, and `column` the width of the column its chevron is centred in.
 */
export function TreeRowGuides({ depth, inset = 0, column = 12 }) {
  if (!depth) return null;
  return Array.from({ length: depth }, (_, level) => <span key={level} aria-hidden='true' data-tree-guide=''
    className='pointer-events-none absolute inset-y-0 w-px bg-border' style={{ left: inset + level * TREE_INDENT_PX + column / 2 - 0.5 }} />);
}

export function TreeRowLabel({ children, className }) {
  return <span className={cn('min-w-0 truncate', className)}>{children}</span>;
}
