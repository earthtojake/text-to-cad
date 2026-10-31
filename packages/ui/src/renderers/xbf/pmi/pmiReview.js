import { pmiDimensionPlaces } from "@text-to-cad/core/lib/xbf/xbfPmi.js";

// What the PMI section reads out to review a requirement by, all of it the document's: a
// dimension's current limits (its nominal plus each signed deviation, or the limits the code gave
// it; none where the code gave no tolerance), the requirements on the features picked, a frame's
// datums in their order and the tolerances a datum is used by -- each datum looked for on the
// annotation's own part.

const clean = value => Number(value.toPrecision(12));

/**
 * A dimension's limits, at the places its nominal is written at (`pmiDimensionPlaces`), or null
 * where it has no tolerance. Limits given are its limits, nominal or none (`limits`).
 */
export function dimensionLimits(entry) {
  const dimension = entry.dimension;
  const tolerance = dimension?.tolerance;
  if (entry.status !== "ok" || !tolerance || !Number.isFinite(tolerance.lower) || !Number.isFinite(tolerance.upper)) return null;
  const places = pmiDimensionPlaces(dimension);
  if (tolerance.type === "limits") return { lower: tolerance.lower, upper: tolerance.upper, unit: dimension.unit, places };
  if (!Number.isFinite(dimension.nominal)) return null;
  return { lower: clean(dimension.nominal + tolerance.lower), upper: clean(dimension.nominal + tolerance.upper), unit: dimension.unit, places };
}

/** The annotations on any of `ids` (elements picked). */
export function featureRequirements(entries, ids) {
  const picked = new Set(ids);
  return entries.filter(entry => entry.featureIds.some(id => picked.has(id)));
}

/** A frame's datums, primary first, each with the datum of its part that has its letter (null for none). */
export function datumRelationships(entry, entries) {
  return (entry.tolerance?.datums || []).map((letter, index) => ({
    letter, role: ["Primary", "Secondary", "Tertiary"][index],
    entry: entries.find(candidate => candidate.kind === "datum" && candidate.part === entry.part && candidate.datum?.letter === letter) || null,
  }));
}

/** The tolerances of a datum's part that refer to its letter: what it is used by. None for anything but a datum. */
export function datumDependents(entry, entries) {
  if (entry.kind !== "datum") return [];
  return entries.filter(item => item.part === entry.part && item.tolerance?.datums.includes(entry.datum.letter));
}
