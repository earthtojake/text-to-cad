/**
 * What you see's controls that an analysis offers when the study's view names none
 * (`defaultControls`, ./analyses), and the pieces the view's own controls share with them. Each is
 * a generic parameter (`@text-to-cad/core/common/parameters.js`) with `drives`, what it moves.
 */
import { clamp } from "@text-to-cad/core/common/numbers.js";
import { fieldWord } from "./fields.js";
import { DISPLACEMENT, frameControl, sigmaControl } from "./series.js";

/** Sensible slider bounds for the deformation scale, with no view to say: 0 to four times the file's own. */
export function deformationRange(baseScale) {
  const max = Math.max(1, (Number(baseScale) || 1) * 4);
  const step = max >= 100 ? 1 : max >= 10 ? 0.5 : 0.1;
  return { min: 0, max, step };
}

/** A select's options over these fields, in this order, each that the result carries, in plain words. */
export function fieldOptions(result, attributes) {
  return attributes.map((attribute) => result.fields.find((entry) => entry.attribute === attribute)).filter(Boolean)
    .map((entry) => ({ value: entry.attribute, label: fieldWord(entry) }));
}

/**
 * The viewer's own two: a field select with no visible label over every field, opening on the first
 * (stress), and a deformation slider from 0 to four times the file's own scale, in the one-column
 * look they always had.
 */
export function fieldAndDeformation(result) {
  const every = result.fields.map((entry) => entry.attribute);
  const range = deformationRange(result.deformationScale);
  return [
    { id: "field", drives: "field", type: "enum", label: "Field", ariaLabel: "Result field", hideLabel: true,
      options: fieldOptions(result, every), defaultValue: every[0] },
    { id: "deformation", drives: "deformation", type: "number", label: "Deformation", ariaLabel: "Deformation scale",
      labelTitle: "How much larger than life the displacement is drawn", min: range.min, max: range.max, step: range.step,
      defaultValue: clamp(result.deformationScale, range.min, range.max), unit: "×" },
  ];
}

/** Whether the result carries a vector to deform the model by: the displacement baked in, or a frame's displacement or mode shape. */
export function deforms(result) {
  const geometry = result.mesh?.geometry;
  const vector = (name) => Boolean(name && geometry?.getAttribute(name)?.itemSize === 3);
  return vector(DISPLACEMENT) || Boolean(result.series?.frames.some((frame) => vector(frame.attributes.displacement) || vector(frame.attributes.mode_shape)));
}

/**
 * What you see's controls for an analysis with no view, from what the result carries (spec 6.4): a
 * series of modes opens on the mode picker and the deformation (modal, buckling); a series of times
 * or frequencies on the scrubber, the field and, where it deforms, the deformation (a transient,
 * a harmonic sweep, a load stepped); RMS fields on the field and the sigma level (random vibration);
 * anything else on the field and, where it deforms, the deformation (a temperature has no deformation).
 */
export function seriesControls(result) {
  const [field, deformation] = fieldAndDeformation(result);
  const moves = deforms(result);
  const frames = frameControl(result);
  if (result.series?.kind === "mode" && frames) return moves ? [frames, deformation] : [frames, field];
  const sigma = sigmaControl(result);
  if (sigma) return [field, sigma];
  return [...(frames ? [frames] : []), field, ...(moves ? [deformation] : [])];
}
