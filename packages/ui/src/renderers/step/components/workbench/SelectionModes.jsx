import { useId } from 'react';
import { CONNECTED_SELECTION, MEASURE_SNAP_MODES, SELECT_MODES, connectedSelectionApplies } from '../../workbench/selectionFilter.js';
import { DropdownMenuCheckboxItem } from '@text-to-cad/ui/primitives/dropdown-menu';
import ToolModeMenu from "../../../kit/tools/ToolModeMenu.jsx";

// The two tools that pick in modes share one set of drawings. Each mode has ONE glyph, drawn on
// the 24-unit grid: a cube whole and bold for Parts; faint, with the element a pick takes drawn
// solid, for Faces (its top face filled) and Edges (its front edge heavy); a dot in a ring for
// Points. The mode menu in the tool's panel shows it at full size — All shows the tool's own
// glyph, Select's pointer or Measure's ruler. The strip's button shows the tool's glyph with the mode's glyph shrunk to a
// badge in its top-right corner (none for All); the tool's glyph steps down to the bottom-left to
// make room, and the badge is cut out of it, so the two never touch at the strip's 14px.
// `weight` thickens a glyph's strokes for the badge, which is drawn at under half size.
const TOOL_GLYPHS = Object.freeze({
  select: <path d="M4.037 4.688a.495.495 0 0 1 .651-.651l16 6.5a.5.5 0 0 1-.063.947l-6.124 1.58a2 2 0 0 0-1.438 1.435l-1.579 6.126a.5.5 0 0 1-.947.063z" />,
  measure: <>
    <path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.41 2.41 0 0 1 0-3.4l2.6-2.6a2.41 2.41 0 0 1 3.4 0Z" />
    <path d="m14.5 12.5 2-2" /><path d="m11.5 9.5 2-2" /><path d="m8.5 6.5 2-2" /><path d="m17.5 15.5 2-2" />
  </>,
});
const CUBE = 'M12 2.5 20.5 7.25v9.5L12 21.5l-8.5-4.75v-9.5Z';
const CUBE_SEAMS = 'M3.5 7.25 12 12l8.5-4.75M12 12v9.5';
const faintCube = weight => <g strokeWidth={1.5 * weight} strokeOpacity="0.45"><path d={CUBE} /><path d={CUBE_SEAMS} /></g>;
const MODE_GLYPHS = Object.freeze({
  parts: weight => <g strokeWidth={2 * weight}><path d={CUBE} /><path d={CUBE_SEAMS} /></g>,
  faces: weight => <>{faintCube(weight)}<path d="M12 2.5 20.5 7.25 12 12 3.5 7.25Z" fill="currentColor" strokeWidth={2 * weight} /></>,
  edges: weight => <>{faintCube(weight)}<path d="M12 12v9.5" strokeWidth={3.5 * weight} /></>,
  points: weight => <><circle cx="12" cy="12" r="8.5" strokeWidth={1.5 * weight} strokeOpacity="0.45" /><circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" /></>,
});
const SVG = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" };
// Where the badge sits: the mode's glyph at 0.44 of its size, centred on (18.5, 5.5).
const BADGE_SCALE = 0.44, BADGE_CENTRE = [18.5, 5.5];
const BADGE_TRANSFORM = `translate(${BADGE_CENTRE[0] - 12 * BADGE_SCALE} ${BADGE_CENTRE[1] - 12 * BADGE_SCALE}) scale(${BADGE_SCALE})`;

/** A mode's own glyph at full size, for the mode menu in the tool's panel: `mode` "all" is the tool's glyph (`tool`). */
function ModeGlyph({ tool, mode, ...props }) {
  const glyph = MODE_GLYPHS[mode];
  return <svg {...SVG} data-mode-glyph={glyph ? mode : tool} {...props}>{glyph ? glyph(1) : TOOL_GLYPHS[tool]}</svg>;
}

/** The strip's composite: the tool's glyph (`tool`, "select" or "measure") badged with `mode`'s glyph, none for "all". */
function ToolModeIcon({ tool, mode, ...props }) {
  const mask = `tool-mode-${useId().replace(/[^\w-]/g, '')}`;
  const glyph = MODE_GLYPHS[mode];
  return <svg {...SVG} data-tool-icon-base={tool} {...props}>
    {glyph ? <>
      <mask id={mask}><rect width="24" height="24" fill="white" /><circle cx={BADGE_CENTRE[0]} cy={BADGE_CENTRE[1]} r="6.25" fill="black" /></mask>
      <g mask={`url(#${mask})`}><g transform="translate(0 4) scale(0.84)" strokeWidth="2.3">{TOOL_GLYPHS[tool]}</g></g>
      <g data-tool-icon-badge={mode} transform={BADGE_TRANSFORM}>{glyph(1.7)}</g>
    </> : TOOL_GLYPHS[tool]}
  </svg>;
}

const known = (modes, mode) => modes.some(item => item.id === mode) ? mode : 'all';

/** The Select tool's button icon for `mode`: the pointer, badged with the mode (`data-select-mode`). */
export function SelectModeIcon({ mode, ...props }) {
  const value = known(SELECT_MODES, mode);
  return <ToolModeIcon tool="select" mode={value} data-select-mode={value} {...props} />;
}

/** The Measure tool's button icon for its snapping `mode`: the ruler, badged with the mode (`data-measure-mode`). */
export function MeasureModeIcon({ mode, ...props }) {
  const value = known(MEASURE_SNAP_MODES, mode);
  return <ToolModeIcon tool="measure" mode={value} data-measure-mode={value} {...props} />;
}

const modeItems = (tool, modes) => modes.map(item => ({ id: item.id, label: item.label,
  icon: <ModeGlyph tool={tool} mode={item.id} className="size-3.5" aria-hidden="true" /> }));

/**
 * Measure's snapping, in the Measure panel's heading beside its fold chevron: a button showing
 * the mode in hand, whose dropdown lists the four modes, each its glyph at full size (All the
 * ruler). Measure has no menu on the strip.
 *
 * @param {{ mode: string, onModeChange(mode: string): void, disabled?: boolean }} props
 */
export function MeasureModeMenu({ mode, onModeChange, disabled = false }) {
  return <ToolModeMenu label="Measure snapping" modes={modeItems('measure', MEASURE_SNAP_MODES)} value={known(MEASURE_SNAP_MODES, mode)}
    onChange={onModeChange} disabled={disabled} />;
}

/**
 * Select's mode, in the Features panel's filter row beside its fold chevron: a button showing
 * the mode in hand, whose dropdown lists the four exclusive modes (Parts only in an assembly),
 * then the connected-selection options that do something under the mode in hand, as checkboxes
 * — both under All, Group faces under Faces, Group edges under Edges, none under Parts. An option
 * that does nothing is not shown, and keeps its choice for when it does; ticking one leaves the
 * menu open. Select has no menu on the strip.
 *
 * @param {{ mode: string, onModeChange(mode: string): void, assembly: boolean,
 *   connected: { edgeChain: boolean, tangentFaces: boolean },
 *   onConnectedChange(id: "edgeChain" | "tangentFaces", checked: boolean): void, disabled?: boolean }} props
 */
export function SelectModeMenu({ mode, onModeChange, assembly, connected, onConnectedChange, disabled = false }) {
  const modes = SELECT_MODES.filter(item => assembly || !item.assemblyOnly);
  const value = known(modes, mode);
  const options = CONNECTED_SELECTION.filter(option => connectedSelectionApplies(option.id, value));
  return <ToolModeMenu label="Select mode" modes={modeItems('select', modes)} value={value} onChange={onModeChange} disabled={disabled}>
    {options.length ? options.map(option => <DropdownMenuCheckboxItem key={option.id} checked={connected[option.id] === true}
      onSelect={event => event.preventDefault()} onCheckedChange={checked => onConnectedChange(option.id, checked === true)}>
      {option.label}
    </DropdownMenuCheckboxItem>) : null}
  </ToolModeMenu>;
}
