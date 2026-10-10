import { CONNECTED_SELECTION, MEASURE_SNAP_MODES, SELECT_MODES, connectedSelectionApplies } from '../../workbench/selectionFilter.js';
import { DropdownMenuCheckboxItem } from '@text-to-cad/ui/primitives/dropdown-menu';
import ToolModeMenu from "../../../kit/tools/ToolModeMenu.jsx";
import { ToolModeIcon, modeMenuItems } from "../../../kit/tools/modeGlyphs.jsx";

// A STEP's modes, drawn as every file's tool modes are (`kit/tools/modeGlyphs.jsx`): a cube whole
// and bold for Parts; faint, with the element a pick takes drawn solid, for Faces (its top face
// filled) and Edges (its front edge heavy); a dot in a ring for Points.
const CUBE = 'M12 2.5 20.5 7.25v9.5L12 21.5l-8.5-4.75v-9.5Z';
const CUBE_SEAMS = 'M3.5 7.25 12 12l8.5-4.75M12 12v9.5';
const faintCube = weight => <g strokeWidth={1.5 * weight} strokeOpacity="0.45"><path d={CUBE} /><path d={CUBE_SEAMS} /></g>;
const MODE_GLYPHS = Object.freeze({
  parts: weight => <g strokeWidth={2 * weight}><path d={CUBE} /><path d={CUBE_SEAMS} /></g>,
  faces: weight => <>{faintCube(weight)}<path d="M12 2.5 20.5 7.25 12 12 3.5 7.25Z" fill="currentColor" strokeWidth={2 * weight} /></>,
  edges: weight => <>{faintCube(weight)}<path d="M12 12v9.5" strokeWidth={3.5 * weight} /></>,
  points: weight => <><circle cx="12" cy="12" r="8.5" strokeWidth={1.5 * weight} strokeOpacity="0.45" /><circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" /></>,
});

const known = (modes, mode) => modes.some(item => item.id === mode) ? mode : 'all';

/** The Select tool's button icon for `mode`: the pointer, badged with the mode (`data-select-mode`). */
export function SelectModeIcon({ mode, ...props }) {
  const value = known(SELECT_MODES, mode);
  return <ToolModeIcon tool="select" glyphs={MODE_GLYPHS} mode={value} data-select-mode={value} {...props} />;
}

/** The Measure tool's button icon for its snapping `mode`: the ruler, badged with the mode (`data-measure-mode`). */
export function MeasureModeIcon({ mode, ...props }) {
  const value = known(MEASURE_SNAP_MODES, mode);
  return <ToolModeIcon tool="measure" glyphs={MODE_GLYPHS} mode={value} data-measure-mode={value} {...props} />;
}

const modeItems = (tool, modes) => modeMenuItems(tool, MODE_GLYPHS, modes);

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
