import { Circle, Eraser, Hand, Minus, PaintBucket, SquareMousePointer, MoveUpRight, Pencil, Redo2, Square, Trash2, Type, Undo2 } from 'lucide-react';
import { useState } from 'react';
import { ToolbarButton } from '@hardcore/ui/primitives/toolbar-button';

/**
 * The shared drawing controls: a CAD tool dropdown, and the
 * standalone drawing editor's own controls. It imports nothing of the drawing
 * SDK, so a host can show it without loading the editor.
 */

/**
 * The drawing editor's tools a host offers. Its lock, image, frame, embed and laser tools are left out.
 * @typedef {'selection' | 'hand' | 'freedraw' | 'line' | 'arrow' | 'rectangle' | 'ellipse' | 'text' | 'fill' | 'eraser'} DrawingTool
 */
// What puts ink down, the pen first: it is what Draw opens on, and the icon of the Draw tool itself.
/** @type {readonly { id: DrawingTool, label: string, Icon: typeof Hand }[]} */
const INK_TOOLS = [
  { id: 'freedraw', label: 'Pen', Icon: Pencil },
  { id: 'line', label: 'Line', Icon: Minus },
  { id: 'arrow', label: 'Arrow', Icon: MoveUpRight },
  { id: 'rectangle', label: 'Rectangle', Icon: Square },
  { id: 'ellipse', label: 'Ellipse', Icon: Circle },
  { id: 'text', label: 'Text', Icon: Type },
  // Not an SDK tool: `fill.ts` adds it.
  { id: 'fill', label: 'Fill area', Icon: PaintBucket },
  { id: 'eraser', label: 'Eraser', Icon: Eraser },
];
// Navigation comes first, followed by ink tools.
/** @type {readonly { id: DrawingTool, label: string, Icon: typeof Hand }[]} */
const HANDLING_TOOLS = [
  { id: 'selection', label: 'Select and move drawings', Icon: SquareMousePointer },
  { id: 'hand', label: 'Pan view', Icon: Hand },
];
/** @type {readonly { id: DrawingTool, label: string, Icon: typeof Hand }[]} */
export const DRAWING_TOOLBAR_TOOLS = [...HANDLING_TOOLS, ...INK_TOOLS];
/** @type {readonly DrawingTool[]} */
export const DRAWING_TOOLS = DRAWING_TOOLBAR_TOOLS.map(tool => tool.id);

// Saturated enough to stand out from a shaded model in either theme; black and
// white for the cases a neon cannot cover (a white page, a dark render).
/** @type {readonly { value: string, label: string }[]} */
export const DRAWING_COLORS = [
  { value: '#ff2d55', label: 'Neon red' },
  { value: '#ff7a00', label: 'Neon orange' },
  { value: '#ffe600', label: 'Neon yellow' },
  { value: '#39ff14', label: 'Neon green' },
  { value: '#00e5ff', label: 'Neon cyan' },
  { value: '#2979ff', label: 'Electric blue' },
  { value: '#d500f9', label: 'Neon magenta' },
  { value: '#ffffff', label: 'White' },
  { value: '#111111', label: 'Black' },
];
export const DEFAULT_OVERLAY_DRAWING_COLOR = DRAWING_COLORS[0].value;

// A shape's stroke in px; the pen draws at the same weight (`drawing/index.tsx`).
/** @type {readonly { value: number, label: string }[]} */
export const DRAWING_STROKE_WIDTHS = [
  { value: 1, label: 'Thin' },
  { value: 2, label: 'Medium' },
  { value: 4, label: 'Bold' },
];
// The weight as a line across a button: 1px, 2px or 3px drawn, whatever it draws on the model.
const strokeGlyph = width => <span aria-hidden="true" className="block w-3 rounded-full bg-current" style={{ height: `${width === 1 ? 1 : width === 2 ? 2 : 3}px` }} />;

// Two rows of seven by default, the width of the block fixed by that count; a
// container narrower than it wraps the same buttons into more rows.
const SURFACE = 'pointer-events-auto flex w-[calc(7*1.5rem+6*0.125rem+0.5rem+2px)] max-w-full flex-wrap gap-0.5 rounded-md border border-border bg-background p-1 text-foreground shadow-sm';
const swatch = color => ({ backgroundColor: color, boxShadow: 'inset 0 0 0 1px color-mix(in oklab, currentColor 35%, transparent)' });

/**
 * `layout="panel"`: the controls of a panel as wide as its column — the tools, wrapping to the
 * width they are given, then a rule, then the settings on a row of their own: colour, stroke width,
 * undo, redo and clear. Both rows share one column grid, so their buttons line up.
 * @param {{ drawing: import('./session.js').DrawingSession, className?: string, layout?: 'toolbar' | 'panel' }} props
 */
export function DrawingToolbar({ drawing, className = '', layout = 'toolbar' }) {
  // Which of the two pickers is open under the buttons, if either: the colours or the weights.
  const [choosing, setChoosing] = useState(/** @type {'' | 'color' | 'width'} */ (''));
  const choosingColor = choosing === 'color';
  const disabled = !drawing.ready;
  // No tooltips: over a canvas they cover the ink being pointed at. Every button keeps its accessible name.
  const toolButton = ({ id, label, Icon }) => <ToolbarButton key={id} tooltip={false} label={label} disabled={disabled}
    active={!disabled && drawing.tool === id} aria-pressed={!disabled && drawing.tool === id} onClick={() => drawing.selectTool(id)}>
    <Icon className="size-3" strokeWidth={2} aria-hidden="true" />
  </ToolbarButton>;
  const panel = layout === 'panel';
  const settings = <>
    <ToolbarButton tooltip={false} label="Color" disabled={disabled} active={choosingColor} aria-expanded={choosingColor} onClick={() => setChoosing(open => open === 'color' ? '' : 'color')}>
      <span className="size-3 rounded-full" style={swatch(drawing.color)} aria-hidden="true" />
    </ToolbarButton>
    <ToolbarButton tooltip={false} label="Stroke width" disabled={disabled} active={choosing === 'width'} aria-expanded={choosing === 'width'} onClick={() => setChoosing(open => open === 'width' ? '' : 'width')}>
      {strokeGlyph(drawing.strokeWidth ?? 2)}
    </ToolbarButton>
    <ToolbarButton tooltip={false} label="Undo" disabled={disabled || !drawing.canUndo} onClick={() => drawing.undo()}><Undo2 className="size-3" strokeWidth={2} aria-hidden="true" /></ToolbarButton>
    <ToolbarButton tooltip={false} label="Redo" disabled={disabled || !drawing.canRedo} onClick={() => drawing.redo()}><Redo2 className="size-3" strokeWidth={2} aria-hidden="true" /></ToolbarButton>
    <ToolbarButton tooltip={false} label="Clear drawing" disabled={disabled || !drawing.hasContent} onClick={() => drawing.clear()}><Trash2 className="size-3" strokeWidth={2} aria-hidden="true" /></ToolbarButton>
  </>;
  const palette = choosingColor && !disabled ? <div role="radiogroup" aria-label="Drawing color"
    className={panel ? "mt-1 flex flex-wrap gap-0.5" : SURFACE}>
    {DRAWING_COLORS.map(({ value, label }) => <ToolbarButton key={value} tooltip={false} label={label} role="radio"
      aria-checked={drawing.color.toLowerCase() === value} active={drawing.color.toLowerCase() === value}
      onClick={() => { drawing.selectColor(value); setChoosing(''); }}>
      <span className="size-3.5 rounded-full" style={swatch(value)} aria-hidden="true" />
    </ToolbarButton>)}
  </div> : choosing === 'width' && !disabled ? <div role="radiogroup" aria-label="Stroke width"
    className={panel ? "mt-1 flex flex-wrap gap-0.5" : SURFACE}>
    {DRAWING_STROKE_WIDTHS.map(({ value, label }) => <ToolbarButton key={value} tooltip={false} label={label} role="radio"
      aria-checked={(drawing.strokeWidth ?? 2) === value} active={(drawing.strokeWidth ?? 2) === value}
      onClick={() => { drawing.selectStrokeWidth?.(value); setChoosing(''); }}>
      {strokeGlyph(value)}
    </ToolbarButton>)}
  </div> : null;
  if (panel) {
    // A grid of 24px columns spread across the width, so however wide the panel is the buttons
    // wrap into even columns, the same columns in both rows.
    const grid = "grid min-w-0 grid-cols-[repeat(auto-fill,1.5rem)] justify-between gap-0.5";
    return <div className={`hardcore-drawing-toolbar ${className}`} data-drawing-controls="">
      <div role="group" aria-label="Drawing tools" className={grid}>{DRAWING_TOOLBAR_TOOLS.map(toolButton)}</div>
      {/* The rule runs the panel's full width, through its inset. */}
      <div role="separator" aria-orientation="horizontal" className="-mx-1 my-1 h-px bg-border" data-drawing-rule="" />
      <div role="group" aria-label="Drawing settings" className={grid}>{settings}</div>
      {palette}
    </div>;
  }
  return <div className={`hardcore-drawing-toolbar flex max-w-full flex-col items-end gap-1 ${className}`}>
    <div role="group" aria-label="Drawing tools" className={SURFACE}>
      {DRAWING_TOOLBAR_TOOLS.map(toolButton)}
      {settings}
    </div>
    {palette}
  </div>;
}
