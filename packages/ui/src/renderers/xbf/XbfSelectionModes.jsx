import { SELECT_GEOMETRY } from './xbfSelectionFilter.js';
import SelectFilterMenu from "../kit/tools/select/SelectFilterMenu.jsx";
import { filterBadge } from "../kit/tools/select/selectFilter.js";
import { useI18n } from "@cad/ui/i18n";
import { ModeGlyph, ToolModeIcon } from "../kit/tools/select/modeGlyphs.jsx";

// Select's button, Measure's and Select's menu, which read on an engine document as the STEP
// renderer's did. The glyphs are the kit's (`kit/tools/select/modeGlyphs.jsx`).

/**
 * Select's two tools, how a pick is made: Select, a click picks what is under it and a drag turns the
 * camera; Box select, a drag from empty space draws a box and picks what is visible in it
 * (`@cad/core/lib/viewer/boxSelect.js`: what shows in it, touching it even in part), a drag from the model, its ink or a measurement still turning
 * the camera and a click still picking as Select's do. Select when a file opens.
 */
export const SELECT_TOOLS = Object.freeze([
  { id: 'select', key: 'tool.select', glyph: 'select' },
  { id: 'box', key: 'select.boxSelect', glyph: 'boxSelect' },
]);

/**
 * The Select tool's button icon: the pointer, or Box select's pointer in a square (`tool`), badged
 * with what its filter ticks (`mode`, `xbfSelectBadge`), none for All.
 */
export function SelectIcon({ tool = "select", mode = "all", ...props }) {
  return <ToolModeIcon tool={tool === 'box' ? 'boxSelect' : 'select'} mode={mode} {...props} />;
}

/** The Measure tool's button icon: the ruler, badged with what its filter ticks (`mode`, `MeasureFilterMenu.jsx`'s `measureBadge`), none for All. */
export function MeasureIcon({ mode = "all", ...props }) {
  return <ToolModeIcon tool="measure" mode={mode} {...props} />;
}

// The overlays Select picks beside the model's geometry, each a kind of its own: the annotations and the
// measurements, drawn over the model, so a click on one is never taken for the face under it.
const SELECT_OVERLAYS = Object.freeze([
  { id: 'annotation', label: 'Annotations', key: 'pick.annotations' },
  { id: 'measurement', label: 'Measurements', key: 'pick.measurements' },
]);
/**
 * Every box ticked, what an engine document's Select picks when a file opens, as a STEP's: the
 * geometry (Parts too, which a part file offers no box of its own), Position's knobs, the annotations
 * and the measurements -- and the order the filter is kept in.
 */
export const XBF_SELECT_DEFAULT = Object.freeze(['parts', 'faces', 'edges', 'position', 'annotation', 'measurement']);
// Each kind's glyph, and Position's, where one is drawn (the badge on Select's button).
const GLYPHS = Object.freeze({ parts: 'parts', faces: 'faces', edges: 'edges', position: 'position' });

/**
 * An engine document's Select filter's kinds, a STEP's: Parts (in an assembly), Faces, Edges, Annotations
 * and Measurements, each ticked on its own; and its extra, Position (where the file has joints: its knobs,
 * shown while it is ticked, beside whatever the kinds pick).
 */
export function xbfSelectKinds({ assembly }) {
  return [...SELECT_GEOMETRY.filter(item => assembly || !item.assemblyOnly), ...SELECT_OVERLAYS];
}
export const xbfSelectExtras = ({ posable }) => (posable ? [{ id: 'position', label: 'Position', key: 'pick.position' }] : []);

/** The badge Select's button wears for `filter`: none for every kind, one kind's glyph, Position's alone, else the funnel. */
export function xbfSelectBadge(filter, { assembly, posable }) {
  return filterBadge(filter, xbfSelectKinds({ assembly }).map(kind => kind.id), { glyphs: GLYPHS, alone: posable ? 'position' : null });
}

/**
 * An engine document's Select menu, a STEP's (`kit/tools/select/SelectFilterMenu.jsx`): its "Selection
 * tool" section, its two tools (`SELECT_TOOLS`), one chosen, since how a pick is made is a choice apart
 * from what it takes; then its one row, "Filter", its kinds ticked (`xbfSelectKinds`) and Position after
 * them. A face's or an edge's tangent chain is the view's menu's to take (Select tangent faces, Select
 * tangent edges), never a setting here.
 *
 * @param {{ value: readonly string[], onChange(filter: readonly string[]): void, assembly: boolean, posable: boolean,
 *   tool?: "select" | "box", onToolChange?(tool: "select" | "box"): void, disabled?: boolean }} props
 */
export function SelectMenu({ value, onChange, assembly, posable, tool = 'select', onToolChange = null, disabled = false }) {
  const { t } = useI18n();
  const tools = onToolChange ? {
    value: tool, onChange: onToolChange,
    items: SELECT_TOOLS.map(item => ({ id: item.id, label: t(item.key), icon: <ModeGlyph tool={item.glyph} mode="all" className="size-3.5" aria-hidden="true" /> })),
  } : null;
  const named = items => items.map(item => ({ id: item.id, label: t(item.key) }));
  return <SelectFilterMenu value={value} onChange={onChange} disabled={disabled} tools={tools} order={XBF_SELECT_DEFAULT}
    kinds={named(xbfSelectKinds({ assembly }))} extras={named(xbfSelectExtras({ posable }))} />;
}
