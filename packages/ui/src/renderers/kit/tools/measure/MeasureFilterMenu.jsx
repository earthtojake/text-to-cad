import SelectFilterMenu from "../select/SelectFilterMenu.jsx";
import { filterBadge } from "../select/selectFilter.js";
import { MEASURE_SNAP_KINDS } from "./measureFilter.js";
import { useI18n } from "@cad/ui/i18n";

// Each kind's badge on Measure's button, Select's own glyphs: a point in a ring for Vertices, the cube with an edge or a face drawn solid.
const GLYPHS = Object.freeze({ vertex: "points", edge: "edges", face: "faces" });
const KIND_IDS = Object.freeze(MEASURE_SNAP_KINDS.map(kind => kind.id));

/** The badge Measure's button wears for `filter` (`selectFilter.js`'s `filterBadge`): none for All, a kind's glyph alone, else the funnel. */
export const measureBadge = filter => filterBadge(filter, KIND_IDS, { glyphs: GLYPHS });

/**
 * Measure's menu: the chevron after its button on the strip, Select's own (`SelectFilterMenu.jsx`)
 * with what Measure picks (`measureFilter.js`): its one row, Filter, ticking Vertices, Edges and Faces.
 * With none ticked a press takes the free point on the model.
 *
 * @param {{ value: readonly string[], onChange(filter: readonly string[]): void, disabled?: boolean }} props
 */
export default function MeasureFilterMenu({ value, onChange, disabled = false }) {
  const { t } = useI18n();
  return <SelectFilterMenu value={value} onChange={onChange} disabled={disabled} name="measure" triggerName={t("measure.filter")}
    kinds={MEASURE_SNAP_KINDS.map(kind => ({ id: kind.id, label: t(kind.key) }))} />;
}
