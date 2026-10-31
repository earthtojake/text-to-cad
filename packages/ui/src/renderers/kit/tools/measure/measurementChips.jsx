import { useMemo } from "react";
import { Trash2 } from "lucide-react";
import { measureLabelText, measureSeriesColor } from "@text-to-cad/core/lib/viewer/measureDimension.js";
import { ToolbarButton } from "@text-to-cad/ui/primitives/toolbar-button";
import ReferenceChips from "../quick-edit/ReferenceChips.jsx";
import SubToolbar, { SubToolbarSeparator } from "../SubToolbar.jsx";
import MeasurementCard from "./MeasurementCard.jsx";
import { useControlUsage } from "../../../../usage/controls.js";
import { useI18n } from "@text-to-cad/ui/i18n";

/**
 * Measure's results as chips, Quick Edit's own (`ReferenceChips.jsx`), in any view: each its
 * colour's ruler and its reading — a mesh's said to be approximate — its X deleting it, resting on
 * it lighting it, its card the full reading. They are the person's alone: nothing of them goes to
 * the agent. None while nothing is measured.
 *
 * @param {ReturnType<typeof import("./useMeasureSession.js").useMeasureSession>} measure
 */
export function useMeasurementChips(measure) {
  const items = measure.measurements;
  const { onDelete, hover } = measure;
  const { t } = useI18n();
  return useMemo(() => items.map((item, index) => {
    const reading = measureLabelText(item.measurement);
    return { key: `measure-${item.id}`, label: t(item.measurement?.approximate ? "measure.chipApproximate" : "measure.chip", { n: index + 1, reading }), text: reading,
      glyph: "ruler", glyphColor: measureSeriesColor(item.colorIndex),
      card: <MeasurementCard item={item} />,
      onRemove: () => onDelete(item.id), onHover: on => hover(on ? item.id : "") };
  }), [items, onDelete, hover, t]);
}

/**
 * Measure's row under the strip while it is the tool: the measurements taken, as chips, then Clear
 * measurements. No row while nothing is measured.
 *
 * @param {{ measure: ReturnType<typeof import("./useMeasureSession.js").useMeasureSession> }} props
 */
export function MeasurementsBar({ measure }) {
  const chips = useMeasurementChips(measure);
  const controls = useControlUsage();
  const { t } = useI18n();
  if (!chips.length) return null;
  // As narrow as the strip, so it never crowds Quick Edit or the sidebar: the chips take two rows at
  // most, the rest under "+N more", and Clear stays at the end, beside them, never wrapped under.
  return <SubToolbar label={t("measure.measurements")} className="w-max max-w-72 flex-nowrap" data-measurements="">
    <ReferenceChips chips={chips} label={t("measure.measurements")} below rows={2} className="min-w-0 px-0.5" />
    <SubToolbarSeparator />
    <ToolbarButton tooltip={false} label={t("measure.clear")} onClick={() => { controls.used("measure_clear"); measure.clear(); }}>
      <Trash2 className="size-3" strokeWidth={2} aria-hidden="true" />
    </ToolbarButton>
  </SubToolbar>;
}
