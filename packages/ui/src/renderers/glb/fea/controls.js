/**
 * What you see's controls, the same for every result. Each is a generic parameter
 * (`@text-to-cad/core/common/parameters.js`) with `drives`, what it moves.
 */
import { clamp } from "@text-to-cad/core/common/numbers.js";
import { fieldWord } from "./fields.js";
import { english } from "../../../i18n/core.js";

/** Sensible slider bounds for the deformation scale: 0 to four times the file's own. */
export function deformationRange(baseScale) {
  const max = Math.max(1, (Number(baseScale) || 1) * 4);
  const step = max >= 100 ? 1 : max >= 10 ? 0.5 : 0.1;
  return { min: 0, max, step };
}

/** The load slider's bounds, as a multiple of the solved load. */
export const LOAD_RANGE = Object.freeze({ min: 0.1, max: 3, step: 0.1 });

/**
 * What you see's three: a field select with no visible label over every field, opening on the first
 * (stress), a deformation slider from 0 to four times the file's own scale, opening at it, and a load
 * slider from 0.1 to 3 times the solved load, opening at it.
 */
export function feaControls(result, t = english) {
  const range = deformationRange(result.deformationScale);
  return [
    { id: "field", drives: "field", type: "enum", label: t("fea.field"), ariaLabel: t("fea.resultField"), hideLabel: true,
      options: result.fields.map((entry) => ({ value: entry.attribute, label: fieldWord(entry) })), defaultValue: result.fields[0].attribute },
    { id: "deformation", drives: "deformation", type: "number", label: t("fea.deformation"), ariaLabel: t("fea.deformationScale"),
      labelTitle: t("fea.deformationTitle"), min: range.min, max: range.max, step: range.step,
      defaultValue: clamp(result.deformationScale, range.min, range.max), unit: "×" },
    { id: "load_scale", drives: "load_scale", type: "number", label: t("fea.load"), ...LOAD_RANGE, defaultValue: 1, unit: "×" },
  ];
}
