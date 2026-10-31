import SelectFilterMenu from "../select/SelectFilterMenu.jsx";
import { ModeGlyph, modeGlyphIcon } from "../select/modeGlyphs.jsx";
import { MEASURE_SNAP_KINDS } from "./measureFilter.js";
import { useI18n } from "@text-to-cad/ui/i18n";

// Each kind's glyph, Select's own: a point in a ring for Vertices, the cube with an edge or a face drawn solid.
const GLYPHS = Object.freeze({ vertex: "points", edge: "edges", face: "faces" });
/** Measure's modes: All (the vertex near the pointer, else the edge, else the face), then each alone. */
export const MEASURE_MODES = Object.freeze([
  { id: "all", label: "All", key: "pick.all", kinds: MEASURE_SNAP_KINDS.map(kind => kind.id), icon: <ModeGlyph tool="measure" mode="all" className="size-3.5" aria-hidden="true" /> },
  ...MEASURE_SNAP_KINDS.map(kind => ({ id: kind.id, label: kind.label, key: kind.key, kinds: [kind.id], icon: modeGlyphIcon(GLYPHS[kind.id]) })),
]);

/**
 * Measure's menu: the chevron after its button on the strip, Select's own (`SelectFilterMenu.jsx`)
 * with what Measure picks (`measureFilter.js`): All, Vertices, Edges or Faces.
 *
 * @param {{ value: readonly string[], onChange(filter: readonly string[]): void, disabled?: boolean }} props
 */
export default function MeasureFilterMenu({ value, onChange, disabled = false }) {
  const { t } = useI18n();
  return <SelectFilterMenu value={value} onChange={onChange} modes={MEASURE_MODES} disabled={disabled} name="measure" triggerName={t("measure.filter")} />;
}
