import { MEASURE_SNAP_LABELS, formatMeasurement, formatMeasurementAngle } from "@text-to-cad/core/lib/viewer/measurement.js";
import { useI18n } from "@text-to-cad/ui/i18n";
import { measureLabelText } from "@text-to-cad/core/lib/viewer/measureDimension.js";
import { CoordValue, InfoRow, MonoValue } from "../../inspector/referenceRows.jsx";

// What the pair's headline reading is called, by its key: what a CAD measure tool calls it.
const HEADLINE = Object.freeze({
  normal: "measure.perpendicular",
  centers: "measure.centreToCentre",
  min: "measure.shortest",
  angle: "measure.angle"
});
// What an end bound to (`MEASURE_SNAP_LABELS`'s kinds), in the view's language.
const snapName = (kind, t) => (MEASURE_SNAP_LABELS[kind] ? t(`measure.snap.${kind}`) : undefined);

/**
 * A measurement's card, its chip's in Measure's row: the full reading — what the two entities make
 * (the perpendicular distance of parallel faces, the centre-to-centre of two holes, the angle of two
 * faces or edges, the shortest distance between the two, or the distance between two points) —
 * with the angle and the shortest distance that go with it, the delta along each axis where
 * the reading is a distance between points, and what each end bound to, so an exact edge or face
 * reading is told from a free point off the surface — and, for a mesh's, that it is approximate: a
 * width across two facets of a curve is no diameter. Rows only, as every chip's card is: the card
 * insets them.
 * @param {{ item: { pickA?: object, pickB?: object, measurement: object } }} props
 */
export default function MeasurementCard({ item }) {
  const { t } = useI18n();
  const measurement = item.measurement;
  const kind = measurement?.kind;
  const angle = formatMeasurementAngle(measurement);
  const delta = measurement?.delta;
  const first = snapName(item.pickA?.snapKind, t);
  const second = snapName(item.pickB?.snapKind, t);
  const pointsApart = kind === undefined || kind === "points" || kind === "distance";
  // An angle's headline is the angle; the distance between the two goes under it.
  const distance = kind === "angle" && measurement?.minDistance !== null && measurement?.minDistance !== undefined ? formatMeasurement(measurement) : "";
  return <>
    <InfoRow label={t(HEADLINE[kind] || "measure.distance")}><MonoValue>{measureLabelText(measurement)}</MonoValue></InfoRow>
    {angle && kind !== "angle" ? <InfoRow label={t("measure.angle")}><MonoValue>{angle}</MonoValue></InfoRow> : null}
    {distance ? <InfoRow label={t("measure.shortest")}><MonoValue>{distance}</MonoValue></InfoRow> : null}
    {pointsApart && Array.isArray(delta) && delta.length >= 3 ? <InfoRow label={t("measure.delta")}><CoordValue vector={delta} /></InfoRow> : null}
    {first && second ? <InfoRow label={t("measure.between")} copy={false}>{`${first} → ${second}`}</InfoRow> : null}
    {measurement?.approximate ? <InfoRow label={t("measure.accuracy")} copy={false}>{t("measure.approximateMesh")}</InfoRow> : null}
  </>;
}
