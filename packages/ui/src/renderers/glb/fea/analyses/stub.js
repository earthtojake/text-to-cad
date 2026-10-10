/**
 * An analysis whose viewer file its own track has not filled yet: static's Display gate, the generic
 * controls (`seriesControls`: a mode picker or a scrubber over its series, the field, the deformation
 * where it has one, the sigma level for RMS fields) and every setup group whose entries the study
 * records (`SETUP_GROUPS`), with the facts the spec already fixes (its word, noun, tier, checks,
 * routine and markers). Its track replaces the defaults it needs to.
 */
import { seriesControls } from "../controls.js";
import { SETUP_GROUPS } from "../setup.js";
import staticAnalysis from "./static.js";

/** The routine an analysis plays in preview, as a descriptor GlbRenderer turns into a clip. */
export const routineOf = (label, kind) => Object.freeze({ id: `fea:${kind.replace(/_/g, "-")}`, label, kind });

/** A planned analysis: static's defaults under what `spec` says. */
export function planned(spec) {
  return Object.freeze({
    ...staticAnalysis,
    family: null,
    scalesWithLoad: false,
    routine: () => null,
    defaultControls: seriesControls,
    setupGroups: SETUP_GROUPS,
    // A Tier 3 analysis's short limit word, which leads its verdict's takeaway ("Laminar · ").
    limitWord: "",
    ...spec,
    checks: Object.freeze([...(spec.checks || staticAnalysis.checks)]),
    checkLabels: Object.freeze({ ...(spec.checkLabels || {}) }),
    markers: Object.freeze([...(spec.markers || staticAnalysis.markers)]),
  });
}
