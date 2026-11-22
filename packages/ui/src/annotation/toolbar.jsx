import { useContext, useEffect, useRef } from 'react';
import { Circle, Eraser, Highlighter, MoveUpRight, Pencil, Redo2, Slash, Square, Trash2, Type, Undo2 } from 'lucide-react';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger
} from '@cad/ui/primitives/dropdown-menu';
import { ToolbarButton } from '@cad/ui/primitives/toolbar-button';
import { cn } from '@cad/ui/utils';
import { FLOATING_SURFACE_CLASS } from '../lib/floatingSurface.js';
import SubToolbar, { SUB_TOOLBAR_WIDTH_CLASS } from '../renderers/kit/tools/SubToolbar.jsx';
import { DRAWING_SHORTCUTS, undoShortcuts } from '../renderers/kit/tools/toolShortcuts.js';
import { ViewerHostContext } from '../host/context.js';
import { toolFamily } from './tools.js';
import { useControlUsage } from '../usage/controls.js';
import { useI18n } from '@cad/ui/i18n';

/**
 * The drawing tools' sub-toolbar (`AnnotationToolbar`): two rows under the strip's Draw tool, on one surface, no rule
 * between them. The first is the tools that put ink down, a button each, the one in hand pressed (Pen, Highlighter,
 * Line, Arrow, Rectangle, Ellipse, Text: `DRAWING_CREATE_ENTRIES`) — choosing one is how Draw changes what it draws
 * with, its family taken up (`takeFamily`); the second, the Eraser, which takes ink already down
 * (`DRAWING_EDIT_ENTRIES`), then what is drawn next, its colour, stroke width and placement (on the surface under each
 * point, or on the plane of the surface the mark starts on), then Undo, Redo and Clear, all the annotation session's
 * (`session.js`). The style is the tool in hand's own — the pen's, the highlighter's, the shapes' — and the eraser,
 * which puts nothing down, has none: its pickers are greyed out. Every stroke is solid. The same colour and stroke
 * width dropdowns (`AnnotationStylePickers`) restyle the ink Select has picked, on its selection's bar.
 */

/** @typedef {import('./tools.js').AnnotationTool} AnnotationTool */
/** @typedef {{ id: AnnotationTool, key: string, label: string, Icon: typeof Pencil }} AnnotationToolEntry */
// What Pencil draws with, the pen first, then the highlighter and the eraser. Each says its `key` in the
// view's language (`drawingToolLabel`); `label` is its English name.
/** @type {readonly AnnotationToolEntry[]} */
export const PENCIL_TOOL_ENTRIES = [
  { id: 'freedraw', key: 'annotate.tool.freedraw', label: 'Pen', Icon: Pencil },
  { id: 'highlighter', key: 'annotate.tool.highlighter', label: 'Highlighter', Icon: Highlighter },
  { id: 'eraser', key: 'annotate.tool.eraser', label: 'Eraser', Icon: Eraser },
];
// What Shapes draws with, the line first; text with them, a mark put down in place.
/** @type {readonly AnnotationToolEntry[]} */
export const SHAPE_TOOL_ENTRIES = [
  { id: 'rectangle', key: 'annotate.tool.rectangle', label: 'Rectangle', Icon: Square },
  { id: 'line', key: 'annotate.tool.line', label: 'Line', Icon: Slash },
  { id: 'arrow', key: 'annotate.tool.arrow', label: 'Arrow', Icon: MoveUpRight },
  { id: 'ellipse', key: 'annotate.tool.ellipse', label: 'Ellipse', Icon: Circle },
  { id: 'text', key: 'annotate.tool.text', label: 'Text', Icon: Type },
];
/**
 * The drawing row's tools, one list in the order a person reaches for them, as design tools order theirs: the
 * freehand pen and highlighter, the shapes (line, arrow, rectangle, ellipse), text, then the tool that takes ink
 * already down, the Eraser.
 * @type {readonly AnnotationToolEntry[]}
 */
export const DRAWING_ROW_ENTRIES = ['freedraw', 'highlighter', 'line', 'arrow', 'rectangle', 'ellipse', 'text', 'eraser']
  .map(id => [...PENCIL_TOOL_ENTRIES, ...SHAPE_TOOL_ENTRIES].find(entry => entry.id === id));
/** The drawing row's first row: the seven tools that put ink down. */
export const DRAWING_CREATE_ENTRIES = DRAWING_ROW_ENTRIES.slice(0, 7);
/** Its second row's first: the tool that takes ink already down, the Eraser. */
export const DRAWING_EDIT_ENTRIES = DRAWING_ROW_ENTRIES.slice(7);
/**
 * The two families that draw, the tool modes the strip's one Draw tool takes up (`drawStripTool`): freehand
 * (`pencil`: the pen, the highlighter, the eraser) and the shapes (`shapes`: the shapes and text), each keeping
 * what it draws with and its style apart. The drawing row lists their tools as one (`DRAWING_ROW_ENTRIES`).
 * @type {readonly { id: import('./tools.js').AnnotationFamily, entries: readonly AnnotationToolEntry[] }[]}
 */
export const DRAWING_TOOLS = [
  { id: 'pencil', entries: PENCIL_TOOL_ENTRIES },
  { id: 'shapes', entries: SHAPE_TOOL_ENTRIES },
];
/** The strip's drawing tool's id: one tool, Draw, over both families' modes. */
export const DRAW_TOOL = 'draw';
/** Whether a tool mode is one of Draw's (`pencil`, `shapes`). */
export const isDrawingMode = mode => mode === 'pencil' || mode === 'shapes';
/**
 * The strip's one drawing tool, **Draw**: a plain button, no chevron or menu. It shows what it draws with now (the
 * family up, else the one last drawn with: the session's `lastFamily`), its tooltip that tool and its key ("Rectangle
 * R"), and a press takes that family up. What it draws with is the drawing row's (`AnnotationToolbar`: both families'
 * tools). Both families are its modes (`drawFamilies`): a drawing tool's key takes it up with that family
 * (`takeFamily`, `pressToolKey`).
 *
 * @param {{ toolMode: string | null, annotation: import('./session.js').AnnotationSession, takeFamily(family: 'pencil' | 'shapes'): void,
 *   disabled?: boolean, t: Function, group?: string }} options
 */
export function drawStripTool({ toolMode, annotation, takeFamily, disabled = false, t, group }) {
  const active = isDrawingMode(toolMode);
  const family = active ? toolMode : annotation.lastFamily === 'shapes' ? 'shapes' : 'pencil';
  const variant = drawingToolVariant(family, annotation);
  const Icon = annotationToolIcon(variant);
  return {
    id: DRAW_TOOL, label: t('annotate.tool.draw'), tooltip: drawingToolLabel(variant, t), shortcut: DRAWING_SHORTCUTS[variant], active, disabled,
    icon: <Icon className="size-3" strokeWidth={2} aria-hidden="true" />, ...(group ? { group } : {}),
    onSelect: () => takeFamily(family), takeFamily, drawFamilies: DRAWING_TOOLS.map(entry => entry.id)
  };
}
/** A drawing tool's name in `t`'s language: Draw's (`draw`) or what one draws with (`freedraw`, `line`, …). */
export const drawingToolLabel = (id, t) => t(`annotate.tool.${id}`);
/** The icon of a drawing tool (the pen's for one it does not know): a strip tool shows the variant it draws with. */
export const annotationToolIcon = id => ([...PENCIL_TOOL_ENTRIES, ...SHAPE_TOOL_ENTRIES].find(tool => tool.id === id) || PENCIL_TOOL_ENTRIES[0]).Icon;
/** The tool a drawing strip tool draws with now: `annotation.pencil` for Pencil, `annotation.shape` for Shapes. */
export const drawingToolVariant = (family, annotation) => (family === 'shapes' ? annotation.shape : annotation.pencil);

// Saturated enough to stand out from a shaded model in either theme; black and
// white for the cases a neon cannot cover (a white page, a dark render).
/** @type {readonly { value: string, label: string }[]} */
// Each says its name in the view's language by its `key`; `label` is its English name.
export const ANNOTATION_COLORS = [
  { value: '#ff2d55', label: 'Neon red', key: 'annotate.color.neonRed' },
  { value: '#ff7a00', label: 'Neon orange', key: 'annotate.color.neonOrange' },
  { value: '#ffe600', label: 'Neon yellow', key: 'annotate.color.neonYellow' },
  { value: '#39ff14', label: 'Neon green', key: 'annotate.color.neonGreen' },
  { value: '#00e5ff', label: 'Neon cyan', key: 'annotate.color.neonCyan' },
  { value: '#2979ff', label: 'Electric blue', key: 'annotate.color.electricBlue' },
  { value: '#d500f9', label: 'Neon magenta', key: 'annotate.color.neonMagenta' },
  { value: '#ffffff', label: 'White', key: 'annotate.color.white' },
  { value: '#111111', label: 'Black', key: 'annotate.color.black' },
];
export const DEFAULT_OVERLAY_ANNOTATION_COLOR = ANNOTATION_COLORS[0].value;
const WHITE = '#ffffff', BLACK = '#111111';
/**
 * The colours offered under `colorScheme`: the neons, and one neutral that reads against the
 * viewer — white in dark mode, near-black in light mode, where white would vanish into the page.
 * @param {'light' | 'dark'} colorScheme
 */
export function annotationColors(colorScheme) {
  const neutral = colorScheme === 'dark' ? WHITE : BLACK;
  return ANNOTATION_COLORS.filter(option => option.value !== (neutral === WHITE ? BLACK : WHITE));
}

// A shape's stroke in px; the pen draws a little heavier at the same weight (`geometry.js`).
// Each keeps a name for assistive technology; the menu shows the line alone.
/** @type {readonly { value: number, label: string }[]} */
export const ANNOTATION_STROKE_WIDTHS = [
  { value: 1, label: 'Thin', key: 'annotate.stroke.thin' },
  { value: 2, label: 'Medium', key: 'annotate.stroke.medium' },
  { value: 4, label: 'Bold', key: 'annotate.stroke.bold' },
  { value: 6, label: 'Heavy', key: 'annotate.stroke.heavy' },
];
// How ink lies, as its glyph: a sphere, in three dimensions, for ink drawn on the surface under it; a
// flat sheet seen in perspective for ink drawn on a plane.
const GLYPH = { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeLinecap: 'round', strokeLinejoin: 'round' };
function SurfaceGlyph({ strokeWidth = 2, ...props }) {
  return <svg {...GLYPH} strokeWidth={strokeWidth} {...props}>
    <circle cx="12" cy="12" r="9" />
    <ellipse cx="12" cy="12" rx="9" ry="3.5" />
    <ellipse cx="12" cy="12" rx="3.5" ry="9" />
  </svg>;
}
function PlaneGlyph({ strokeWidth = 2, ...props }) {
  return <svg {...GLYPH} strokeWidth={strokeWidth} {...props}>
    <path d="M7.5 6.5h14l-5 11h-14Z" />
    <path d="M14.5 6.5l-5 11M5 12h14" strokeWidth={1.25} strokeOpacity="0.5" />
  </svg>;
}
/** @typedef {'surface' | 'plane'} AnnotationPlacement */
// How ink lies: on the surface of the model under each point, or on the plane of the surface the mark
// starts on (`annotation3d.js`'s `levelOf`). Only what is drawn next: ink already down stays put.
/** @type {readonly { value: AnnotationPlacement, label: string, Icon: typeof Pencil }[]} */
export const ANNOTATION_PLACEMENTS = [
  { value: 'surface', label: 'On surface', key: 'annotate.placement.surface', Icon: SurfaceGlyph },
  { value: 'plane', label: 'On plane', key: 'annotate.placement.plane', Icon: PlaneGlyph },
];
const placementGlyph = placement => {
  const { Icon } = ANNOTATION_PLACEMENTS.find(option => option.value === placement) ?? ANNOTATION_PLACEMENTS[0];
  return <Icon className="size-3" strokeWidth={2} aria-hidden="true" />;
};
// The weight as a straight line, drawn at the weight itself (1, 2, 4 or 6px), round-ended, whatever it draws on the model.
const strokeGlyph = width => <svg {...GLYPH} aria-hidden="true" className="h-4 w-[18px]" viewBox="0 0 18 16" strokeWidth={width} data-stroke-weight={width}>
  <path d="M3 8h12" />
</svg>;
// Stroke width's own glyph, fixed whatever is chosen (as Figma's and Excalidraw's are): three lines thin to thick. Its menu
// shows each choice's line.
const ROWS_GLYPH = { viewBox: '0 0 16 16', fill: 'none', stroke: 'currentColor', strokeLinecap: 'round', className: 'size-4', 'aria-hidden': 'true' };
const strokeWidthIcon = <svg {...ROWS_GLYPH} data-glyph="stroke-width">
  <path d="M2.5 3h11" strokeWidth={1} /><path d="M2.5 7.5h11" strokeWidth={2} /><path d="M2.5 12.5h11" strokeWidth={3.5} />
</svg>;
const swatch = color => ({ backgroundColor: color, boxShadow: 'inset 0 0 0 1px color-mix(in oklab, currentColor 35%, transparent)' });
const ROW = 'flex min-w-0 flex-wrap items-center gap-0.5';

// A menu's heading, as the strip's menus have one (Select's "Filter" and Measure's "Measure filter", Display's).
const menuHeading = text => <DropdownMenuLabel className="font-normal text-muted-foreground">{text}</DropdownMenuLabel>;

/**
 * One of a mark's styles as a dropdown, laid out as the strip's menus are: its button shows the
 * value (no chevron; `icon`, a fixed glyph in its place), and opens a menu headed with its name, a row per choice, its glyph and its
 * name, the check on the right of the current one. One chosen closes it. `bare`: no heading and no
 * names, the glyphs alone (Stroke width: a line per weight), each choice keeping its name for assistive technology.
 */
function StyleMenu({ label, options, value, glyph, icon, onChange, disabled, bare = false }) {
  const { t } = useI18n();
  return <DropdownMenu modal={false}>
    <DropdownMenuTrigger asChild>
      {/* Its name on a hover (Stroke width: a button of lines, named by it). */}
      <ToolbarButton label={label} disabled={disabled}>{icon ?? glyph(value)}</ToolbarButton>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" sideOffset={4} collisionPadding={8} aria-label={label}
      className={cn(FLOATING_SURFACE_CLASS, bare ? 'w-auto min-w-0' : 'w-40', 'data-[state=closed]:animate-none!')}>
      {bare ? null : menuHeading(label)}
      <DropdownMenuRadioGroup value={String(value)} onValueChange={next => onChange(options.find(option => String(option.value) === next).value)}>
        {options.map(option => <DropdownMenuRadioItem key={option.value} value={String(option.value)} aria-label={t(option.key)} data-style-option={option.value}>
          <span className="grid min-w-3.5 place-items-center">{glyph(option.value)}</span>{bare ? null : t(option.key)}
        </DropdownMenuRadioItem>)}
      </DropdownMenuRadioGroup>
    </DropdownMenuContent>
  </DropdownMenu>;
}
const colorGlyph = color => <span className="size-3 rounded-full" style={swatch(color)} aria-hidden="true" />;
// The colour wheel's swatch: every hue round the circle.
const WHEEL = { background: 'conic-gradient(#ff2d55, #ffe600, #39ff14, #00e5ff, #2979ff, #d500f9, #ff2d55)' };

/**
 * The system's colour picker, behind a hidden input: `open()` shows it, `input` is the element to render. Its colour is taken as it
 * closes (`change`), not as it is dragged (`input`): one change, one step of the history, however long it is dragged.
 */
function useColorPicker(value, onChange) {
  const picker = useRef(null);
  const commit = useRef(onChange);
  commit.current = onChange;
  useEffect(() => {
    const input = picker.current;
    if (!input) return undefined;
    const changed = () => commit.current(input.value);
    input.addEventListener('change', changed);
    return () => input.removeEventListener('change', changed);
  }, []);
  const open = () => {
    const input = picker.current;
    if (!input) return;
    try { input.showPicker(); } catch { input.click(); }
  };
  const input = <input ref={picker} type="color" value={/^#[0-9a-f]{6}$/i.test(value) ? value : '#ff2d55'} onChange={() => {}}
    tabIndex={-1} aria-hidden="true" className="pointer-events-none absolute size-0 opacity-0" data-color-picker="" />;
  return { input, open };
}

/**
 * The colour, as a dropdown: its button shows the colour in hand, and opens a grid of swatches, with no
 * heading, unnamed (each
 * keeps its name for assistive technology) — the palette, then the colour wheel, which opens the
 * system's colour picker for any other colour. A colour off the palette shows on the button as it
 * is, and no swatch is marked.
 */
function ColorMenu({ value, colors, onChange, disabled }) {
  const { input, open: pick } = useColorPicker(value, onChange);
  const { t } = useI18n();
  return <>
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <ToolbarButton tooltip={false} label={t('annotate.colour')} disabled={disabled}>{colorGlyph(value)}</ToolbarButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" sideOffset={4} collisionPadding={8} aria-label={t('annotate.colour')}
        className={cn(FLOATING_SURFACE_CLASS, 'w-auto min-w-0 p-1.5 data-[state=closed]:animate-none!')}>
        <div className="grid grid-cols-3 gap-1">
          {colors.map(option => <DropdownMenuItem key={option.value} aria-label={option.key ? t(option.key) : option.label} data-color={option.value}
            data-checked={option.value === value ? '' : undefined} onSelect={() => onChange(option.value)}
            className="size-control justify-center rounded-md p-0 data-[checked]:bg-accent">
            <span className="size-4 rounded-full" style={swatch(option.value)} aria-hidden="true" />
          </DropdownMenuItem>)}
          <DropdownMenuItem aria-label={t('annotate.customColour')} data-color="custom" onSelect={pick} className="size-control justify-center rounded-md p-0">
            <span className="size-4 rounded-full" style={WHEEL} aria-hidden="true" />
          </DropdownMenuItem>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
    {input}
  </>;
}

/**
 * The colour, stroke width and placement dropdowns (`StyleMenu`): what is drawn next, on the drawing row
 * (`AnnotationToolbar`), and the ink picked, on its selection's bar. Each is left out where it has nothing to set
 * (`width` null: no stroke picked); `placement` only where Draw puts ink down.
 * `children` follow them on their row.
 *
 * @param {{ color: string, width?: number | null, placement?: AnnotationPlacement | null,
 *   onColor(value: string): void, onWidth?(value: number): void,
 *   onPlacement?(value: AnnotationPlacement): void, colors?: readonly { value: string, label: string }[],
 *   disabled?: boolean, label: string, className?: string,
 *   children?: import('react').ReactNode }} props
 */
export function AnnotationStylePickers({ color, width = null, placement = null, onColor, onWidth, onPlacement,
  colors = ANNOTATION_COLORS, disabled = false, label, className = ROW, children = null }) {
  const { t } = useI18n();
  return <div role="group" aria-label={label} className={className}>
    <ColorMenu value={color.toLowerCase()} colors={colors} onChange={onColor} disabled={disabled} />
    {width == null ? null : <StyleMenu bare label={t('annotate.strokeWidth')} options={ANNOTATION_STROKE_WIDTHS} value={width} glyph={strokeGlyph} icon={strokeWidthIcon}
      onChange={value => onWidth?.(value)} disabled={disabled} />}
    {placement == null ? null : <StyleMenu label={t('annotate.placement')} options={ANNOTATION_PLACEMENTS} value={placement} glyph={placementGlyph}
      onChange={value => onPlacement?.(value)} disabled={disabled} />}
    {children}
  </div>;
}

const icon = Icon => <Icon className="size-3" strokeWidth={2} aria-hidden="true" />;
const GROUP = 'flex items-center gap-1';

/**
 * The drawing tools' sub-toolbar (`kit/tools/SubToolbar.jsx`), under the strip while Draw is in hand: two rows on one
 * surface, the same for both families, no rule between them. First the tools that put ink down, as buttons, the one in
 * hand pressed (Pen, Highlighter, Line, Arrow, Rectangle, Ellipse and Text; choosing one is all Draw needs to draw
 * with it); then the Eraser, and what is drawn next, its Colour (`annotationColors`, for the viewer's `colorScheme`,
 * or any from the wheel), Stroke width and Placement, each a dropdown laid out as the strip's are (kept per drawing
 * kind: the pen's, the highlighter's, the shapes'; greyed out under the Eraser), then Undo, Redo and Clear annotations.
 * Undo and Redo walk the view's one history (the session's `undo`, `redo`), as ⌘Z and ⇧⌘Z do (`useViewerShortcuts.js`),
 * each off where the history has no step that way, its tooltip its key (`undoShortcuts`, for the host's platform).
 * A flat view, where ink has nowhere to lie but the drawing, has no placement to choose (`placements={false}`). On a
 * phone, where the rows are as wide as the view, each wraps rather than scrolls.
 * @param {{ annotation: import('./session.js').AnnotationSession, colorScheme?: 'light' | 'dark', placements?: boolean }} props
 */
export function AnnotationToolbar({ annotation, colorScheme = 'light', placements = true, takeFamily = null }) {
  const controls = useControlUsage();
  const { t } = useI18n();
  const disabled = !annotation.ready;
  const { style } = annotation;
  // The eraser draws nothing: Color, Stroke width and Placement stay on the row, greyed out, so it does not jump.
  const erasing = annotation.tool === 'eraser';
  const keys = undoShortcuts(useContext(ViewerHostContext)?.environment?.platform);
  const choose = id => { annotation.selectTool(id); takeFamily?.(toolFamily(id)); };
  // Each tool its name and its key in a tooltip ("Rectangle R"): the row's way to learn the letters.
  const toolButton = ({ id, Icon }) => <ToolbarButton key={id} shortcut={DRAWING_SHORTCUTS[id]} label={drawingToolLabel(id, t)} tooltip={drawingToolLabel(id, t)} disabled={disabled}
    active={!disabled && annotation.tool === id} aria-pressed={!disabled && annotation.tool === id} onClick={() => choose(id)}>
    {icon(Icon)}
  </ToolbarButton>;
  // Two rows of seven on one surface, left-aligned on the row's padding, the gap between them the row's own 4px, no rule:
  // the tools that put ink down (`DRAWING_CREATE_ENTRIES`), then the Eraser, which takes ink already down, beside what
  // is drawn next — its Colour, Stroke width and Placement — then Undo, Redo and Clear.
  return <SubToolbar label={t('annotate.controls')} data-annotation-controls="" className={cn('text-to-cad-annotation-toolbar flex-col flex-nowrap items-start', SUB_TOOLBAR_WIDTH_CLASS, 'data-[touch]:w-auto')}>
    <div role="group" aria-label={t('annotate.drawTools')} className={cn(GROUP, 'flex-wrap')} data-annotation-row="create">
      {DRAWING_CREATE_ENTRIES.map(toolButton)}
    </div>
    <div className={cn(GROUP, 'flex-wrap')} data-annotation-row="style">
      <div role="group" aria-label={t('annotate.editTools')} className={GROUP}>{DRAWING_EDIT_ENTRIES.map(toolButton)}</div>
      <AnnotationStylePickers label={t('annotate.style')} className={GROUP} disabled={disabled || erasing}
        colors={annotationColors(colorScheme)} color={style.color} width={style.strokeWidth}
        placement={placements ? style.placement : null}
        onColor={annotation.selectColor} onWidth={annotation.selectStrokeWidth} onPlacement={annotation.selectPlacement}>
        <ToolbarButton label={t('annotate.undo')} shortcut={keys.undo} disabled={disabled || !annotation.canUndo} onClick={annotation.undo}>{icon(Undo2)}</ToolbarButton>
        <ToolbarButton label={t('annotate.redo')} shortcut={keys.redo} disabled={disabled || !annotation.canRedo} onClick={annotation.redo}>{icon(Redo2)}</ToolbarButton>
        <ToolbarButton tooltip={false} label={t('annotate.clear')} disabled={disabled || !annotation.hasContent} onClick={() => { controls.used('annotate_clear'); annotation.clear(); }}>{icon(Trash2)}</ToolbarButton>
      </AnnotationStylePickers>
    </div>
  </SubToolbar>;
}
