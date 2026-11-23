import { Search, X } from 'lucide-react';
import { cn } from '@cad/ui/utils';
import { useI18n } from '@cad/ui/i18n';

/**
 * The filter box above a tree, and the highlight its matches use. Shared by the
 * file tree and the Model tree so the two filters are one control; each caller
 * owns its corpus, ranking and keyboard. `yieldWhileTyping`: the `trailing` controls step aside
 * while the box has focus, so the whole row is the box (a narrow panel's filter). `dense`: the view's
 * panel's search box, the head of the panel — a panel row's 28px and the panel's text, and no box of
 * its own drawn on focus: the caret says where typing goes. Dense, its inside is a row's
 * (`primitives/tree-row.jsx`): its box's edge on a row's fill line (8px in, in the view's panel), the
 * search icon a row's 12px glyph 8px inside it, on the rows' glyph line (16px), the text on the rows'
 * names' line (32px), the clear button a row action's (16x20, a 12px glyph) whose glyph ends 8px in
 * from the right edge. A phone's 16px glyphs keep the same anatomy. `onDismiss`: a box opened from a
 * button (the view's panel's search): its X is always there, named `dismissLabel`, and closes it.
 * `clearable={false}`: no X of its own (the view's panel's head carries its close in the search
 * button's place).
 */
export function TreeFilterInput({ label, placeholder, value, onChange, onKeyDown, inputRef, trailing, yieldWhileTyping = false, dense = false, clearLabel: givenClearLabel,
  onDismiss = null, dismissLabel, clearable = true, className, ...props }) {
  const { t } = useI18n();
  const clearLabel = onDismiss ? dismissLabel : givenClearLabel ?? t('tree.clearFilter');
  return <div {...props} data-slot="tree-filter" className={cn('group/filter flex shrink-0 items-center gap-1',
    // Dense, the separator is an inset line rather than a border, so the row's full 28px centre its
    // buttons (a border would take a pixel from under them).
    dense ? 'h-control px-1 shadow-[inset_0_-1px_0_var(--border)]' : 'h-9 border-b px-1', className)}>
    <div className={cn('relative flex min-w-0 flex-1 items-center', dense && 'h-full')}>
      <Search data-tree-filter-icon='' className={cn('pointer-events-none absolute text-muted-foreground', dense ? 'left-[7px] size-3' : 'left-[5px] size-3')} />
      <input
        ref={inputRef}
        aria-label={label}
        className={cn('w-full min-w-0 rounded-md bg-transparent pr-5 outline-none placeholder:text-muted-foreground',
          dense ? 'h-full pl-[23px] text-ui' : 'h-icon-button pl-[21px] text-xs focus:bg-background/70')}
        onChange={event => onChange(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        spellCheck={false}
        value={value}
      />
      {clearable && (value !== '' || onDismiss) ? <button
        aria-label={clearLabel}
        className={cn('absolute flex items-center justify-center rounded-sm text-muted-foreground hover:bg-accent', dense ? 'right-1.5 h-5 w-4' : 'right-1 size-4')}
        onClick={() => (onDismiss ? onDismiss() : onChange(''))}
        type="button"
        data-tree-filter-clear=''
      ><X className={dense ? 'size-3' : 'size-2.5'} /></button> : null}
    </div>
    {/* The same spacing as a panel heading's buttons, so the icons line up down a stack. */}
    {trailing ? <div data-tree-filter-trailing="" className={cn('flex shrink-0 items-center gap-0.5',
      yieldWhileTyping && 'group-has-[input:focus]/filter:hidden')}>{trailing}</div> : null}
  </div>;
}

/**
 * Matched characters in the brand's text colour, a weight up (`--brand-text`, medium): seen against a
 * name at full strength in either theme, as against a muted one.
 */
export function TreeFilterHighlight({ text, indices, from = 0 }) {
  const hits = new Set(indices.map(index => index - from));
  return <>{[...text].map((character, index) => hits.has(index)
    ? <span className="font-medium text-brand-text" data-tree-filter-hit="" key={index}>{character}</span>
    : <span key={index}>{character}</span>)}</>;
}

/**
 * Where `query` falls in `text`, ignoring case: the indices `TreeFilterHighlight` lights, for a list
 * searched by plain substring (a board's layers, a schematic's sheets); none where it does not.
 */
export function matchIndices(text, query) {
  const at = query ? String(text).toLowerCase().indexOf(query.toLowerCase()) : -1;
  return at < 0 ? [] : Array.from({ length: query.length }, (_, step) => at + step);
}

/** A row's name with the search's match lit in it (`matchIndices`). */
export function TreeFilterMatch({ text, query }) {
  const indices = matchIndices(text, query);
  return indices.length ? <TreeFilterHighlight text={String(text)} indices={indices} /> : text;
}

/**
 * The line over a search's hits saying how many there are, or that the first `shown` of `total` are
 * listed: every tree's, in the panel's text. `hit`: marks it as the panel's search's (`data-flat-panel-hit`).
 */
export function TreeSearchStatus({ shown, total, hit = false }) {
  const { t } = useI18n();
  return <p role="status" className="px-[calc(var(--tree-row-pad,5px)-var(--tree-row-hang,0px))] py-1 text-muted-foreground" data-tree-status="" data-flat-panel-hit={hit ? '' : undefined}>
    {total > shown ? t('tree.firstMatches', { shown, total: total.toLocaleString() }) : t(total === 1 ? 'tree.match' : 'tree.matches', { count: total })}
  </p>;
}
