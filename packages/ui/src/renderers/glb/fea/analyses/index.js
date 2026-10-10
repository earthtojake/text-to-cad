/**
 * The analyses an FEA result can be, by the name its extras give (`extras.analysis.type`; none is
 * static). Each says, for the viewer: its plain `word` and tier, the `noun` its takeaway line uses
 * ("this load", "this shake"), whether it is of the static `family` (its verdict needs a stress
 * field), whether its checks follow the load control (`scalesWithLoad`), the check kinds it judges
 * (`checks`, with any `checkLabels` of its own: shock's stress is "Shock"), What you see's controls
 * when the view names none (`defaultControls(result)`), Study's setup groups (`setupGroups`), its
 * preview routine (`routine(result)`, a descriptor or null), the marker kinds it draws (`markers`)
 * and its Display gate's title (`displayTitle`). Pure: no three.js, no React.
 */
import { FEA_CHECK_KINDS } from "../checkKinds.js";
import bolt from "./bolt.js";
import buckling from "./buckling.js";
import cfd from "./cfd.js";
import cfd_compressible from "./cfd_compressible.js";
import cfd_turbulent from "./cfd_turbulent.js";
import composite from "./composite.js";
import contact from "./contact.js";
import creep from "./creep.js";
import drop from "./drop.js";
import electromagnetic from "./electromagnetic.js";
import fatigue from "./fatigue.js";
import harmonic from "./harmonic.js";
import impact from "./impact.js";
import modal from "./modal.js";
import nonlinear from "./nonlinear.js";
import random_vibration from "./random_vibration.js";
import shock from "./shock.js";
import staticAnalysis from "./static.js";
import { planned } from "./stub.js";
import thermal from "./thermal.js";
import thermal_stress from "./thermal_stress.js";
import thermal_transient from "./thermal_transient.js";
import transient from "./transient.js";

export const ANALYSES = Object.freeze({
  static: staticAnalysis, modal, buckling, thermal, thermal_transient, thermal_stress, harmonic, random_vibration, shock, transient,
  fatigue, drop, cfd, impact, nonlinear, contact, bolt, creep, composite, electromagnetic, cfd_turbulent, cfd_compressible,
});

/** Every analysis this viewer knows, by name. */
export const FEA_ANALYSES = Object.freeze(Object.keys(ANALYSES));

const unknown = new Map();

/**
 * The analysis of this name; static for none. One from a newer cadgen is read as a planned one with
 * the file's word, judging every check kind this viewer knows.
 */
export function analysisNamed(name, word = "") {
  const type = typeof name === "string" && name ? name : "static";
  if (Object.hasOwn(ANALYSES, type)) return ANALYSES[type];
  const key = `${type}\u0000${word}`;
  if (!unknown.has(key)) unknown.set(key, planned({ name: type, word: word || type, checks: FEA_CHECK_KINDS }));
  return unknown.get(key);
}

/** The analysis a result read by `readFeaResult` is. */
export const feaAnalysis = (result) => analysisNamed(result?.analysis?.type, result?.analysis?.word);
