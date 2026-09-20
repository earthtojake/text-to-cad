import { Search, X } from 'lucide-react';

/**
 * The filter box above a tree, and the highlight its matches use. Shared by the
 * file tree and the Model tree so the two filters are one control; each caller
 * owns its corpus, ranking and keyboard.
 */
export function TreeFilterInput({ label, placeholder, value, onChange, onKeyDown, trailing, clearLabel = 'Clear filter' }) {
  return <div className="flex h-9 shrink-0 items-center gap-1 border-b px-2">
    <div className="relative flex min-w-0 flex-1 items-center">
      <Search className="pointer-events-none absolute left-2 size-3 text-muted-foreground" />
      <input
        aria-label={label}
        className="h-6 w-full min-w-0 rounded-md bg-transparent pr-5 pl-6.5 text-[12px] outline-none placeholder:text-muted-foreground focus:bg-background/70"
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
    {trailing}
  </div>;
}

/** Matched characters use the primary text color without changing weight. */
export function TreeFilterHighlight({ text, indices, from = 0 }) {
  const hits = new Set(indices.map(index => index - from));
  return <>{[...text].map((character, index) => hits.has(index)
    ? <span className="text-foreground" key={index}>{character}</span>
    : <span key={index}>{character}</span>)}</>;
}
