import { PositionIcon } from '../kit/tools/ChangedDot.jsx';
import { CONNECTED_SELECTION, SELECT_GEOMETRY, connectedSelectionApplies } from './xbfSelectionFilter.js';
import { DropdownMenuCheckboxItem, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem } from '@cad/ui/primitives/dropdown-menu';
import SelectFilterMenu from "../kit/tools/select/SelectFilterMenu.jsx";
import { useControlUsage } from "../../usage/controls.js";
import { useI18n } from "@cad/ui/i18n";
import { ModeGlyph, ToolModeIcon, modeGlyphIcon } from "../kit/tools/select/modeGlyphs.jsx";

// Select's button, Measure's and Select's menu, which read on an engine document as the STEP
// renderer's did. The glyphs are the kit's (`kit/tools/select/modeGlyphs.jsx`).

const lucideIcon = Icon => <Icon className="size-3.5" strokeWidth={2} aria-hidden="true" />;

/**
 * Select's two tools, how a pick is made: Select, a click picks what is under it; Box select, a drag
 * draws a box and picks what is visible in it (`@cad/core/lib/viewer/boxSelect.js`), a click still
 * picking as Select's does. Select when a file opens.
 */
export const SELECT_TOOLS = Object.freeze([
  { id: 'select', key: 'tool.select', glyph: 'select' },
  { id: 'box', key: 'select.boxSelect', glyph: 'boxSelect' },
]);

/**
 * The Select tool's button icon: the pointer, or Box select's pointer in a square (`tool`), badged
 * with what it picks alone (`mode`), none for All.
 */
export function SelectIcon({ tool = "select", mode = "all", ...props }) {
  return <ToolModeIcon tool={tool === 'box' ? 'boxSelect' : 'select'} mode={mode} {...props} />;
}

// What each of Measure's modes is badged with: a vertex the point in a ring, an edge or a face the cube's.
const MEASURE_BADGES = Object.freeze({ vertex: "points", edge: "edges", face: "faces" });

/** The Measure tool's button icon: the ruler, badged with what it picks alone (`mode`), none for All. */
export function MeasureIcon({ mode = "all", ...props }) {
  return <ToolModeIcon tool="measure" mode={MEASURE_BADGES[mode] || mode} {...props} />;
}

const glyphIcon = modeGlyphIcon;
// The overlays All picks too, beside the model's geometry: the annotations and measurements,
// drawn over the model, so a click on one is never mistaken for the face under it.
const SELECT_OVERLAYS = Object.freeze(['annotation', 'measurement']);
// Each connected-selection option's glyph.
const GROUP_GLYPHS = Object.freeze({ tangentFaces: 'groupFaces', edgeChain: 'groupEdges' });
/** All, what an engine document's Select picks when a file opens, as a STEP's: Parts too, which a part file offers no mode of its own. */
export const XBF_SELECT_DEFAULT = Object.freeze([...SELECT_GEOMETRY.map(kind => kind.id), 'position', ...SELECT_OVERLAYS]);

/**
 * An engine document's Select modes, a STEP's: All (the default: a face or an edge, else the part,
 * Position's knobs, the annotations and the measurements), then each alone — Parts (in an
 * assembly), Faces, Edges, and Position (where the file has joints: its knobs, the model picks nothing).
 */
export function xbfSelectModes({ assembly, posable }) {
  return [
    { id: 'all', label: 'All', key: 'pick.all', kinds: XBF_SELECT_DEFAULT, icon: <ModeGlyph tool="select" mode="all" className="size-3.5" aria-hidden="true" /> },
    ...SELECT_GEOMETRY.filter(item => assembly || !item.assemblyOnly).map(item => ({ id: item.id, label: item.label, key: item.key, kinds: [item.id], icon: glyphIcon(item.id) })),
    ...(posable ? [{ id: 'position', label: 'Position', key: 'pick.position', kinds: ['position'], icon: lucideIcon(PositionIcon) }] : []),
  ];
}

/**
 * An engine document's Select menu, a STEP's (`kit/tools/select/SelectFilterMenu.jsx`): its two
 * tools (`SELECT_TOOLS`), one chosen, in their own section at the top, since how a pick is made is a
 * choice apart from what it takes; then its modes (`xbfSelectModes`), one chosen; then the connected-selection options that do something under it —
 * Group faces while it picks faces, Group edges while it picks edges. An option that does nothing
 * is not shown, and keeps its choice for when it does.
 *
 * @param {{ value: readonly string[], onChange(filter: readonly string[]): void, assembly: boolean, posable: boolean,
 *   connected: { edgeChain: boolean, tangentFaces: boolean },
 *   onConnectedChange(id: "edgeChain" | "tangentFaces", checked: boolean): void,
 *   tool?: "select" | "box", onToolChange?(tool: "select" | "box"): void, disabled?: boolean }} props
 */
export function SelectModeMenu({ value, onChange, assembly, posable, connected, onConnectedChange, tool = 'select', onToolChange = null, disabled = false }) {
  const options = CONNECTED_SELECTION.filter(option => connectedSelectionApplies(option.id, value));
  const controls = useControlUsage();
  const { t } = useI18n();
  const tools = onToolChange ? <>
    <DropdownMenuLabel className="text-tiny font-normal text-muted-foreground">{t('select.tool')}</DropdownMenuLabel>
    <DropdownMenuRadioGroup value={tool} onValueChange={onToolChange}>
      {SELECT_TOOLS.map(item => <DropdownMenuRadioItem key={item.id} value={item.id} data-select-tool={item.id}>
        <ModeGlyph tool={item.glyph} mode="all" className="size-3.5" aria-hidden="true" />{t(item.key)}
      </DropdownMenuRadioItem>)}
    </DropdownMenuRadioGroup>
  </> : null;
  return <SelectFilterMenu value={value} onChange={onChange} modes={xbfSelectModes({ assembly, posable })} disabled={disabled} header={tools}>
    {options.length ? options.map(option => <DropdownMenuCheckboxItem key={option.id} checked={connected[option.id] === true}
      onSelect={event => event.preventDefault()} onCheckedChange={checked => {
        controls.used(option.id === 'tangentFaces' ? 'select_group_faces' : 'select_group_edges');
        onConnectedChange(option.id, checked === true);
      }}>
      {glyphIcon(GROUP_GLYPHS[option.id])}{t(option.key)}
    </DropdownMenuCheckboxItem>) : null}
  </SelectFilterMenu>;
}
