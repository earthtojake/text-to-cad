import { MEASURE_SNAP_LABELS, formatMeasurement, formatMeasurementAngle } from "@cad/core/lib/viewer/measurement.js";
import { measureLabelText } from "@cad/core/lib/viewer/measureDimension.js";
import { CoordValue } from "../../inspector/referenceRows.jsx";

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
 * A measurement, as its chip's card reads it (`ItemDetail.jsx`'s facts): the full reading — what the two
 * entities make (the perpendicular distance of parallel faces, the centre-to-centre of two holes, the
 * angle of two faces or edges, the shortest distance between the two, or the distance between two
 * points) — with the angle and the shortest distance that go with it, the delta along each axis where
 * the reading is a distance between points, and what each end bound to, so an exact edge or face
 * reading is told from a free point off the surface — and, for a mesh's, that it is approximate: a
 * width across two facets of a curve is no diameter.
 * @param {{ pickA?: object, pickB?: object, measurement: object }} item
 * @returns {import("../../inspector/inspect.js").DetailFact[]}
 */
export function measurementFacts(item, t) {
  const measurement = item.measurement;
  const kind = measurement?.kind;
  const angle = formatMeasurementAngle(measurement);
  const delta = measurement?.delta;
  const first = snapName(item.pickA?.snapKind, t);
  const second = snapName(item.pickB?.snapKind, t);
  const pointsApart = kind === undefined || kind === "points" || kind === "distance";
  // An angle's headline is the angle; the distance between the two goes under it.
  const distance = kind === "angle" && measurement?.minDistance !== null && measurement?.minDistance !== undefined ? formatMeasurement(measurement) : "";
  return [
    { label: t(HEADLINE[kind] || "measure.distance"), value: measureLabelText(measurement) },
    ...(angle && kind !== "angle" ? [{ label: t("measure.angle"), value: angle }] : []),
    ...(distance ? [{ label: t("measure.shortest"), value: distance }] : []),
    ...(pointsApart && Array.isArray(delta) && delta.length >= 3 ? [{ label: t("measure.delta"), value: <CoordValue vector={delta} /> }] : []),
    ...(first && second ? [{ label: t("measure.between"), value: <>{`${first} → ${second}`}</>, copy: false }] : []),
    ...(measurement?.approximate ? [{ label: t("measure.accuracy"), value: <>{t("measure.approximateMesh")}</>, copy: false }] : [])
  ];
}
