import { Search, X } from 'lucide-react';
import { cn } from '@text-to-cad/ui/utils';

/**
 * The filter box above a tree, and the highlight its matches use. Shared by the
 * file tree and the Model tree so the two filters are one control; each caller
 * owns its corpus, ranking and keyboard. `yieldWhileTyping`: the `trailing` controls step aside
 * while the box has focus, so the whole row is the box (a narrow panel's filter). `dense`: a
 * tool-stack panel's first row — a panel heading's 28px and 11px text, the box close to its walls,
 * so its buttons sit exactly where a heading's do. `inputProps`: the box's own ARIA, for a caller
 * whose filter is a combobox over its list.
 */
export function TreeFilterInput({ label, placeholder, value, onChange, onKeyDown, trailing, yieldWhileTyping = false, dense = false, clearLabel = 'Clear filter', inputProps, className, ...props }) {
  return <div {...props} data-slot="tree-filter" className={cn('group/filter flex shrink-0 items-center gap-1',
    // Dense, the separator is an inset line rather than a border, so the row's full 28px centre its
    // buttons exactly as a heading's (a border would take a pixel from under them).
    dense ? 'h-7 px-1 shadow-[inset_0_-1px_0_var(--border)]' : 'h-9 border-b px-2', className)}>
    <div className="relative flex min-w-0 flex-1 items-center">
      <Search className={cn('pointer-events-none absolute text-muted-foreground', dense ? 'left-1.5 size-2.5' : 'left-2 size-3')} />
      <input
        {...inputProps}
        aria-label={label}
        className={cn('w-full min-w-0 rounded-md bg-transparent pr-5 outline-none placeholder:text-muted-foreground focus:bg-background/70',
          dense ? 'h-5 pl-5 text-tiny' : 'h-6 pl-6.5 text-xs')}
        onChange={event => onChange(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        spellCheck={false}
        value={value}
      />
      {value !== '' ? <button
        aria-label={clearLabel}
        className="absolute right-1 flex size-4 items-center justify-center rounded-sm text-muted-foreground hover:bg-accent"
        onClick={() => onChange('')}
        type="button"
      ><X className="size-2.5" /></button> : null}
    </div>
    {/* The same spacing as a panel heading's buttons, so the icons line up down a stack. */}
    {trailing ? <div data-tree-filter-trailing="" className={cn('flex shrink-0 items-center gap-0.5',
      yieldWhileTyping && 'group-has-[input:focus]/filter:hidden')}>{trailing}</div> : null}
  </div>;
}

/** Matched characters use the primary text color without changing weight. */
export function TreeFilterHighlight({ text, indices, from = 0 }) {
  const hits = new Set(indices.map(index => index - from));
  return <>{[...text].map((character, index) => hits.has(index)
    ? <span className="text-foreground" key={index}>{character}</span>
    : <span key={index}>{character}</span>)}</>;
}
