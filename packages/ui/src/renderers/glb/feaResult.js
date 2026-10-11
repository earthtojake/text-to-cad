/**
 * An FEA result inside a GLB, as `cadgen fea solve` writes it, and what the
 * viewer can do with it without a second file.
 *
 * The writer (cadgen `_internal/fea/outputs.py`) stores the raw fields as
 * custom vertex attributes beside the baked colour: `_VON_MISES` (float, MPa)
 * and `_DISPLACEMENT` (vec3, glTF units, i.e. metres, unscaled), and puts in
 * the mesh extras a `fields` list describing each one (`attribute`, `name`,
 * `units`, `min`, `max`, `attribute_scale`), `deformation_scale` (the
 * multiplier already baked into the positions), the colour `ramp` it used and
 * the result's `safety_factor` (null when it has none). A result written since
 * the study was recorded also carries the `study` it was solved for (material,
 * fixtures, loads, mesh), `faces` (the occurrence's face refs) and `_FACE`, the
 * index into `faces` of the face each vertex lies on (-1 for none). A bonded
 * assembly also carries `parts` (name, material, peak stress, safety factor of
 * each part), `connections` (each detected pair: type, contact area, gap and the
 * interface faces of both sides), `_PART` (the index into `parts` of the part
 * each vertex belongs to) and the weakest part's name and peak; a single part has
 * none of these. A study that says what the viewer should offer carries its `view`
 * (`feaControls`): the controls of Study's What you see, each shown `when` the checks say, named
 * presets, Study's `sections` and whether the loads and fixtures are drawn. A result since the
 * study picked its checks carries `checks`, each judged (`feaVerdict`); an older one's verdict is
 * its safety factor's, the stress check derived from the fields it has.
 * A result of another analysis than static says which (`analysis`: modal, thermal, ...; none is
 * static), and may carry a `series` (its modes, times or frequencies, each frame's fields in
 * attributes of their own) and the steps cadgen took to fit the run (`fit`). What the viewer does
 * per analysis, per check kind and per field is in `fea/`: `analyses/` (its controls, setup and
 * routine), `checkKinds.js` (each kind's words) and `fields.js` (each field's word).
 * GLTFLoader lower-cases custom attribute names and copies extras into
 * `userData`, which is what is read here.
 *
 * Everything is in-place on the loaded geometry: recolouring rewrites the
 * `color` bytes, re-scaling the deformation rewrites `position` from the
 * file's own positions and displacement vector. The originals are kept on
 * the mesh so any scale or field can be chosen in any order, and a request
 * for what is already shown does nothing.
 */
import { Raycaster } from "three";
import { clamp } from "@text-to-cad/core/common/numbers.js";
import { feaAnalysis } from "./fea/analyses/index.js";
import { CHECK_KINDS, FEA_CHECK_KINDS, checkCaption, checkLabel as kindLabel, checkLine as kindLine, checkTitle, loadCaption } from "./fea/checkKinds.js";
import { deformationRange, fieldOptions } from "./fea/controls.js";
import { flooredFactor, plainNumber, threeFigures } from "./fea/numbers.js";
import { DISPLACEMENT, SIGMA_LEVELS, frameControl, isRms, sigmaControl, snapFrame } from "./fea/series.js";
import { detailRows, faceLabel, facePartIndex, faceSummary, isRoller, loadWords, spaced, wholeRefs } from "./fea/setup.js";

export { FEA_CHECK_KINDS } from "./fea/checkKinds.js";
export { deformationRange } from "./fea/controls.js";
import { fieldInfo } from "./fea/fields.js";
export { FIELD_WORDS } from "./fea/fields.js";
export { faceLabel, faceTitle, forceDirection } from "./fea/setup.js";

const GENERATOR = "cadgen fea";

// The ramp the writer uses when a file carries none: blue -> red.
export const DEFAULT_RAMP = Object.freeze([
  [0.0, [0.05, 0.10, 0.90]],
  [0.25, [0.05, 0.85, 0.95]],
  [0.5, [0.10, 0.85, 0.15]],
  [0.75, [0.98, 0.90, 0.10]],
  [1.0, [0.90, 0.08, 0.05]],
]);

/** RGB in [0, 1] for t in [0, 1], piecewise linear between the ramp stops. */
export function feaRamp(t, stops = DEFAULT_RAMP) {
  const x = clamp(Number(t) || 0, 0, 1);
  for (let i = 1; i < stops.length; i += 1) {
    const [t1, c1] = stops[i];
    if (x <= t1) {
      const [t0, c0] = stops[i - 1];
      const f = t1 === t0 ? 0 : (x - t0) / (t1 - t0);
      if (f >= 1) return [...c1];
      return [c0[0] + (c1[0] - c0[0]) * f, c0[1] + (c1[1] - c0[1]) * f, c0[2] + (c1[2] - c0[2]) * f];
    }
  }
  return [...stops[stops.length - 1][1]];
}

/** The CSS gradient of the ramp, low at the start, for a colour bar. */
export function feaRampGradient(stops = DEFAULT_RAMP, direction = "to right") {
  const parts = stops.map(([t, [r, g, b]]) =>
    `rgb(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)}) ${Math.round(t * 100)}%`);
  return `linear-gradient(${direction}, ${parts.join(", ")})`;
}

/** 256 RGB byte triples of the ramp: one lookup per vertex instead of an interpolation. */
function rampTable(stops) {
  const table = new Uint8Array(256 * 3);
  for (let i = 0; i < 256; i += 1) {
    const [r, g, b] = feaRamp(i / 255, stops);
    table[i * 3] = Math.round(r * 255);
    table[i * 3 + 1] = Math.round(g * 255);
    table[i * 3 + 2] = Math.round(b * 255);
  }
  return table;
}

function rampStops(raw) {
  const valid = Array.isArray(raw) && raw.length >= 2 && raw.every((stop) =>
    Array.isArray(stop) && Number.isFinite(stop[0]) && Array.isArray(stop[1]) && stop[1].length === 3);
  return valid ? raw : DEFAULT_RAMP;
}

const vector = (value) => (Array.isArray(value) && value.length === 3 && value.every(Number.isFinite) ? value.map(Number) : null);

/** The result's findings, kept for the agent (the viewer shows none), in the file's order, each with its position as `index`; malformed ones are left out. */
function readFindings(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((finding) => finding && (typeof finding.summary === "string" || typeof finding.description === "string"))
    .map((finding, index) => ({
      check: String(finding.check || "fea"),
      severity: finding.severity === "error" ? "error" : "warning",
      type: String(finding.type || ""),
      summary: String(finding.summary || ""),
      description: String(finding.description || ""),
      index,
      items: (Array.isArray(finding.items) ? finding.items : []).map((item) => ({
        text: String(item?.text || ""),
        ref: typeof item?.ref === "string" && item.ref ? item.ref : null,
        at: vector(item?.at),
      })),
    }));
}

const text = (value) => (typeof value === "string" ? value : "");
const faceRefs = (raw) => (Array.isArray(raw) ? raw.filter((ref) => typeof ref === "string" && ref) : []);
const finiteOrNull = (value) => (Number.isFinite(value) ? Number(value) : null);

/** An assembly's parts in `_PART` order (a malformed entry keeps its place, empty); [] for a single part. */
function readParts(raw) {
  if (!Array.isArray(raw)) return [];
  return raw.map((part) => ({
    ref: text(part?.ref), name: text(part?.name), material: text(part?.material), yieldMPa: finiteOrNull(part?.yield_MPa),
    peakMPa: finiteOrNull(part?.peak_MPa), safetyFactor: finiteOrNull(part?.safety_factor), maxDisplacementMm: finiteOrNull(part?.max_displacement_mm),
  }));
}

/** An assembly's detected pairs: `between` the two part refs, `names` theirs, the interface `faces` of both sides (none for a free pair). */
function readConnections(raw) {
  if (!Array.isArray(raw)) return [];
  return raw.filter((joint) => joint && Array.isArray(joint.between) && joint.between.length === 2).map((joint) => ({
    between: joint.between.map(text),
    names: [0, 1].map((side) => text(joint.names?.[side]) || text(joint.between[side])),
    type: text(joint.type) || "free",
    areaMm2: finiteOrNull(joint.area_mm2),
    gapMm: finiteOrNull(joint.gap_mm),
    faces: faceRefs(joint.faces),
  }));
}

/**
 * The study's `view`, as the file carries it: `controls` (null when it names none), `presets` and
 * `show`. null for a result with no view: the viewer's own defaults. Each control is checked where
 * it is used (`feaControls`), so one this viewer does not know is skipped rather than refused.
 */
function readView(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  return {
    sections: Array.isArray(raw.sections) ? raw.sections.filter((name) => typeof name === "string") : null,
    controls: Array.isArray(raw.controls) ? raw.controls.filter((control) => control && typeof control === "object") : null,
    presets: Array.isArray(raw.presets) ? raw.presets.filter((preset) => preset && typeof preset.label === "string" && preset.label.trim()) : [],
    show: raw.show && typeof raw.show === "object" ? raw.show : {},
  };
}

/** Where in a result's series a check's value occurs (`at`: its frame, and the frame's value and unit); null for none. */
function readAt(raw) {
  if (!raw || typeof raw !== "object" || !Number.isInteger(raw.frame) || raw.frame < 0) return null;
  return { frame: raw.frame, value: finiteOrNull(raw.value), unit: text(raw.unit) };
}

/** A frequency band's ends, low first; null for anything else. */
const band = (raw) => (Array.isArray(raw) && raw.length === 2 && raw.every(Number.isFinite) && raw[0] < raw[1] ? raw.map(Number) : null);

/**
 * The checks the file judged (`kind`, `label`, `value`, `limit`, `unit`, `ratio`, `closeAt`, `status`, `where`,
 * and where its kind's line needs them `at`, `mode`, `band`, `need`, `life`, `reference`), in the study's
 * order, those of a kind its analysis does not judge (`kinds`) or this viewer does not know, or with
 * numbers it cannot use, left out; null for a result written before checks were.
 */
function readChecks(raw, kinds) {
  if (!Array.isArray(raw)) return null;
  return raw.filter((check) => check && kinds.includes(check.kind) && FEA_CHECK_KINDS.includes(check.kind) && Number.isFinite(check.value)
    && Number.isFinite(check.limit) && (check.limit > 0 || CHECK_KINDS[check.kind].signedLimit === true) && Number.isFinite(check.ratio))
    .map((check) => ({
      kind: check.kind, label: text(check.label), value: Number(check.value), limit: Number(check.limit), unit: text(check.unit),
      ratio: Number(check.ratio), closeAt: Number.isFinite(check.close_at) ? Number(check.close_at) : 1,
      margin: Number.isFinite(check.margin) && check.margin >= 1 ? Number(check.margin) : null,
      status: ["fails", "close", "passes"].includes(check.status) ? check.status : null, part: text(check.part),
      faces: faceRefs(check.faces), where: text(check.where?.ref),
      ...(readAt(check.at) ? { at: readAt(check.at) } : {}),
      ...(Number.isInteger(check.mode) && check.mode >= 1 ? { mode: check.mode } : {}),
      ...(band(check.avoid_Hz) ? { band: band(check.avoid_Hz) } : {}),
      ...(Number.isFinite(check.need) && check.need > 0 ? { need: Number(check.need) } : {}),
      ...(Number.isFinite(check.life) && check.life > 0 ? { life: Number(check.life) } : {}),
      ...(Number.isFinite(check.reference) ? { reference: Number(check.reference) } : {}),
      // A laminate's worst ply (ply_failure): its number from the bottom face and its angle.
      ...(Number.isInteger(check.ply) && check.ply >= 1 ? { ply: check.ply, angle: finiteOrNull(check.angle_deg) ?? 0 } : {}),
      // Where along a crack's front its K is largest (fracture): "the deepest point", "the surface".
      ...(typeof check.point === "string" && check.point ? { point: check.point } : {}),
      // A fill level judged against the tank's own brim (multiphase, no limit_mm given): its line says so.
      ...(check.brim === true ? { brim: true } : {}),
      // A check that grows with the square of what drives it (a magnetic force's stress, with the current).
      ...(check.scaling === "quadratic" ? { scaling: "quadratic" } : {}),
      // A check of an analysis not linear in the load (nonlinear, contact, bolt, composite): judged as solved only.
      ...(check.scaling === "none" ? { scaling: "none" } : {}),
      // A field's peak out in the air (electrostatic, no faces named), above what the colours on the parts show.
      ...(check.where?.in === "air" ? { inAir: { near: text(check.where.near) } } : {}),
    }));
}

/**
 * What analysis the result is (`extras.analysis`; none is static): its `type`, `tier`, plain `word`,
 * whether it is an `estimate`, the `noun` its takeaway uses, its stated `limits` and `warnings`, and
 * the reference temperature its temperature checks are measured from (`referenceC`). The file's
 * words win over the registry's.
 */
function readAnalysis(raw) {
  const own = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
  const known = feaAnalysis({ analysis: { type: text(own.type), word: text(own.word) } });
  const sentences = (list) => (Array.isArray(list) ? list.filter((line) => typeof line === "string" && line) : []);
  return {
    type: known.name, tier: [1, 2, 3].includes(own.tier) ? own.tier : known.tier, word: text(own.word) || known.word,
    estimate: typeof own.estimate === "boolean" ? own.estimate : known.estimate, noun: text(own.noun) || known.noun,
    limits: sentences(own.limits), warnings: sentences(own.warnings), referenceC: finiteOrNull(own.reference_C),
    ...(readReynolds(own.reynolds) ? { reynolds: readReynolds(own.reynolds) } : {}),
    // A flow that carries heat says which model it solved: "laminar" or "turbulent".
    ...(own.regime === "laminar" || own.regime === "turbulent" ? { regime: own.regime } : {}),
    ...(readMach(own.mach) ? { mach: readMach(own.mach) } : {}),
    ...(readUnsettled(own.unsettled) ? { unsettled: readUnsettled(own.unsettled) } : {}),
  };
}

/**
 * Where a contact solve's forces did not settle (`analysis.unsettled`: `at_percent`, the load steps
 * in % of the load, and `first_percent`): `{ atPercent, firstPercent }`. null for none.
 */
function readUnsettled(raw) {
  if (!raw || typeof raw !== "object") return null;
  const atPercent = (Array.isArray(raw.at_percent) ? raw.at_percent : []).filter(Number.isFinite).map(Number);
  const firstPercent = Number.isFinite(raw.first_percent) ? Number(raw.first_percent) : atPercent.length ? Math.min(...atPercent) : null;
  return firstPercent === null ? null : { atPercent, firstPercent };
}

/**
 * A fast gas flow's highest Mach number as the file states it (`analysis.mach`: value, limit, regime,
 * checked): `checked` false where the file warns (past the Mach the solver is checked to, or a
 * supersonic outlet); a file that does not say is judged by its value against its limit. null for none.
 */
function readMach(raw) {
  if (!raw || typeof raw !== "object" || !Number.isFinite(raw.value)) return null;
  const limit = Number.isFinite(raw.limit) && raw.limit > 0 ? Number(raw.limit) : null;
  const regime = ["subsonic", "transonic", "supersonic"].includes(raw.regime) ? raw.regime : "";
  const checked = typeof raw.checked === "boolean" ? raw.checked : limit === null || raw.value <= limit;
  return { value: Number(raw.value), limit, regime, checked };
}

/** A flow's Reynolds number as the file states it (`analysis.reynolds`: value, limit, kind); null for none. */
function readReynolds(raw) {
  if (!raw || typeof raw !== "object" || !Number.isFinite(raw.value)) return null;
  const kind = raw.kind === "external" ? "external" : "internal";
  return { value: Number(raw.value), limit: Number.isFinite(raw.limit) ? Number(raw.limit) : kind === "external" ? 1000 : 2000, kind };
}

/**
 * The result's series (`extras.series`): its `kind` (mode, time or frequency), `unit`, the frame it
 * opens on (`default`) and its `frames`, each a `value`, a `label` and the attribute that holds each
 * field at that frame (`attributes`, lower-cased as the geometry names them). null for a result with none.
 */
function readSeries(raw) {
  if (!raw || typeof raw !== "object" || !Array.isArray(raw.frames)) return null;
  const frames = raw.frames.filter((frame) => frame && Number.isFinite(frame.value)).map((frame) => ({
    value: Number(frame.value), label: text(frame.label),
    attributes: Object.fromEntries(Object.entries(frame.attributes && typeof frame.attributes === "object" ? frame.attributes : {})
      .filter(([, attribute]) => typeof attribute === "string" && attribute).map(([name, attribute]) => [name, attribute.toLowerCase()])),
  }));
  if (!frames.length) return null;
  const opening = Number.isInteger(raw.default) && raw.default >= 0 && raw.default < frames.length ? raw.default : 0;
  return { kind: ["mode", "time", "frequency"].includes(raw.kind) ? raw.kind : "time", unit: text(raw.unit), default: opening, frames };
}

/**
 * The steps cadgen took to fit the run to the machine (`extras.fit`), in order: each its `rung`, its
 * `words`, its `accuracy` note and `accuracyPct` where it can say, the `faces` it is about and its
 * `detail`. [] when it took none.
 */
function readFit(raw) {
  if (!Array.isArray(raw)) return [];
  return raw.filter((step) => step && typeof step.words === "string" && step.words).map((step) => ({
    rung: text(step.rung), words: step.words, accuracy: text(step.accuracy), accuracyPct: finiteOrNull(step.accuracy_pct),
    faces: faceRefs(step.faces), detail: text(step.detail),
  }));
}

const entries = (raw) => (Array.isArray(raw) ? raw.filter((entry) => entry && typeof entry === "object") : []);
const record = (raw) => (raw && typeof raw === "object" && !Array.isArray(raw) ? raw : null);

/**
 * A load's or a shake's `history` over time as the file echoes it, kept in its own form (a table of
 * [t_s, factor] rows, or `{shape, duration_s}`), for the words that say it; null for none.
 */
function readHistory(raw) {
  if (Array.isArray(raw)) {
    const rows = raw.filter((row) => Array.isArray(row) && row.length === 2 && row.every(Number.isFinite)).map((row) => row.map(Number));
    return rows.length ? rows : null;
  }
  const own = record(raw);
  if (!own || typeof own.shape !== "string") return null;
  return { shape: own.shape, ...(Number.isFinite(own.duration_s) ? { duration_s: Number(own.duration_s) } : {}) };
}

/** A spectrum table's rows, [Hz, value] with both positive: a PSD's g²/Hz or a shock's g. [] for none. */
const spectrumTable = (raw) => (Array.isArray(raw)
  ? raw.filter((row) => Array.isArray(row) && row.length === 2 && row.every((value) => Number.isFinite(value) && value > 0)).map((row) => row.map(Number))
  : []);

/** A random vibration's PSD, from the study's echo: its `table` (Hz, g²/Hz), its `grms` as the file states it (null where it does not) and its `direction`. null for none. */
function readPsd(raw) {
  const psd = record(raw);
  if (!psd) return null;
  return { table: spectrumTable(psd.table), grms: Number.isFinite(psd.grms) && psd.grms > 0 ? Number(psd.grms) : null, direction: vector(psd.direction) };
}

/** A shock's spectrum, from the study's echo: its `table` (Hz, g), its `direction` and the `dampingRatio` it is quoted at. null for none. */
function readSrs(raw) {
  const srs = record(raw);
  if (!srs) return null;
  return { table: spectrumTable(srs.table), direction: vector(srs.direction), dampingRatio: finiteOrNull(srs.damping_ratio) };
}

/**
 * What shakes the part, from the study's echo: a base `excitation` (`kind` "base", or "force" for
 * one through its loads), else a random-vibration `psd` or a shock `srs`, each along its
 * `direction`, with an `amplitudeG` where it has one and the `history` a shake over time follows
 * (null for none). null for none.
 */
function readExcitation(raw) {
  const own = record(raw.excitation);
  if (own) {
    return { kind: own.type === "force" ? "force" : "base", direction: vector(own.direction), amplitudeG: finiteOrNull(own.amplitude_g),
      history: readHistory(own.history) };
  }
  for (const kind of ["psd", "srs"]) {
    const spectrum = record(raw[kind]);
    if (spectrum) return { kind, direction: vector(spectrum.direction), amplitudeG: null };
  }
  return null;
}

/**
 * A flow's openings, from the study's echo: its inlets (`speed` m/s, or an external flow's `velocity`) and outlets (`pressure` Pa).
 * A flow that carries heat adds each inlet's `temperatureC` (an external free stream's), its `fluid`'s name and its `regime`. null for none.
 */
function readFlow(raw) {
  const flow = record(raw);
  if (!flow) return null;
  const external = vector(flow.velocity_m_s);
  const fluid = record(flow.fluid);
  return {
    kind: flow.kind === "external" ? "external" : "internal",
    inlets: external ? [{ opening: "", speed: Math.hypot(...external), velocity: external, temperatureC: finiteOrNull(flow.temperature_C) }]
      : entries(flow.inlets).map((inlet) => ({ opening: text(inlet.opening), speed: finiteOrNull(inlet.velocity_m_s), velocity: null,
        temperatureC: finiteOrNull(inlet.temperature_C) })),
    outlets: entries(flow.outlets).map((outlet) => ({ opening: text(outlet.opening), pressure: finiteOrNull(outlet.pressure_Pa) })),
    fluid: typeof flow.fluid === "string" ? flow.fluid : fluid ? text(fluid.name) : "",
    regime: text(flow.regime),
  };
}

/** A drop, from the study's echo: its `heightMm`, the faces that land (`onto`), how it stops, its `direction`, its `floor` and an impact's `friction`. null for none. */
function readDrop(raw) {
  const drop = record(raw);
  if (!drop) return null;
  return { heightMm: finiteOrNull(drop.height_mm), onto: faceRefs(drop.onto), stopMm: finiteOrNull(drop.stop_mm), impactMs: finiteOrNull(drop.impact_ms),
    direction: vector(drop.direction), floor: text(drop.floor), friction: finiteOrNull(drop.friction) };
}

/** An electromagnetic study's voltages or currents put on faces: each its `faces`, its `value` (V or A) and its `name`. */
const electrodes = (raw, unit) => entries(raw).map((entry) => ({ faces: faceRefs(entry.faces), value: finiteOrNull(entry[unit]), name: text(entry.name) }));

/** An electromagnetic study's coils: the `part` each is wound on, its `turns`, its current (`amps`), its `name` and its `axis` (direction, point). */
function readCoils(raw) {
  return entries(raw).map((coil) => ({
    part: text(coil.part), turns: finiteOrNull(coil.turns), amps: finiteOrNull(coil.A), name: text(coil.name),
    axis: { direction: vector(coil.axis?.direction), point: vector(coil.axis?.point_mm) },
  }));
}

/** An AC study's uniform field the air carries (`applied_field`): its `mT` and `direction`. null for none. */
function readAppliedField(raw) {
  const field = record(raw);
  return field ? { mT: finiteOrNull(field.mT), direction: vector(field.direction) } : null;
}

/** Where an electromagnetic study's Joule heat goes (`electro_thermal`): its fixed `temperatures` and its `convection`, as a thermal study's. null for none. */
function readHeatOut(raw) {
  const block = record(raw);
  if (!block) return null;
  return {
    temperatures: entries(block.temperatures).map((entry) => ({ faces: faceRefs(entry.faces), celsius: finiteOrNull(entry.C) })),
    convection: entries(block.convection).map((entry) => ({ faces: faceRefs(entry.faces), h: finiteOrNull(entry.h_W_m2K), ambientC: finiteOrNull(entry.ambient_C) })),
  };
}

/**
 * A composite's layup, from the study's echo (`layup`): its `plies` bottom first (each its `material`,
 * `angle_deg` and `thickness_mm`, as the file says them), its `notation` ("" where it gives none), its
 * `thicknessMm` and the 0° `axis` and `normal` where it says. null for none.
 */
function readLayupEcho(raw) {
  const layup = record(raw);
  if (!layup) return null;
  const plies = entries(layup.plies).filter((ply) => Number.isFinite(ply.thickness_mm))
    .map((ply) => ({ material: text(ply.material), angle_deg: Number.isFinite(ply.angle_deg) ? Number(ply.angle_deg) : 0, thickness_mm: Number(ply.thickness_mm) }));
  return { plies, notation: text(layup.notation), thicknessMm: finiteOrNull(layup.thickness_mm), axis: vector(layup.axis), normal: vector(layup.normal) };
}

/**
 * An acoustic study's echo: what it solved (`solve`, `domain`), its `fluid`, its `sources` (a speaker
 * face's `faces` and `velocityMmS`, or a `point` and its `volumeVelocity`), its `absorbers` (`faces`,
 * `absorption` or `impedanceRayl`), its `open` faces (one list per entry), its `probes` (`label`, `at`),
 * its sweep and loss, and `from` ("harmonic" when the part's vibration drives it). null for none.
 */
function readAcoustic(raw) {
  const block = record(raw);
  if (!block) return null;
  const fluid = record(block.fluid);
  return {
    solve: text(block.solve), domain: text(block.domain),
    fluid: fluid ? { name: text(fluid.name), densityKgM3: finiteOrNull(fluid.density_kg_m3), speedMS: finiteOrNull(fluid.speed_m_s) } : null,
    sources: entries(block.sources).map((source) => ({
      faces: faceRefs(source.faces), velocityMmS: finiteOrNull(source.velocity_mm_s), point: vector(source.point_mm),
      volumeVelocity: finiteOrNull(source.volume_velocity_m3_s),
    })),
    absorbers: entries(block.absorbers).map((entry) => ({
      faces: faceRefs(entry.faces), absorption: finiteOrNull(entry.absorption), impedanceRayl: finiteOrNull(entry.impedance_rayl),
    })),
    open: entries(block.open).map((entry) => faceRefs(entry.faces)),
    probes: entries(block.probes).map((probe) => ({ label: text(probe.label), at: vector(probe.at_mm) || [0, 0, 0] })),
    sweepHz: band(block.sweep_Hz), lossFactor: finiteOrNull(block.loss_factor), from: text(block.from),
  };
}

/**
 * A piezo study's echo: what it solved (`solve`: static, resonance or harmonic), its `electrodes` (each its
 * `faces`, `name`, `volts` held, or `open`) and each piezo part's `poling` (`part`, `material`, `direction`).
 * null for a study with no electrodes.
 */
function readPiezo(raw) {
  if (!Array.isArray(raw.electrodes)) return null;
  return {
    solve: text(raw.solve) || "static",
    electrodes: entries(raw.electrodes).map((entry) => ({
      faces: faceRefs(entry.faces), name: text(entry.name), volts: finiteOrNull(entry.V), open: entry.open === true,
    })),
    poling: entries(raw.poling).map((entry) => ({ part: text(entry.part), material: text(entry.material), direction: vector(entry.direction) }))
      .filter((entry) => entry.direction),
  };
}

/** A composite's ply materials by name (`laminae`), each its numeric properties as the file gives them. {} for none. */
function readLaminae(raw) {
  const named = record(raw);
  if (!named) return {};
  return Object.fromEntries(Object.entries(named).filter(([, lamina]) => record(lamina))
    .map(([name, lamina]) => [name, Object.fromEntries(Object.entries(lamina).filter(([, value]) => Number.isFinite(value)))]));
}

/**
 * The study the result was solved for, as the file records it; null for a result written before it
 * did. Beside the material, fixtures, loads (a body load, gravity or an acceleration, has no faces
 * and its `g` vector), mesh and margin, what another analysis echoes: fixed `temperatures`, `heat`
 * inputs, `convection`, the `excitation`, the `drop`, the `flow`, the `rigidPlanes`, the
 * `sigma` a random vibration judges at and its `psd` (table and g rms), a shock's `srs` and how its
 * modes were `combination`ed, a sweep's `sweepHz` and the `dampingRatio`. A load over time keeps its
 * `history`, as the excitation does. An electromagnetic study's `mode`, `frequencyHz`, `voltages`,
 * `currents`, `coils`, `appliedField` and `heatOut`; a composite's `layup` and `laminae`; an acoustic
 * study's block, a piezo's electrodes, a bolted joint's `bolts`, a contact study's `contactPairs`, a
 * fracture's `crack`, a multiphase's block and a rotor's spin, bearings, discs and unbalances. A fixture's
 * `type` is "fixed" (none given) or "roller" (it may slide in the face's plane, not off it). Every
 * analysis reads its study from here, never the raw echo.
 */
function readStudy(raw) {
  if (!raw || typeof raw !== "object") return null;
  const material = raw.material && typeof raw.material === "object"
    ? { name: text(raw.material.name), yieldMPa: finiteOrNull(raw.material.yield_MPa) } : null;
  const mesh = raw.mesh && typeof raw.mesh === "object"
    ? { sizeMm: finiteOrNull(raw.mesh.size_mm), refinedFromMm: finiteOrNull(raw.mesh.refined_from_mm) } : null;
  return {
    material,
    fixtures: (Array.isArray(raw.fixtures) ? raw.fixtures : []).filter(Boolean)
      .map((fixture) => ({ type: text(fixture.type) || "fixed", faces: faceRefs(fixture.faces) })),
    loads: (Array.isArray(raw.loads) ? raw.loads : []).filter(Boolean).map((load) => ({
      type: text(load.type), faces: faceRefs(load.faces), vector: vector(load.vector_N), pressure: finiteOrNull(load.pressure_MPa),
      ...(vector(load.vector_g) ? { g: vector(load.vector_g) } : {}),
      ...(readHistory(load.history) ? { history: readHistory(load.history) } : {}),
    })),
    mesh,
    margin: Number.isFinite(raw.margin) && raw.margin >= 1 ? Number(raw.margin) : null,
    temperatures: entries(raw.temperatures).map((entry) => ({ faces: faceRefs(entry.faces), celsius: finiteOrNull(entry.C) })),
    heat: entries(raw.heat).map((entry) => ({ faces: faceRefs(entry.faces), watts: finiteOrNull(entry.W), fluxWm2: finiteOrNull(entry.W_per_m2) })),
    convection: entries(raw.convection).map((entry) => ({ faces: faceRefs(entry.faces), h: finiteOrNull(entry.h_W_m2K), ambientC: finiteOrNull(entry.ambient_C) })),
    // Faces radiating to their surroundings (and, `surfaceToSurface`, to each other): a thermal study's.
    radiation: entries(raw.radiation).map((entry) => ({ faces: faceRefs(entry.faces), emissivity: finiteOrNull(entry.emissivity),
      ambientC: finiteOrNull(entry.ambient_C), surfaceToSurface: entry.surface_to_surface === true })),
    excitation: readExcitation(raw),
    drop: readDrop(raw.drop),
    flow: readFlow(raw.flow),
    rigidPlanes: entries(raw.rigid_planes).map((plane) => ({ point: vector(plane.point_mm) || [0, 0, 0], normal: vector(plane.normal) }))
      .filter((plane) => plane.normal && Math.hypot(...plane.normal) > 0),
    sigma: raw.sigma === 1 || raw.sigma === 3 ? raw.sigma : null,
    psd: readPsd(raw.psd),
    srs: readSrs(raw.srs),
    combination: raw.combination === "cqc" || raw.combination === "srss" ? raw.combination : "",
    sweepHz: band(raw.sweep_Hz),
    dampingRatio: finiteOrNull(raw.damping_ratio),
    // Electromagnetic: what it solved (`mode`, an AC study's `frequencyHz`), its voltages and currents on faces, its coils, an AC
    // field the air carries, and where its Joule heat goes.
    mode: text(raw.mode),
    frequencyHz: finiteOrNull(raw.frequency_Hz),
    voltages: electrodes(raw.voltages, "V"),
    currents: electrodes(raw.currents, "A"),
    coils: readCoils(raw.coils),
    appliedField: readAppliedField(raw.applied_field),
    heatOut: readHeatOut(raw.electro_thermal),
    // Composite: the layup and the ply materials.
    layup: readLayupEcho(raw.layup),
    laminae: readLaminae(raw.laminae),
    // Acoustic: where the air is, what makes and soaks up the sound, where it is listened to (null for none).
    acoustic: readAcoustic(raw.acoustic),
    // Topology: the share of the material to keep, and the faces whose nearby material stays solid.
    volumeFraction: finiteOrNull(raw.volume_fraction),
    keptSolid: faceRefs(raw.kept_solid),
    // Piezo: what it solved, its electrodes (held at a voltage, or open) and each part's poling. null for none.
    piezo: readPiezo(raw),
    // Bolted joint and contact: the bolts and contact pairs as the study gives them (their analyses word them).
    bolts: entries(raw.bolts),
    contactPairs: entries(raw.contact_pairs),
    // Fracture: the crack the study cuts in (`kind`, `face`, `size_mm`, `length_mm`). null for none.
    crack: record(raw.crack),
    // Two fluids: the multiphase block (the liquid, the shake, the openings). null for none.
    multiphase: record(raw.multiphase),
    // Spinning: the spin (`axis`, `rpm`), the bearings, discs and unbalances as the study gives them. null for no spin.
    rotor: record(raw.spin) ? { spin: raw.spin, bearings: entries(raw.bearings), discs: entries(raw.discs), unbalance: entries(raw.unbalance) } : null,
  };
}

/**
 * The absolute path of the STEP a result was solved from. The file records its name (`document`),
 * which is the GLB's own folder's; an absolute one is kept. "" when it names nothing.
 */
export function resultSourcePath(glbPath, document) {
  const named = String(document || "").trim();
  if (!named) return "";
  const absolute = /^(?:[A-Za-z]:)?[\\/]/.test(named);
  const parts = absolute ? named.split("/") : [...String(glbPath || "").split("/").slice(0, -1), ...named.split("/")];
  const out = [];
  for (const part of parts) {
    if (part === "..") out.pop();
    else if (part !== ".") out.push(part);
  }
  return out.join("/");
}

/** A finding's `ref` as a selector in the prompt grammar: the token's leading "#" is not part of it. */
export const findingSelector = (ref) => String(ref).replace(/^#/, "");

/**
 * The FEA result a loaded glTF scene root carries, or null for any other GLB.
 */
export function readFeaResult(root) {
  if (!root?.traverse) {
    return null;
  }
  let found = null;
  root.traverse((object) => {
    if (found || !object?.isMesh || !object.geometry) {
      return;
    }
    const extras = object.userData || {};
    if (extras.generator !== GENERATOR || !Array.isArray(extras.fields)) {
      return;
    }
    const fields = extras.fields
      .filter((field) => typeof field?.attribute === "string" && object.geometry.getAttribute(field.attribute.toLowerCase()))
      .map((field) => ({
        attribute: field.attribute.toLowerCase(),
        name: String(field.name || field.attribute),
        units: String(field.units || ""),
        min: Number(field.min) || 0,
        max: Number(field.max) || 0,
        attributeScale: Number(field.attribute_scale) || 1,
        ...(typeof field.field === "string" && field.field ? { view: field.field } : {}),
        ...(field.signed === true ? { signed: true } : {}),
        ...(field.per_frame === true ? { perFrame: true } : {}),
        // Colours stopped below the field's peak (a singular edge's spike): where, and the peak itself.
        ...(Number.isFinite(field.capped?.peak) && Number.isFinite(field.capped?.quantile)
          ? { capped: { quantile: Number(field.capped.quantile), peak: Number(field.capped.peak) } } : {}),
      }));
    if (fields.length === 0) {
      return;
    }
    const analysis = readAnalysis(extras.analysis);
    found = {
      analysis,
      mesh: object,
      name: String(extras.name || ""),
      document: String(extras.document || ""),
      occurrence: String(extras.occurrence || ""),
      deformationScale: Number(extras.deformation_scale) || 1,
      safetyFactor: Number.isFinite(extras.safety_factor) ? extras.safety_factor : null,
      fields,
      ramp: rampStops(extras.ramp),
      findings: readFindings(extras.findings),
      study: readStudy(extras.study),
      faces: faceRefs(extras.faces),
      parts: readParts(extras.parts),
      connections: readConnections(extras.connections),
      weakestPart: text(extras.weakest_part),
      weakestPartPeakMPa: finiteOrNull(extras.weakest_part_peak_MPa),
      maxDisplacementMm: finiteOrNull(extras.max_displacement_mm),
      view: readView(extras.view),
      checks: readChecks(extras.checks, feaAnalysis({ analysis }).checks),
      series: readSeries(extras.series),
      fit: readFit(extras.fit),
      // A nonlinear run that collapsed: the last load it carried, in % of the load (`load_percent`).
      collapsed: extras.collapsed === true,
      loadPercent: finiteOrNull(extras.load_percent),
    };
  });
  return found;
}

/** The file's own positions, each field's values once read, and what is currently shown, kept on the mesh. */
function shown(mesh) {
  let kept = mesh.userData.__fea;
  if (!kept) {
    kept = { position: Float32Array.from(mesh.geometry.getAttribute("position").array), values: {}, field: null, scale: null };
    mesh.userData.__fea = kept;
  }
  return kept;
}

/** The positions the file wrote (its own deformation scale baked in), whatever is drawn now. */
export const filePositions = (mesh) => shown(mesh).position;

/** A field's values, read from the geometry once: a ramp playing recolours every frame. */
function keptValues(mesh, field) {
  const kept = shown(mesh);
  if (!kept.values[field.attribute]) kept.values[field.attribute] = fieldValues(mesh, field);
  return kept.values[field.attribute];
}

/** The scalar value per vertex of a field: the attribute itself, or a vector's magnitude, in the field's units. */
export function fieldValues(mesh, field) {
  const attribute = mesh.geometry.getAttribute(field.attribute);
  if (!attribute) {
    return null;
  }
  const { count, itemSize: size, array } = attribute;
  const out = new Float32Array(count);
  const scale = field.attributeScale || 1;
  for (let i = 0; i < count; i += 1) {
    if (size === 1) {
      out[i] = array[i] * scale;
    } else {
      let sum = 0;
      for (let k = 0; k < size; k += 1) {
        const v = array[i * size + k];
        sum += v * v;
      }
      out[i] = Math.sqrt(sum) * scale;
    }
  }
  return out;
}

// What a chosen face is tinted toward: no colour of the ramp, two thirds of the way, so a chosen face
// reads at the ramp's blue end and its red end alike while its stress still shows through.
const HIGHLIGHT = Object.freeze([255, 64, 242]);
const HIGHLIGHT_BLEND = 0.68;
// A chosen joint also tints the two parts it joins, lightly: the interface faces sit hidden between them.
const SOFT_BLEND = 0.3;
// What a vertex under a threshold is drawn: a neutral grey, no colour of the ramp.
const BELOW_THRESHOLD = Object.freeze([150, 150, 150]);

/** The face each vertex lies on (`_FACE`), or null for a result that does not say. */
function vertexFaces(mesh) {
  const attribute = mesh.geometry.getAttribute("_face");
  return attribute?.itemSize === 1 ? attribute.array : null;
}

/** The part each vertex belongs to (`_PART`), or null for a single part's result. */
function vertexParts(mesh) {
  const attribute = mesh.geometry.getAttribute("_part");
  return attribute?.itemSize === 1 ? attribute.array : null;
}

/**
 * Rewrite the mesh's vertex colours from one field over `[field.min, field.max]`, with the
 * vertices of the faces in `highlight` (indices into the result's `faces`) and of the parts in
 * `parts` (indices into its `parts`) tinted, and the parts in `softParts` tinted lightly (a joint's
 * two parts; its interface faces keep the full tint).
 * A field whose worst is its lowest (`lowWorst` in `fea/fields.js`: a life, a fatigue margin) is drawn
 * down the ramp, its lowest red. `scaling`, for a load other than the solved one: the values are drawn at `valueScale` times
 * their own and the ramp spans `rangeScale` times the field's range (both the load scale; while a
 * load ramp plays the values climb toward the range). `threshold`: `{ field, value, scale }`, every
 * vertex whose value of that field (times `scale`) is under `value` drawn grey. `blend`: `{ field,
 * weight }`, a series playing between two frames, the values that far toward the other frame's
 * (`field` the same field at that frame).
 * Returns true when the colours changed; false when that field and tint were already shown.
 */
export function recolorByField(mesh, field, ramp = DEFAULT_RAMP, highlight = null, parts = null, softParts = null,
  { valueScale = 1, rangeScale = 1, threshold = null, blend = null } = {}) {
  const color = mesh.geometry.getAttribute("color");
  // The attribute's presence, not its values: a ramp playing recolours every frame, and keptValues
  // reads them once per field.
  const own = mesh.geometry.getAttribute(field.attribute) && keptValues(mesh, field);
  const toward = own && blend?.field && blend.weight > 0 && mesh.geometry.getAttribute(blend.field.attribute) ? keptValues(mesh, blend.field) : null;
  const values = toward ? blended(mesh, own, toward, blend.weight) : own;
  if (!color || !values) {
    return false;
  }
  const kept = shown(mesh);
  const under = threshold?.field ? keptValues(mesh, threshold.field) : null;
  const faces = vertexFaces(mesh);
  const tinted = faces && highlight?.length ? new Set(highlight) : null;
  const partOf = vertexParts(mesh);
  const tintedParts = partOf && parts?.length ? new Set(parts) : null;
  const lightParts = partOf && softParts?.length ? new Set(softParts) : null;
  const sorted = (set) => (set ? [...set].sort((a, b) => a - b).join(",") : "");
  const cut = under ? `${threshold.field.attribute}<${threshold.value}x${threshold.scale}` : "";
  const mix = toward ? `~${blend.field.attribute}@${blend.weight}` : "";
  const key = `${field.attribute}${mix}x${valueScale}/${rangeScale}|${cut}|${sorted(tinted)}|${sorted(tintedParts)}|${sorted(lightParts)}`;
  if (kept.field === key) {
    return false;
  }
  const table = rampTable(ramp);
  const low = field.min * rangeScale;
  const span = (field.max - field.min) * rangeScale;
  const stride = color.itemSize;
  const bytes = color.array;
  const cutScale = under ? threshold.scale ?? 1 : 1;
  // A field whose worst is its lowest (a life, a fatigue margin) runs down the ramp, so its worst is red.
  const lowWorst = fieldInfo(field.attribute)?.lowWorst === true;
  for (let i = 0; i < values.length; i += 1) {
    const along = span > 0 ? clamp((values[i] * valueScale - low) / span, 0, 1) : 0;
    const t = lowWorst ? 1 - along : along;
    const entry = Math.round(t * 255) * 3;
    const grey = under !== null && under[i] * cutScale < threshold.value;
    const base = i * stride;
    const tint = (tinted !== null && tinted.has(Math.round(faces[i]))) || (tintedParts !== null && tintedParts.has(Math.round(partOf[i])));
    const blend = tint ? HIGHLIGHT_BLEND : lightParts !== null && lightParts.has(Math.round(partOf[i])) ? SOFT_BLEND : 0;
    for (let k = 0; k < 3; k += 1) {
      const own = grey ? BELOW_THRESHOLD[k] : table[entry + k];
      bytes[base + k] = blend ? Math.round(own + (HIGHLIGHT[k] - own) * blend) : own;
    }
    if (stride > 3) bytes[base + 3] = 255;
  }
  color.needsUpdate = true;
  kept.field = key;
  return true;
}

/** Two frames' values `weight` of the way from one to the other, in a buffer kept on the mesh (a series plays every frame). */
function blended(mesh, from, to, weight) {
  const kept = shown(mesh);
  if (!kept.blend || kept.blend.length !== from.length) kept.blend = new Float32Array(from.length);
  for (let i = 0; i < from.length; i += 1) kept.blend[i] = from[i] + (to[i] - from[i]) * weight;
  return kept.blend;
}

/**
 * Show the displacement at `scale` times its true size. The file's positions
 * already carry `baseScale` times the displacement, so the change is
 * `(scale - baseScale)` times the displacement vector. Returns true when the
 * positions changed; false when that scale was already shown.
 *
 * `attribute`: the vector to deform by, where it is not the displacement the file baked in (a mode
 * shape, a frame of a series): the positions are then the file's, less what it baked in, plus
 * `scale` times that vector. Or a list of `[attribute, weight]` terms, the vector their sum (a
 * harmonic frame turning through its phase, re·cos − im·sin; a series between two frames).
 */
export function applyDeformation(mesh, scale, baseScale, attribute = DISPLACEMENT) {
  const geometry = mesh.geometry;
  const position = geometry.getAttribute("position");
  const terms = (Array.isArray(attribute) ? attribute : [[attribute, 1]]).map(([name, weight]) => [geometry.getAttribute(name), Number(weight) || 0, name]);
  if (!position || !terms.length || terms.some(([vectors]) => !vectors || vectors.itemSize !== 3)) {
    return false;
  }
  const kept = shown(mesh);
  const wanted = Number(scale) || 0;
  // The displacement the file baked in, at its own scale, is today's: drawn as it always was.
  const plain = terms.length === 1 && terms[0][2] === DISPLACEMENT && terms[0][1] === 1;
  const key = plain ? wanted : `${terms.map(([, weight, name]) => `${name}*${weight}`).join("+")}x${wanted}`;
  if (kept.scale === key || (kept.scale === null && plain && wanted === (Number(baseScale) || 0))) {
    kept.scale = key;
    return false;
  }
  const out = position.array;
  const base = kept.position;
  if (plain) {
    const delta = wanted - (Number(baseScale) || 0);
    const d = terms[0][0].array;
    for (let i = 0; i < out.length; i += 1) {
      out[i] = base[i] + delta * d[i];
    }
  } else {
    const baked = geometry.getAttribute(DISPLACEMENT);
    const rest = baked?.itemSize === 3 && baked.count * 3 === out.length ? baked.array : null;
    const bakedScale = Number(baseScale) || 0;
    for (let i = 0; i < out.length; i += 1) {
      let v = 0;
      for (const [vectors, weight] of terms) v += weight * vectors.array[i];
      out[i] = base[i] - (rest ? bakedScale * rest[i] : 0) + wanted * v;
    }
  }
  position.needsUpdate = true;
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  kept.scale = key;
  return true;
}

/** A field over a range symmetric about 0 (± its largest magnitude): a signed shape that swings through its sign (Ring). */
export function symmetricRange(field) {
  const most = Math.max(Math.abs(field.min), Math.abs(field.max));
  return most > 0 ? { ...field, min: -most, max: most } : field;
}

/** The least a routine (Vibrate, the Load ramp, Play) moves the model: its largest motion this share of the model's size. */
export const ROUTINE_MOTION_SHARE = 0.1;

/**
 * The exaggeration a routine plays at: the one shown (the Exaggerate control's, `scale`), raised where that would
 * move the model's largest motion (over the vectors `attributes`) less than `ROUTINE_MOTION_SHARE` of its diagonal,
 * so a small part's motion (a piezo bimorph, a disc's mode) is clearly seen; an exaggeration of 0 stays 0.
 */
export function routineScale(mesh, attributes, scale) {
  const wanted = Number(scale) || 0;
  if (!(wanted > 0)) return wanted;
  const kept = shown(mesh);
  if (kept.diagonal === undefined) {
    const rest = kept.position;
    const low = [Infinity, Infinity, Infinity];
    const high = [-Infinity, -Infinity, -Infinity];
    for (let i = 0; i < rest.length; i += 1) {
      low[i % 3] = Math.min(low[i % 3], rest[i]);
      high[i % 3] = Math.max(high[i % 3], rest[i]);
    }
    kept.diagonal = rest.length ? Math.hypot(high[0] - low[0], high[1] - low[1], high[2] - low[2]) : 0;
  }
  kept.peaks ||= {};
  let peak = 0;
  for (const name of attributes) {
    if (kept.peaks[name] === undefined) {
      const vectors = mesh.geometry.getAttribute(name);
      let most = 0;
      if (vectors?.itemSize === 3) {
        const a = vectors.array;
        for (let i = 0; i + 2 < a.length; i += 3) most = Math.max(most, Math.hypot(a[i], a[i + 1], a[i + 2]));
      }
      kept.peaks[name] = most;
    }
    peak = Math.max(peak, kept.peaks[name]);
  }
  return peak > 0 && kept.diagonal > 0 ? Math.max(wanted, (ROUTINE_MOTION_SHARE * kept.diagonal) / peak) : wanted;
}

/**
 * What a view's control can move, the closed set the viewer knows how to apply: the four every
 * result has, and over a series the `mode` shown (modal, buckling) or the `frame` (a time, a
 * frequency, a load step), and a random vibration's `sigma` level.
 */
export const FEA_DRIVES = Object.freeze(["field", "deformation", "load_scale", "threshold", "mode", "frame", "sigma"]);
const DRIVE_TYPES = Object.freeze({ field: "enum", deformation: "number", load_scale: "number", threshold: "number", mode: "enum", frame: "number", sigma: "enum" });
const DRIVE_LABELS = Object.freeze({ field: "Field", deformation: "Deformation", load_scale: "Load", threshold: "Show above" });
// The drives a series answers (frameControl) and the sigma level (sigmaControl): each built from the result, the view giving its label and default.
const SERIES_DRIVES = Object.freeze({ mode: (result, raw) => frameControl(result, "mode", raw), frame: (result, raw) => frameControl(result, "frame", raw),
  sigma: (result, raw) => sigmaControl(result, raw) });

/** A view's field name ("von_mises") as the attribute the result carries ("_von_mises"). */
const fieldAttribute = (name) => `_${String(name || "").toLowerCase()}`;

const finiteNumber = (value) => typeof value === "number" && Number.isFinite(value);

/**
 * Study's What you see controls, as generic parameters (`@text-to-cad/core/common/parameters.js`: `id`,
 * `type`, `label`, `min`, `max`, `defaultValue`, `unit`, `options`) with `drives`, what each moves:
 * `field` (which field the colours show; its options are attributes), `deformation` (how many times
 * the displacement is drawn), `load_scale` (the load as a multiple of the solved one) and
 * `threshold` (values of its `field` under it drawn grey). They are the study's `view.controls`, in
 * its order, with its labels and ranges; one whose `drives` or `type` this viewer does not know, or
 * whose range or fields it cannot use, is skipped. With no view, or none of its controls this viewer
 * can draw (an empty list, or all from a newer cadgen), the analysis's own (`defaultControls`): for
 * static, a field select over every field, opening on the first (stress), and a deformation slider
 * from 0 to four times the file's own scale. A view that picks the field but names no deformation keeps
 * the analysis's own Deformation slider after its controls. The view's are labelled in the agent's words, often a
 * sentence: their labels run over the whole row (`wideLabel`), where the default two keep the
 * one-column look they always had.
 */
export function feaControls(result) {
  const every = result.fields.map((entry) => entry.attribute);
  const chosen = result.view?.controls ? viewControls(result, every) : [];
  return chosen.length ? keptDeformation(result, chosen) : feaAnalysis(result).defaultControls(result);
}

/**
 * A view that picks the field but says nothing of the deformation keeps the analysis's own Deformation
 * slider, after its controls: choosing what the colours show is no reason to lose how far it is drawn.
 */
function keptDeformation(result, chosen) {
  if (!chosen.some((control) => control.drives === "field") || chosen.some((control) => control.drives === "deformation")) return chosen;
  const own = feaAnalysis(result).defaultControls(result).find((control) => control.drives === "deformation");
  return own ? [...chosen, own] : chosen;
}

/** The view's controls this viewer can draw, in its order; none when it names none it knows. */
function viewControls(result, every) {
  const controls = [];
  for (const raw of result.view.controls) {
    const drives = raw.drives;
    const type = DRIVE_TYPES[drives];
    if (!type || (raw.type ?? type) !== type || controls.some((control) => control.drives === drives)) continue;
    // A load control only where the analysis follows the load (a temperature or a frequency does not).
    if (drives === "load_scale" && !feaAnalysis(result).scalesWithLoad) continue;
    if (SERIES_DRIVES[drives]) {
      const built = SERIES_DRIVES[drives](result, raw);
      if (built) controls.push({ ...built, wideLabel: true, ...whenOf(raw) });
      continue;
    }
    const label = typeof raw.label === "string" && raw.label.trim() ? raw.label.trim() : DRIVE_LABELS[drives];
    if (drives === "field") {
      const options = fieldOptions(result, Array.isArray(raw.options) ? raw.options.map(fieldAttribute) : every);
      if (!options.length) continue;
      const opening = options.find((option) => option.value === fieldAttribute(raw.default)) || options[0];
      controls.push({ id: drives, drives, type, label, options, defaultValue: opening.value, wideLabel: true, ...whenOf(raw) });
      continue;
    }
    // A deformation with no range is the default slider's: none to four times the file's own exaggeration.
    const ranged = !(drives === "deformation" && !finiteNumber(raw.max));
    const own = ranged ? null : deformationRange(result.deformationScale);
    const min = own ? own.min : finiteNumber(raw.min) ? raw.min : 0;
    const max = own ? own.max : raw.max;
    if (!finiteNumber(max) || !(min < max)) continue;
    const measured = drives === "threshold" ? result.fields.find((entry) => entry.attribute === fieldAttribute(raw.field)) : null;
    if (drives === "threshold" && !measured) continue;
    const fallback = drives === "load_scale" ? 1 : drives === "deformation" ? result.deformationScale : min;
    const unit = typeof raw.unit === "string" && raw.unit.trim() ? raw.unit.trim() : measured ? measured.units : "×";
    controls.push({
      id: drives, drives, type, label, min, max, defaultValue: clamp(finiteNumber(raw.default) ? raw.default : fallback, min, max), unit, wideLabel: true,
      ...(measured ? { field: measured.attribute } : {}), ...(own ? { step: own.step } : {}), ...whenOf(raw),
    });
  }
  return controls;
}

/** When a control shows, as the view says: `failing` or `passing`; a control that says neither, or what this viewer does not know, always. */
const whenOf = (raw) => (raw.when === "failing" || raw.when === "passing" ? { when: raw.when } : {});

/** Whether a control with this `when` shows, with the checks failing (or close) or not; null, nothing judged, shows every one. */
const showsWhen = (when, failing) => failing === null || !when || (when === "failing" ? failing : !failing);

/**
 * The controls What you see shows, and what each control does, at the values chosen (`values`, by id):
 * a control shows `when` the checks say, judged at the load shown (`feaFailing`). The load control's
 * own `when` is judged at its default load, where it opens (the load as solved unless the view says),
 * so moving it never hides it, the very control a person drags to see what load would pass. A hidden
 * control acts as if at its default (`values` keeps what was chosen, for when it shows again).
 * `shown`: the controls, in order; `effective`: every control's value, by id; `loadScale`: the load shown.
 */
export function feaShownControls(result, controls, values) {
  const load = controls.find((control) => control.drives === "load_scale") || null;
  const loadShown = !load || showsWhen(load.when, feaFailing(result, load.defaultValue));
  const loadScale = load ? finiteNumber(values[load.id]) && loadShown ? values[load.id] : load.defaultValue : 1;
  const failing = feaFailing(result, loadScale);
  const shown = controls.filter((control) => (control === load ? loadShown : showsWhen(control.when, failing)));
  const effective = Object.fromEntries(controls.map((control) => [control.id, shown.includes(control) ? values[control.id] : control.defaultValue]));
  return { shown: atSigma(shown, effective), effective, loadScale };
}

/**
 * The field select's RMS options at the sigma level chosen ("Stress (3σ)"), as the colour bar says it;
 * the controls as they are with no sigma control.
 */
function atSigma(controls, effective) {
  const sigma = controls.find((control) => control.drives === "sigma");
  const level = sigma ? Number(effective[sigma.id]) : NaN;
  if (!SIGMA_LEVELS.includes(level) || level === 1) return controls;
  return controls.map((control) => (control.drives !== "field" ? control : {
    ...control,
    options: control.options.map((option) => (isRms({ attribute: option.value })
      ? { ...option, label: option.label.replace("(1σ)", `(${level}σ)`) } : option)),
  }));
}

/** The parts of Study, in order: the view's `sections` this viewer knows, each once; with none, all four. */
export const FEA_SECTIONS = Object.freeze(["verdict", "setup", "controls", "details"]);
export function feaSections(result) {
  const named = (result.view?.sections || []).filter((name, index, all) => FEA_SECTIONS.includes(name) && all.indexOf(name) === index);
  return named.length ? named : FEA_SECTIONS;
}

/** Every control at its default, by id. */
export function feaDefaults(controls) {
  return Object.fromEntries(controls.map((control) => [control.id, control.defaultValue]));
}

/** A preset's value for an enum control as one of its options: a field's name as its attribute, a mode's number as its frame's place, a sigma level as is. */
function presetOption(result, control, value) {
  if (control.drives === "mode") {
    const index = finiteNumber(value) ? (result.series?.frames || []).findIndex((frame) => frame.value === value) : -1;
    return index >= 0 ? String(index) : null;
  }
  if (control.drives === "sigma") return value === undefined || value === null ? null : String(value);
  return fieldAttribute(value);
}

/**
 * The study's named states over its controls, as a Preset select lists them: `value` (its place),
 * `label`, and `values`, every control at its default but what the preset sets (a full state, as a
 * kinematics pose is). What a preset names that no control drives is left out.
 */
export function feaPresets(result, controls) {
  const defaults = feaDefaults(controls);
  return (result.view?.presets || []).map((preset, index) => {
    const values = { ...defaults };
    for (const control of controls) {
      const value = preset[control.id];
      if (control.type === "enum") {
        const option = presetOption(result, control, value);
        if (control.options.some((entry) => entry.value === option)) values[control.id] = option;
      }
      if (control.type === "number" && finiteNumber(value)) values[control.id] = control.snaps ? snapFrame(control, value) : clamp(value, control.min, control.max);
    }
    return { value: `preset:${index}`, label: preset.label.trim(), values };
  });
}

/**
 * Whether the loads and the fixtures are drawn on the model, as the study's `view.show` says: each
 * unless it is false. `on` is the Display switch's default, on while either is drawn; turned on by
 * the person when the view turned both off, it draws both.
 */
export function feaMarkerShow(result) {
  const show = result.view?.show || {};
  const loads = show.loads !== false;
  const fixtures = show.fixtures !== false;
  return { on: loads || fixtures, loads: loads || !fixtures, fixtures: fixtures || !loads };
}

/** An assembly's Parts panel shows from this many parts up; under it the picked face's Reference names its part. */
export const PARTS_PANEL_FROM = 6;

/**
 * Whether an assembly's Parts panel is shown: as the study's `view.show.parts` says, else only from
 * `PARTS_PANEL_FROM` parts up, since a few parts are told apart on the model, a picked face's
 * Reference naming its part, and the findings name the joints. Never for a single part.
 */
export function feaShowsParts(result) {
  if (!result.parts.length) return false;
  const chosen = result.view?.show?.parts;
  return typeof chosen === "boolean" ? chosen : result.parts.length >= PARTS_PANEL_FROM;
}

/**
 * A safety factor at `loadScale` times the solved load: yield over a stress that many times larger.
 * No load has no factor to say (null, so "holds" is left out rather than "holds Infinity×").
 */
const scaledFactor = (factor, loadScale) => {
  if (factor === null || !(loadScale > 0)) return null;
  const scaled = factor / loadScale;
  return Number.isFinite(scaled) ? scaled : null;
};

/** A colour bar end's text: enough figures to tell the values apart, no more. */
export function formatValue(value) {
  const v = Number(value) || 0;
  if (v === 0) return "0";
  const magnitude = Math.abs(v);
  if (magnitude >= 100) return v.toFixed(0);
  if (magnitude >= 10) return v.toFixed(1);
  if (magnitude >= 1) return v.toFixed(2);
  return v.toPrecision(3);
}

/** A part's row detail: its material and what it holds ("yields" under a factor of 1), at `loadScale` times the load. */
function partDetail(part, loadScale) {
  const factor = scaledFactor(part.safetyFactor, loadScale);
  const holds = factor === null ? "" : factor < 1 ? "yields" : `holds ${flooredFactor(factor)}×`;
  return [part.material, holds].filter(Boolean).join(" · ");
}

/** A joint's row detail: bonded with its contact area and any gap closed, or not connected and how far apart. */
function jointDetail(joint) {
  const gap = joint.gapMm !== null && joint.gapMm > 0 ? `${plainNumber(joint.gapMm)} mm` : "";
  if (joint.type !== "bonded") return ["not connected", gap ? `${gap} apart` : ""].filter(Boolean).join(" · ");
  return ["bonded", joint.areaMm2 === null ? "" : `${plainNumber(joint.areaMm2)} mm²`, gap ? `${gap} gap closed` : ""].filter(Boolean).join(" · ");
}

/** What a prompt calls a joint: "Bonded joint between 'post' and 'base'". */
function jointSummary(joint) {
  const [first, second] = joint.names;
  return joint.type === "bonded" ? `Bonded joint between '${first}' and '${second}'` : `'${first}' and '${second}' aren't connected`;
}

/**
 * A joint as it is chosen: its interface `faces`, or for a free pair (no faces) both parts' refs
 * (`refs`), with both parts tinted lightly (`softParts`, indices into the result's `parts`) and
 * what a prompt calls it; `name` says both parts, for its button's name. One id per joint, so its
 * row under either part is the same choice.
 */
function jointChoice(result, joint, index) {
  return {
    id: `joint:${index}`, name: `${spaced(joint.names[0])} ↔ ${spaced(joint.names[1])}`, detail: jointDetail(joint), wrap: true,
    softParts: joint.between.map((ref) => result.parts.findIndex((part) => part.ref === ref)).filter((at) => at >= 0),
    ...(joint.faces.length ? { faces: joint.faces } : { refs: joint.between.filter(Boolean) }), summary: jointSummary(joint),
  };
}

/**
 * The Parts panel's rows, for an assembly (`parts` in the file); [] for a single part. One row per
 * part, chosen like a face's: its ref into Quick Edit (`refs`) and its triangles tinted (`parts`).
 * Under it, each joint it is in, named by the OTHER part ("↔ base") with how it is joined, so a
 * joint is under both its parts and either row is the same choice (`jointChoice`). Details wrap
 * (`wrap`) rather than truncate. What each part holds is at `loadScale` times the solved load.
 */
export function partRows(result, loadScale = 1) {
  const joints = result.connections.map((joint, index) => jointChoice(result, joint, index));
  return result.parts.map((part, index) => {
    const children = part.ref ? result.connections.flatMap((joint, at) => {
      const side = joint.between.indexOf(part.ref);
      return side < 0 ? [] : [{ ...joints[at], label: `↔ ${spaced(joint.names[1 - side])}` }];
    }) : [];
    return {
      id: `part:${index}`, label: spaced(part.name || part.ref), detail: partDetail(part, loadScale), wrap: true, refs: part.ref ? [part.ref] : [], parts: [index],
      summary: `Part '${part.name || part.ref}'`, ...(children.length ? { children } : {}),
    };
  });
}

/** The index of an assembly's weakest part: the one the file names, else the lowest safety factor; -1 for none. */
export function weakestPartIndex(result) {
  const named = result.weakestPart ? result.parts.findIndex((part) => part.name === result.weakestPart) : -1;
  if (named >= 0) return named;
  let weakest = -1;
  result.parts.forEach((part, index) => {
    if (part.safetyFactor !== null && (weakest < 0 || part.safetyFactor < result.parts[weakest].safetyFactor)) weakest = index;
  });
  return weakest;
}

/** The safety factor a study asks a part to keep, where it records none: cadgen's own default. */
export const DEFAULT_MARGIN = 2;

/**
 * The checks the verdict judges: the file's (`checks`), else, for a result written before them, the
 * stress check derived from what it has, today's verdict (the peak against the weakest part's yield,
 * its safety factor and the study's margin). [] where the file cannot say: no stress field, or a
 * stress with no safety factor (older than the factor), or an analysis outside the static family
 * that judged nothing.
 */
export function feaChecks(result) {
  if (result.checks) return result.checks;
  if (feaAnalysis(result).family !== "static") return [];
  const stress = result.fields.find((entry) => entry.attribute === "_von_mises");
  const factor = result.safetyFactor;
  if (!stress || factor === null || !(factor > 0)) return [];
  const margin = result.study?.margin ?? DEFAULT_MARGIN;
  const weakest = result.parts[weakestPartIndex(result)] || null;
  const value = result.weakestPartPeakMPa ?? weakest?.peakMPa ?? stress.max;
  // The limit is the yield of the part these numbers are for; failing that, what the factor says it is.
  const limit = weakest?.yieldMPa ?? result.study?.material?.yieldMPa ?? value * factor;
  return [{ kind: "stress", label: "", value, limit, unit: stress.units || "MPa", ratio: 1 / factor, closeAt: 1 / margin, margin,
    status: factor < 1 ? "fails" : factor < margin ? "close" : "passes", part: "" }];
}

const STATUS_RANK = Object.freeze({ fails: 0, close: 1, passes: 2 });
// The verdict's tones: each status as the findings card's tones name it.
const TONE_OF = Object.freeze({ fails: "weak", close: "close", passes: "strong" });

/** The noun a result's takeaway line uses: "this load", "this shake". */
const nounOf = (result) => result.analysis?.noun || feaAnalysis(result).noun;

/**
 * The margin a check is held to, where its kind has one: a stress check's own, else the study's,
 * else cadgen's 2; a buckling or fatigue check's own (buckling's limit is its margin). null for a
 * kind judged by a share of its limit alone.
 */
function marginOf(result, check) {
  if (check.kind === "stress") return check.margin ?? result.study?.margin ?? DEFAULT_MARGIN;
  if (!CHECK_KINDS[check.kind].margin) return null;
  return check.margin ?? (check.kind === "buckling" ? check.limit : null);
}

/**
 * One check at `loadScale` times the solved load (a linear study scales exactly), as its kind moves
 * with the load (`scaling`): a linear kind's value and share of its limit (`use`) k times the solved
 * ones, an inverse kind's value (buckling's load factor) over k and its share k times, a quadratic
 * check (`scaling` on the check: a magnetic force's stress, with the current squared) k² times, its
 * `times` the square root of the room left, and a kind that does not scale as solved. `times`: how many times this load it would take to reach the limit
 * (null for a kind that does not scale), and its `status` at it. The stress check's is the result's
 * safety factor over k (its margin, not a share, makes it close), so it says exactly what the safety
 * factor says; at the solved load a check's status is the one cadgen judged.
 */
function checkAt(result, check, k) {
  // The check's own scaling (cadgen's: "none" for an analysis not linear in the load, "quadratic" for a magnetic
  // force's), else its analysis's for every check (nonlinear, contact, bolt, composite: "none"), else its kind's.
  const scaling = check.scaling || feaAnalysis(result).scaling || CHECK_KINDS[check.kind].scaling;
  const moves = scaling !== "none";
  // A quadratic check (a magnetic force's stress) is k² times as much at k times the drive.
  const power = scaling === "quadratic" ? 2 : 1;
  const grown = k ** power;
  const use = check.ratio * (moves ? grown : 1);
  // How many times this drive reaches the limit: the power's root of the room left.
  const factor = check.kind === "stress" && result.safetyFactor !== null && result.safetyFactor > 0 ? result.safetyFactor / grown : 1 / use;
  const times = !moves ? null : factor ** (1 / power);
  const margin = marginOf(result, check);
  const status = (k === 1 || !moves) && check.status ? check.status
    : times === null ? (use >= 1 ? "fails" : use > check.closeAt ? "close" : "passes")
      : factor < 1 ? "fails" : (margin !== null ? factor < margin : use > check.closeAt) ? "close" : "passes";
  const shown = scaling === "linear" || scaling === "quadratic" ? check.value * grown : scaling === "inverse" ? check.value / k : check.value;
  return { ...check, use: check.kind === "stress" ? 1 / factor : use, times, status, margin, shown };
}

const STATUS_WORDS = Object.freeze({ fails: "fails", close: "is close to its limit", passes: "passes" });

/**
 * What a check chosen in the verdict carries into a prompt: the faces it is over, else the face it
 * peaks on, else the whole result; and what it says, in one sentence ("Tip sag fails: moves 0.62 mm,
 * limit 0.5 mm (OK only to 0.8× this load)"; a kind that does not scale with the load, its line
 * alone). `part`: whose numbers a stress check's are, in an assembly.
 */
function checkChoice(result, check, part, label) {
  const faces = check.faces?.length ? check.faces : check.where ? [check.where] : [];
  const noun = nounOf(result);
  const line = kindLine(check, { noun }).replace(/ /g, " ");
  const where = check.kind === "stress" && part ? ` in ${part}` : "";
  const takeaway = check.times !== null ? ` (${loadCaption(check.times, noun)})` : "";
  const summary = `${label} ${STATUS_WORDS[check.status]}${where}: ${line[0].toLowerCase()}${line.slice(1)}${takeaway}`;
  // Where its value occurs in a series (a mode, a moment, a frequency), choosing it shows that frame.
  const frame = result.series && check.at && check.at.frame < result.series.frames.length ? { frame: check.at.frame } : {};
  return { id: `check:${check.index}`, ...(faces.length ? { faces } : { refs: wholeRefs(result) }), summary, ...frame };
}

/** Whether cadgen took a step to fit the run that cost some accuracy (a step with an accuracy note, or a share it moved the answer by). */
export const feaAdapted = (result) => result.fit.some((step) => Boolean(step.accuracy) || (step.accuracyPct ?? 0) > 0);

const REYNOLDS = /\bRe\s*(\d[\d,.]*)/;
/**
 * A flow's warning that it ran past the laminar range: from the file's structured `analysis.reynolds`
 * (value, limit, kind) when it has one, else from its sentence (`analysis.warnings`: "Re 4200 is past
 * the laminar range: ..."): `{ sentence, limit }`, the Reynolds number the laminar solve is good to
 * (said in the sentence, else 1000 for an external flow, 2000 for an internal one).
 * null for none, or for another analysis.
 */
export function reynoldsWarning(result) {
  if (result.analysis?.type !== "cfd") return null;
  // The structured number first (`analysis.reynolds`), with the file's sentence where it gives one.
  const stated = result.analysis.reynolds;
  if (stated) {
    if (stated.value <= stated.limit) return null;
    const line = result.analysis.warnings.find((text) => REYNOLDS.test(text) && /laminar|turbulen/i.test(text));
    return { sentence: line || `Re ${Math.round(stated.value)} is past the laminar range: real flow is likely turbulent, so this pressure drop is a lower bound and the flow pattern may be wrong`, limit: stated.limit };
  }
  const sentence = result.analysis.warnings.find((line) => REYNOLDS.test(line) && /laminar|turbulen/i.test(line));
  if (!sentence) return null;
  const said = /above Re\s*(\d[\d,]*)/i.exec(sentence);
  return { sentence, limit: said ? Number(said[1].replace(/,/g, "")) : result.study?.flow?.kind === "external" ? 1000 : 2000 };
}

const MACH_SENTENCE = /\bMach\s*\d[\d.]*.*(past Mach|faster than sound)/i;
/**
 * A fast gas flow's warning that it ran past what its solver is checked to, from the file's
 * `analysis.mach` (checked false): `{ sentence, short, value, limit }`, the file's own sentence
 * (`analysis.warnings`) where it gives one, and the caption's few words: "past Mach 1.8", or, a flow
 * within it whose outlet runs supersonic, "supersonic outlet". null for none, or for another analysis.
 */
export function machWarning(result) {
  const mach = result.analysis?.mach;
  if (!mach || mach.checked) return null;
  const past = mach.limit !== null && mach.value > mach.limit;
  const stated = result.analysis.warnings.find((line) => MACH_SENTENCE.test(line));
  const sentence = stated || (past
    ? `Mach ${threeFigures(mach.value)} is past Mach ${plainNumber(mach.limit)}, the fastest this solver is checked to: shocks are captured over a few elements and their strength and place are approximate`
    : `Mach ${threeFigures(mach.value)}, and the gas leaves the outlet faster than sound: the flow near the outlet is not to be trusted`);
  return { sentence, short: past ? `past Mach ${plainNumber(mach.limit)}` : "supersonic outlet", value: mach.value, limit: mach.limit };
}

const UNSETTLED_SENTENCE = /did not settle/i;
/**
 * A contact solve whose forces did not settle at some load step (`analysis.unsettled`): `{ sentence,
 * short, percent }`, the file's own sentence (`analysis.warnings`) where it gives one, and the
 * caption's few words, "contact did not settle at 80%". null for none.
 */
export function unsettledWarning(result) {
  const unsettled = result.analysis?.unsettled;
  if (!unsettled) return null;
  const percent = plainNumber(unsettled.firstPercent);
  const sentence = result.analysis.warnings.find((line) => UNSETTLED_SENTENCE.test(line))
    || `Contact did not settle at ${percent}% of the load: the forces here do not balance, so this result is not reliable`;
  return { sentence, short: `contact did not settle at ${percent}%`, percent: unsettled.firstPercent };
}

/**
 * What leads the verdict's takeaway, by the analysis's tier, after "Not reliable · contact did not
 * settle at 80% · " where a contact solve's forces did not settle (`unsettledWarning`): "Estimate · " for an estimate (Tier 2),
 * a Tier 3 analysis's short limit word ("Laminar · ", "Rigid floor · "; a flow past the laminar
 * range "Laminar · unreliable above Re 2000 · "; a fast gas flow the file warns of "Ideal gas · past
 * Mach 1.8 · "); "" for Tier 1. And what ends it: " · adapted" where a step to fit the run cost some
 * accuracy.
 */
function captionFrame(result, analysis) {
  const lead = [];
  const unsettled = unsettledWarning(result);
  if (unsettled) lead.push("Not reliable", unsettled.short);
  if (result.analysis?.estimate || (result.analysis?.tier ?? analysis.tier) === 2) lead.push("Estimate");
  if ((result.analysis?.tier ?? analysis.tier) === 3) {
    const reynolds = reynoldsWarning(result);
    // An analysis whose limit word follows what the file solved (electromagnetic: "Static", or "AC" at a frequency).
    const word = (typeof analysis.limitWordOf === "function" && analysis.limitWordOf(result)) || analysis.limitWord;
    const mach = machWarning(result);
    lead.push(word || "Lite", ...(reynolds ? [`unreliable above Re ${reynolds.limit}`] : []), ...(mach ? [mach.short] : []));
  }
  return { lead: lead.length ? `${lead.join(" · ")} · ` : "", tail: feaAdapted(result) ? " · adapted" : "" };
}

/**
 * Whether some check fails or is close at `loadScale` times the solved load: what a control's `when`
 * reads. null where the file judges nothing (no checks, or no load), so every control shows.
 */
export function feaFailing(result, loadScale = 1) {
  const k = Number(loadScale) >= 0 ? Number(loadScale) : 1;
  const checks = feaChecks(result);
  if (!checks.length || !(k > 0)) return null;
  return checks.some((check) => checkAt(result, check, k).status !== "passes");
}

// The headline over several checks: how many fail, else whether any is close.
const failedTitle = (failing, total) => (failing === total ? (total === 2 ? "Fails both checks" : `Fails all ${total} checks`)
  : `Fails ${failing} of ${total} checks`);

/**
 * The answer at a glance, at `loadScale` times the solved load, for the verdict at the top of Study:
 * a headline, one line of what it means for the load, then every check the same way. `status` is
 * the worst check's tone ("weak" failing, "close", "strong" passing; "none" with no stress: no load
 * reaches the part, or the load is set to 0). `title`: one check's own words ("Too weak", "Moves too
 * much", "Stiff enough", its kind's, `checkKinds.js`), or over several, how many fail ("Fails both
 * checks"), else "Close to the limit" or "Passes all checks". `caption`: how much of this load (the
 * analysis's noun) the weakest check takes ("OK only to 0.4× this load"; with no stress, what to do),
 * or where the worst check's kind does not scale with the load, its own sentence ("Hottest 84 °C,
 * 16 °C under its limit"), or the analysis's own where it has one (a collapse: "Lite · Collapses at
 * about 70 % of the load"). `rows`: each check, worst first (failing before close before passing, then
 * the most of its limit used), with its `label` in the person's words, the `part` a stress check's
 * numbers are for in an assembly, its `line` (the value against the limit, the label saying what it
 * is: "405 MPa, limit 276 MPa"), `use` (the share of the limit, 1 at it), the `margin` a stress,
 * buckling or fatigue check is held to (null for another) and its `choice` for Quick Edit. null where
 * the file cannot say: in the static family, no stress field, or a stress with no safety factor and
 * no checks (a result older than both); in any other analysis, no checks.
 */
export function feaVerdict(result, loadScale = 1) {
  const analysis = feaAnalysis(result);
  const staticFamily = analysis.family === "static";
  const stress = result.fields.find((entry) => entry.attribute === "_von_mises");
  if (staticFamily && !stress) return null;
  const k = Number(loadScale) >= 0 ? Number(loadScale) : 1;
  if (!(k > 0)) return { status: "none", title: "No load", caption: "The load is set to 0", rows: [] };
  const checks = feaChecks(result);
  if (staticFamily) {
    const unloaded = checks.some((check) => check.kind === "stress" && !(check.value > 0));
    if (!checks.length || unloaded) {
      return stress.max > 0 && !unloaded ? null : { status: "none", title: "No stress", caption: "Check the load reaches the part", rows: [] };
    }
  } else if (!checks.length) return null;
  const noun = nounOf(result);
  const weakest = result.parts[weakestPartIndex(result)] || null;
  const weakestName = result.weakestPart ? spaced(result.weakestPart) : weakest?.name ? spaced(weakest.name) : "";
  const judged = checks.map((check, index) => ({ ...checkAt(result, check, k), index }))
    .sort((a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status] || b.use - a.use || a.index - b.index);
  const [worst] = judged;
  const failing = judged.filter((check) => check.status === "fails").length;
  const title = judged.length === 1 ? checkTitle(worst, worst.status)
    : failing ? failedTitle(failing, judged.length) : worst.status === "close" ? "Close to the limit" : "Passes all checks";
  // The load the weakest check takes, over the checks that scale with the load.
  const times = judged.filter((check) => check.times !== null).map((check) => check.times);
  const { lead, tail } = captionFrame(result, analysis);
  // An analysis may say the takeaway itself (a collapse: "Collapses at about 70 % of the load"), else the worst check's.
  const own = typeof analysis.caption === "function" ? analysis.caption(result) : "";
  return {
    status: TONE_OF[worst.status], title,
    caption: `${lead}${own || checkCaption(worst, { times: worst.times !== null ? Math.min(...times) : null, noun })}${tail}`,
    rows: judged.map((check) => {
      const part = check.kind === "stress" ? (check.part ? spaced(check.part) : weakestName) : "";
      const label = kindLabel(check, analysis.checkLabels);
      return { id: `check:${check.index}`, kind: check.kind, status: TONE_OF[check.status], label, part, line: kindLine(check, { bare: true, noun }),
        use: check.use, margin: check.margin, choice: checkChoice(result, check, part, label) };
    }),
  };
}

/**
 * A fast gas flow's Mach row in Details: where the file warns, its sentence (first, as a flow's
 * Reynolds warning is); else "Fastest flow Mach 1.2", its regime and the Mach the solver is checked
 * to its hint. [] for another analysis.
 */
function machRows(result, whole) {
  const mach = result.analysis?.mach;
  if (!mach) return [];
  const warning = machWarning(result);
  if (warning) return [{ id: "mach", label: warning.sentence, detail: "", wrap: true, ...whole(warning.sentence) }];
  const label = `Fastest flow Mach ${threeFigures(mach.value)}`;
  const hint = [mach.regime, mach.limit !== null ? `checked to Mach ${plainNumber(mach.limit)}` : ""].filter(Boolean).join(", ");
  const summary = `${label}${mach.regime ? ` (${mach.regime})` : ""}${mach.limit !== null ? `, within the Mach ${plainNumber(mach.limit)} its solver is checked to` : ""}`;
  return [{ id: "mach", label, detail: "", wrap: true, ...(hint ? { hint: `${hint.charAt(0).toUpperCase()}${hint.slice(1)}` } : {}), ...whole(summary) }];
}

/**
 * Details' rows, each chosen into Quick Edit with what it says: a contact solve's warning that its
 * forces did not settle (first, its own row); a flow's warning that it ran past the
 * laminar range (its own row, first); a fast gas flow's Mach number (`machRows`); the mesh (`detailRows`); "Adapted to fit", one row per step
 * cadgen took to fit the run, its words as the label and its accuracy note as the hint, chosen with
 * the faces it is about (the region kept fine, the features left out) tinted, else the whole result;
 * and a Tier 3 analysis's "Limits", one row per sentence of what its model leaves out.
 */
function detailsGroup(result) {
  const refs = wholeRefs(result);
  const whole = (summary) => (refs.length ? { refs, summary } : {});
  const reynolds = reynoldsWarning(result);
  const flow = reynolds ? [{ id: "reynolds", label: reynolds.sentence, detail: "", wrap: true, ...whole(reynolds.sentence) }] : [];
  const mesh = result.study ? detailRows(result)[0]?.children || [] : [];
  const fit = result.fit.length ? [{ id: "fit", label: "Adapted to fit", detail: "", children: result.fit.map((step, index) => {
    const summary = `Adapted to fit: ${step.words}${step.accuracy ? ` (${step.accuracy})` : ""}`;
    return { id: `fit:${index}`, label: step.words, detail: "", wrap: true, ...(step.accuracy ? { hint: step.accuracy } : {}),
      ...(step.faces.length ? { faces: step.faces, summary } : whole(summary)) };
  }) }] : [];
  const tier3 = result.analysis?.tier === 3 && result.analysis.limits.length;
  const limits = tier3 ? [{ id: "limits", label: "Limits", detail: "", children: result.analysis.limits.map((sentence, index) => ({
    id: `limit:${index}`, label: sentence, detail: "", wrap: true, ...whole(`Limits of this ${result.analysis.word.toLowerCase()} result: ${sentence}`) })) }] : [];
  const unsettled = unsettledWarning(result);
  const settle = unsettled ? [{ id: "unsettled", label: unsettled.sentence, detail: "", wrap: true, ...whole(unsettled.sentence) }] : [];
  // An analysis's own Details rows (`detailRows(result, whole)`: fsi's coupling iterations), before the mesh.
  const own = typeof feaAnalysis(result).detailRows === "function" ? feaAnalysis(result).detailRows(result, whole) : [];
  const children = [...settle, ...flow, ...machRows(result, whole), ...own, ...mesh, ...fit, ...limits];
  return children.length ? [{ id: "details", label: "Details", detail: "", collapsed: true, children }] : [];
}

// Details follow "What you see" (the panel's own), shut; a result kind with more to say adds a group here.
const DETAIL_GROUPS = Object.freeze([detailsGroup]);

/**
 * Study's rows for a result's study, in order: its analysis's setup (`setupGroups`: for static, where
 * it is held, the fixed faces; what pushes it, each load with its faces under it; what it is made
 * of), then Details (the mesh, shut: `DETAIL_GROUPS`). An assembly's parts and joints are the Parts
 * panel's (`partRows`). A row that stands for faces carries them (`faces`, the file's refs) and what a
 * prompt calls them (`summary`); a group row (`children`) carries none, and one of the setup's names
 * its `glyph`, the marker it is drawn as on the model. A row that opens shut says so (`collapsed`), and
 * a fact's further words are its hint (`hint`). [] for a result written before the study was recorded.
 */
export function studyRows(result) {
  const { setup, details } = studySections(result);
  return [...setup, ...details];
}

/** Study's rows by section: `setup` (the analysis's `setupGroups`) and `details` (`DETAIL_GROUPS`), each [] where the file records nothing for it. */
export function studySections(result) {
  return { setup: result.study ? feaAnalysis(result).setupGroups.flatMap((group) => group(result)) : [], details: DETAIL_GROUPS.flatMap((group) => group(result)) };
}

/**
 * What a picked face's Reference says of its part, in an assembly: its material and what it holds
 * at `loadScale` times the load ("6061-T6 · holds 1.4×", "yields"), as Parts' rows say it. "" for a
 * single part's face.
 */
export function facePartDetail(result, ref, loadScale = 1) {
  const index = facePartIndex(result, ref);
  return index < 0 ? "" : partDetail(result.parts[index], loadScale);
}

/** What a prompt calls a face, by what the study does to it; "Face 17" for a face it does nothing to. */
export function facePromptSummary(result, ref) {
  return (result.study && faceSummary(result.study, ref)) || faceLabel(ref);
}

/** What the study does to a face, in words: "fixed", "slides along it" (a roller), "2500 N load, down", "2 MPa pressure", or "free". */
export function faceRole(result, ref) {
  const study = result.study;
  if (!study) return "";
  const roles = [
    ...study.fixtures.filter((fixture) => fixture.faces.includes(ref)).map((fixture) => (isRoller(fixture) ? "slides along it" : fixture.type)),
    ...study.loads.filter((load) => load.faces.includes(ref)).map((load) => {
      const words = loadWords(load);
      return [[words.amount, words.noun].filter(Boolean).join(" "), words.direction].filter(Boolean).join(", ");
    }),
    // What another analysis does to it: a fixed temperature, heat, the air, the drop landing on it.
    ...study.temperatures.filter((entry) => entry.faces.includes(ref)).map((entry) => (entry.celsius === null ? "kept at a fixed temperature" : `kept at ${plainNumber(entry.celsius)} °C`)),
    ...study.heat.filter((entry) => entry.faces.includes(ref)).map((entry) => `${entry.watts !== null ? `${plainNumber(entry.watts)} W` : entry.fluxWm2 !== null ? `${plainNumber(entry.fluxWm2)} W/m²` : "some"} of heat in`),
    ...study.convection.filter((entry) => entry.faces.includes(ref)).map((entry) => `cooled by air${entry.ambientC === null ? "" : ` at ${plainNumber(entry.ambientC)} °C`}`),
    ...(study.radiation || []).filter((entry) => entry.faces.includes(ref)).map((entry) => `radiates${entry.ambientC === null ? "" : ` to ${plainNumber(entry.ambientC)} °C`}`),
    ...(study.drop?.onto.includes(ref) ? ["lands on the drop"] : []),
  ];
  return roles.length ? roles.join("; ") : "free";
}

/** The indices into the result's `faces` of these refs, for `recolorByField`'s tint. */
export function faceIndices(result, refs) {
  return refs.map((ref) => result.faces.indexOf(ref)).filter((index) => index >= 0);
}

const raycaster = new Raycaster();

/**
 * The source face of the result's triangle under a world-space ray: `{ id, ref, point }`, the
 * scene contract's pick (`kit/scene.js`), with `ref` the file's face ref. null over nothing, and
 * over a triangle the mesher matched to no face. `clip`: a world-space plane the view cuts the result
 * with (`feaClip.js`): what lies past it is not there to pick, so the ray goes on to what the cut shows.
 */
export function pickFace(result, ray, clip = null) {
  const faces = vertexFaces(result.mesh);
  if (!faces) return null;
  raycaster.ray.copy(ray);
  const hit = raycaster.intersectObject(result.mesh, false).find((entry) => !clip || clip.distanceToPoint(entry.point) >= -1e-6);
  const ref = hit?.face ? result.faces[Math.round(faces[hit.face.a])] : null;
  return ref ? { id: ref, ref, point: hit.point } : null;
}
