import { forwardRef } from 'react';
import { useViewerMobile } from '../file-viewer/responsive.js';
import { ChevronRight } from 'lucide-react';
import { cn } from '@cad/ui/utils';
import { DESKTOP_SCALE, PHONE_SCALE, scaleFor } from '../lib/scale.js';

// Every tree's row is one compact line at THE scale (`globals.css`): the explorer's a small row (`--cad-row-sm`, 24px
// on a desktop) in 12px text, a list of the view's panel a row (`--cad-row`, 28px) in the panel's one text size
// (`dense`: `--cad-text-panel`); a phone's both 36px, from the scale, never from the row.
export const TREE_ROW_HEIGHT = DESKTOP_SCALE.rowSm;
export const TREE_ROW_DENSE_HEIGHT = DESKTOP_SCALE.row;
/** A phone's row (the scale's, `lib/scale.js`). */
export const TREE_ROW_TOUCH_HEIGHT = PHONE_SCALE.row;
/** The height, in px, of a panel's tree row in the viewer at hand (for a virtual list's arithmetic): the scale's row. */
export const useTreeRowHeight = () => scaleFor(useViewerMobile()).row;
/** What each level of a tree adds to a row's indent: little, its rows hung from a faint line under each owner's glyph. */
export const TREE_INDENT_PX = 10;
/** The explorer's rows' left padding (`FolderExplorer.jsx`, `ModelList.jsx`): the default of `--tree-row-pad`. */
export const TREE_ROW_INSET_PX = 5;
/** A row's glyph — its disclosure chevron, its kind's icon — small and light, 12px. */
export const TREE_GLYPH_CLASS = 'size-3 shrink-0 text-muted-foreground/70';
/** A kind icon's line: lighter than lucide's own, so the names carry the tree. */
export const TREE_GLYPH_STROKE = 1.5;
/** A dense tree's icon: a row's kind, the one glyph every tree draws. */
export const TREE_ROW_DENSE_ICON_CLASS = TREE_GLYPH_CLASS;
/**
 * A row's name: its button (or span) after the glyph slot, the label first to truncate and its muted
 * detail 4px after it, ending 8px before the row's right end, on the panel's right line.
 */
export const TREE_ROW_NAME_CLASS = 'flex h-full min-w-0 flex-1 items-center gap-1 rounded pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

// Where a row's geometry comes from: whoever holds the rows sets these once (the view's panel, `PanelSurface.jsx`:
// its rows hang half its inset out past it, `--tree-row-hang`, their fill reaching that far, and pad half its inset,
// `--tree-row-pad`, so their first glyph stands on the inset and their last action's glyph ends the inset from the
// right, `--tree-row-actions-pad`); the defaults are the explorer's, whose rows hang out by nothing.
const PAD = `var(--tree-row-pad, ${TREE_ROW_INSET_PX}px)`;
const HANG = 'var(--tree-row-hang, 0px)';
const GLYPH = 'var(--tree-row-glyph, 12px)';
const rowPadding = depth => (depth ? `calc(${PAD} + ${depth * TREE_INDENT_PX}px)` : PAD);

/**
 * One row of a list: the scale's small row (24px; the row, 28, in the view's panel, `dense`; both 36 on a phone), its radius and its hover,
 * selected (`active`: the brand's subtle fill, `--brand-subtle`) and cursor fills. A row given a `depth` owns its horizontal geometry: its padding
 * (`--tree-row-pad`, and 10px a level), its hang (`--tree-row-hang`), a faint guide under each of its owners' glyph slots, and no
 * right padding (its name's and its actions' own). Its children are, in order: its ONE glyph slot — a
 * branch's chevron (`TreeRowToggle`) or a leaf's kind icon or marker (`TreeRowGlyph`: a layer's colour
 * takes the slot instead of an icon), never two, so every name at a level starts on one column — its
 * name (`TREE_ROW_NAME_CLASS`: `TreeRowName` and `TreeRowDetail`), then its actions (`TreeRowActions`),
 * `actions` of them, which the name fades out under. Without a `depth` (the explorer's rows) the caller pads it. `dense`: the panel's text,
 * its names at full strength.
 */
export const TreeRowSurface = forwardRef(function TreeRowSurface({
  as: Component = 'div', active = false, cursor = false, dense = false, depth = null, actions = 0, className, style, children, ...props
}, ref) {
  const owned = depth !== null;
  return <Component ref={ref} className={cn(
    'relative flex min-w-0 w-full items-center gap-1 rounded-md text-left font-normal transition-colors', owned ? 'pr-0' : 'pr-2', dense ? 'text-ui' : 'text-xs',
    active ? 'bg-brand-subtle text-foreground' : cn(dense ? 'text-foreground' : 'text-foreground/80', 'hover:bg-accent/50'),
    cursor && !active && 'bg-accent/30', className
  )} data-tree-row="" style={{
    height: dense ? 'var(--cad-row)' : 'var(--cad-row-sm)',
    ...(owned ? { paddingLeft: rowPadding(depth), marginInline: `calc(${HANG} * -1)`, width: `calc(100% + 2 * ${HANG})` } : null),
    ...(actions ? { '--row-actions': `${0.5 + actions}rem` } : null),
    ...style,
  }} {...props}>{children}{owned ? <Guides depth={depth} /> : null}</Component>;
});

// The faint lines a row `depth` levels down hangs from: one under each of its owners' glyph slots,
// the row's full height, so the rows under an open branch draw its line unbroken.
function Guides({ depth }) {
  return Array.from({ length: depth }, (_, level) => <span key={level} aria-hidden='true' data-tree-guide=''
    className='pointer-events-none absolute inset-y-0 w-px bg-border'
    style={{ left: `calc(${PAD} + ${level * TREE_INDENT_PX}px + ${GLYPH} / 2 - 0.5px)` }} />);
}

const SLOT_CLASS = 'relative grid h-full min-w-3 shrink-0 place-items-center';

/**
 * A row's glyph slot, always its first child: 12px wide (a phone's 16px glyphs widen it), its glyph
 * centred — the row's kind icon, a layer's colour — or nothing, the slot kept. A row has one slot, never
 * a second glyph; a row a level down hangs from its owner's line by its `depth` (`TreeRowSurface`).
 */
export function TreeRowGlyph({ className, children, ...props }) {
  return <span data-tree-row-glyph='' aria-hidden='true' className={cn(SLOT_CLASS, className)} {...props}>{children}</span>;
}

/** A branch's disclosure: one light chevron, turned down while it is open. The explorer draws it bare. */
export function TreeRowChevron({ expanded }) {
  return <ChevronRight className={cn(TREE_GLYPH_CLASS, 'transition-transform duration-100', expanded && 'rotate-90')} aria-hidden='true' />;
}

/**
 * A branch's glyph slot: its chevron as the button that opens or shuts it (`label`, `aria-expanded`).
 * `locked`: the chevron a mark nobody can press, at half strength (while something else decides the
 * tree's shape). `mark`: a chevron the pointer opens and shuts but the keyboard passes by, for a row
 * whose name is that button already (a block's).
 */
export function TreeRowToggle({ open, label, onToggle, locked = false, mark = false, ...props }) {
  if (locked || mark) return <span data-tree-row-glyph='' aria-hidden='true' className={cn(SLOT_CLASS, locked && 'opacity-50', mark && 'cursor-pointer')}
    onClick={mark ? onToggle : undefined} {...props}><TreeRowChevron expanded={open} /></span>;
  return <span data-tree-row-glyph='' className={SLOT_CLASS}>
    <button type='button' aria-label={label} aria-expanded={open} onClick={onToggle} {...props}
      className='grid h-full w-full place-items-center rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'>
      <TreeRowChevron expanded={open} />
    </button>
  </span>;
}

/**
 * A row's actions (Isolate, the Hide/Reveal eye) float over its right end, and its name fades out
 * under them: full strength up to half a rem before them, gone where they begin, so the row's own
 * colour shows through, hover or not. `--row-actions` (set on the row by its `actions` count) is the
 * actions' width; `shown` while an action is on, `hover` otherwise. Spelled out in full: Tailwind
 * generates only class names it finds written whole.
 */
export const ROW_NAME_UNDER_ACTIONS = {
  hover: 'group-hover/row:[mask-image:linear-gradient(to_right,#000_calc(100%-var(--row-actions)-0.5rem),transparent_calc(100%-var(--row-actions)))] group-focus-within/row:[mask-image:linear-gradient(to_right,#000_calc(100%-var(--row-actions)-0.5rem),transparent_calc(100%-var(--row-actions)))] [@media(hover:none)]:[mask-image:linear-gradient(to_right,#000_calc(100%-var(--row-actions)-0.5rem),transparent_calc(100%-var(--row-actions)))]',
  shown: '[mask-image:linear-gradient(to_right,#000_calc(100%-var(--row-actions)-0.5rem),transparent_calc(100%-var(--row-actions)))]',
};

/**
 * The actions' box over the row's right end: each a 16x20 button with a 12px glyph, 2px apart, the
 * last one's glyph `--tree-row-actions-pad` and its button's 2px from the row's right end. Shown on
 * the row's hover or keyboard focus (always on a touch screen, which cannot hover), and kept while one
 * is on (`persistent`).
 */
export function TreeRowActions({ persistent = false, className, children }) {
  return <div data-row-actions='' className={cn('absolute inset-y-0 right-0 flex items-center gap-0.5 pl-0.5 transition-opacity',
    persistent ? 'opacity-100' : 'opacity-0 group-hover/row:opacity-100 focus-within:opacity-100 [@media(hover:none)]:opacity-100', className)}
  style={{ paddingRight: 'var(--tree-row-actions-pad, 3px)' }}>{children}</div>;
}

export function TreeRowLabel({ children, className }) {
  return <span className={cn('min-w-0 truncate', className)}>{children}</span>;
}

/** A row's name where a detail follows it: whole before the detail gives way. */
export function TreeRowName({ children, className }) {
  return <TreeRowLabel className={cn('max-w-full shrink-0', className)}>{children}</TreeRowLabel>;
}

/**
 * A row's detail after its name, 4px on, muted, in the row's own text: a count (a layer's entities, a
 * net's pins), a page number, an owner's path. Every tree's details and counts are this one, so a count
 * reads the same in every view; it is the first to truncate.
 */
export function TreeRowDetail({ children, className }) {
  return <TreeRowLabel className={cn('flex-1 text-muted-foreground', className)}>{children}</TreeRowLabel>;
}

/**
 * A heading over a run of a list's rows (a board's Front and Back, a model's parameters' file, a tab's
 * name over its search hits): a 28px line in the panel's text, muted, its words on the rows' glyph line
 * (on the panel's inset, no padding of its own), so it reads as a label of the rows under it, never as one of them.
 * `as`: its element (an `h3`, or an `li` in a list it heads).
 */
export function TreeRowHeading({ as: Component = 'h3', className, children, ...props }) {
  return <Component className={cn('flex h-control min-w-0 items-center text-ui font-normal text-muted-foreground', className)} data-tree-heading='' {...props}>
    <span className='min-w-0 truncate'>{children}</span>
  </Component>;
}

/**
 * The faint lines an explorer row `depth` levels down hangs from, for rows that pad themselves:
 * `inset` is where the row's first level starts, and `column` the width its chevron is centred in.
 */
export function TreeRowGuides({ depth, inset = 0, column = 12 }) {
  if (!depth) return null;
  return Array.from({ length: depth }, (_, level) => <span key={level} aria-hidden='true' data-tree-guide=''
    className='pointer-events-none absolute inset-y-0 w-px bg-border' style={{ left: inset + level * TREE_INDENT_PX + column / 2 - 0.5 }} />);
}

// The names' widths of the loading rows, as shares of the room after the glyph: uneven, so they read as a list.
const LOADING_NAME_WIDTHS = Object.freeze([62, 44, 74, 36, 56, 30]);

/**
 * Where a tree's rows will stand while its file is still loading and it has none to show: placeholder rows in the
 * rows' own geometry (`TreeRowSurface`'s height, padding and hang, so each glyph block stands where a row's glyph does
 * and each bar where its name starts), a block the glyph's size and a bar for the name, of a few widths, fading out
 * downwards, in the muted ink, pulsing gently where motion is welcome and still where it is not. Nothing in it is a row
 * (`data-tree-row`): it is drawn only until rows arrive. `label`: what assistive technology hears instead ("Loading").
 * @param {{ label: string, rows?: number }} props
 */
export function TreeRowsLoading({ label, rows = LOADING_NAME_WIDTHS.length }) {
  const height = useTreeRowHeight();
  return <div role='status' className='motion-safe:animate-pulse' data-tree-rows-loading=''>
    <span className='sr-only'>{label}</span>
    {LOADING_NAME_WIDTHS.slice(0, rows).map((width, at) => <div key={at} aria-hidden='true' data-tree-row-placeholder=''
      className='relative flex min-w-0 items-center gap-1'
      style={{ height, paddingLeft: PAD, marginInline: `calc(${HANG} * -1)`, width: `calc(100% + 2 * ${HANG})`, opacity: 1 - at * 0.16 }}>
      <span className={SLOT_CLASS}><span className='block rounded-[3px] bg-muted-foreground/20' style={{ width: GLYPH, height: GLYPH }} data-tree-row-placeholder-glyph='' /></span>
      <span className='block h-2 rounded-full bg-muted-foreground/20' style={{ width: `${width}%` }} data-tree-row-placeholder-name='' />
    </div>)}
  </div>;
}
