// A cadgen engine document's mechanism as a page poses it: the structure's `kinematics` block
// (`cadgen/engine/mechanism.py`, `block`), which the engine harvests from the model's build123d
// joints. Its links are the instances that move as one, its pairs join two links with a frame on
// each (4x4, column-major, in its link's frame, coinciding at value 0), and link 2 stands at
// `link_1 · item_1 · M(v) · item_2⁻¹`: M a turn about Z (revolute), a slide along Z (prismatic),
// both (cylindrical: angle, then distance) or an intrinsic X-Y-Z rotation (spherical). Degrees and
// millimetres. A coupling (`couplings`, by name) is a constraint among several pairs, AP242's
// couplers: at value c each of its pairs' values is its as-built one plus its ratio times c, so 0
// is as built, and its pairs move only through it. Its range is its joints' limits, the tightest
// interval in which each keeps within its own (null on a side nothing bounds).
//
// Posing is exact forward kinematics on the tree, from the ground down, the same fold the engine
// makes for a posed snapshot or export: each link's placement at the values over its placement at
// the values its instances stand at now, applied to them. No time: a pose is a configuration.

const DEG = Math.PI / 180;
const IDENTITY = Object.freeze([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);

/** The number of values a pair of `type` has. */
export const XBF_PAIR_VALUES = Object.freeze({ revolute: 1, prismatic: 1, cylindrical: 2, spherical: 3 });
const VALUE_NAMES = Object.freeze({ cylindrical: ["angle", "position"], spherical: ["x", "y", "z"] });

/** A document's mechanism, or null where it has none. */
export function xbfKinematics(structure) {
  const found = structure?.kinematics;
  return found && Array.isArray(found.pairs) && Array.isArray(found.links) ? found : null;
}

function multiply(a, b) {
  const out = new Array(16).fill(0);
  for (let column = 0; column < 4; column += 1) {
    for (let row = 0; row < 4; row += 1) {
      let sum = 0;
      for (let k = 0; k < 4; k += 1) sum += a[k * 4 + row] * b[column * 4 + k];
      out[column * 4 + row] = sum;
    }
  }
  return out;
}

/** The inverse of a rigid placement: its rotation transposed, its translation turned back. */
function invert(m) {
  const out = [m[0], m[4], m[8], 0, m[1], m[5], m[9], 0, m[2], m[6], m[10], 0, 0, 0, 0, 1];
  for (let row = 0; row < 3; row += 1) out[12 + row] = -(out[row] * m[12] + out[4 + row] * m[13] + out[8 + row] * m[14]);
  return out;
}

function rotation(axis, degrees) {
  const c = Math.cos(degrees * DEG), s = Math.sin(degrees * DEG);
  const out = [...IDENTITY];
  const [i, j] = [[1, 2], [2, 0], [0, 1]][axis];
  out[i * 4 + i] = c; out[j * 4 + i] = -s; out[i * 4 + j] = s; out[j * 4 + j] = c;
  return out;
}

/** `M(v)`: what a pair's values do between its two frames (4x4, column-major). */
export function xbfPairMotion(type, values) {
  if (type === "revolute") return rotation(2, values[0]);
  if (type === "prismatic") { const out = [...IDENTITY]; out[14] = values[0]; return out; }
  if (type === "cylindrical") { const out = rotation(2, values[0]); out[14] = values[1]; return out; }
  if (type === "spherical") return multiply(multiply(rotation(0, values[0]), rotation(1, values[1])), rotation(2, values[2]));
  throw new Error(`a ${type} pair has no value`);
}

const asValues = value => (Array.isArray(value) ? value.map(Number) : [Number(value)]);

/**
 * Each coupling of the block, by name: `{ range: [lower, upper], terms: [[pair, value index, ratio]] }`,
 * a side of the range null where nothing bounds it.
 * @returns {Record<string, { range: (number | null)[], terms: [string, number, number][] }>}
 */
export function xbfCouplings(kinematics) {
  const found = kinematics?.couplings;
  return found && typeof found === "object" && !Array.isArray(found) ? found : {};
}

/** A coupling's range as numbers: a side nothing bounds is infinite. */
function rangeOf(coupling) {
  const [lower, upper] = coupling?.range || [null, null];
  return [lower == null ? -Infinity : Number(lower), upper == null ? Infinity : Number(upper)];
}

/**
 * Each pair a coupling drives, which moves only through it: the coupling's name.
 * @returns {Map<string, string>}
 */
export function xbfCoupledPairs(kinematics) {
  const found = new Map();
  for (const [name, coupling] of Object.entries(xbfCouplings(kinematics))) {
    for (const [label] of coupling.terms || []) found.set(label, name);
  }
  return found;
}

/**
 * Each pair that cannot be posed, and why: each pair of a loop; and each coupling driving one.
 * @returns {Map<string, string>}
 */
export function xbfUnposable(kinematics) {
  const found = new Map();
  for (const label of kinematics?.loop || []) {
    if (!found.has(label)) found.set(label, `pairs ${kinematics.loop.join(", ")} close a loop, which has no pose without a solver`);
  }
  for (const [name, coupling] of Object.entries(xbfCouplings(kinematics))) {
    const stuck = (coupling.terms || []).find(([label]) => found.has(label));
    if (stuck) found.set(name, `its joint '${stuck[0]}' cannot be`);
  }
  return found;
}

/** What the build left out and no row says: the warnings of the block, but a loop's (its rows say it). */
export function xbfOtherWarnings(kinematics) {
  return (kinematics?.warnings || []).filter(text => !text.startsWith("pairs "));
}

function checked(pair, values, where) {
  const count = XBF_PAIR_VALUES[pair.type];
  if (values.length !== count || !values.every(Number.isFinite)) {
    throw new Error(`${where}: joint '${pair.label}' (${pair.type}) takes ${count === 1 ? "a number" : `${count} numbers`}`);
  }
  values.forEach((value, at) => {
    const [lower, upper] = pair.limits?.[at] || [null, null];
    if ((lower != null && value < lower - 1e-9) || (upper != null && value > upper + 1e-9)) {
      const unit = pair.units?.[at] || "";
      throw new Error(`${where}: joint '${pair.label}' at ${value} ${unit} is outside its range [${lower ?? "-inf"}, ${upper ?? "inf"}] ${unit}`);
    }
  });
  return values;
}

/**
 * The pair values couplings put their joints at: `controls` is each coupling's value by name, and
 * `given` the joints the same pose sets. Each joint stands at its as-built values plus each
 * coupling's ratio times its value (couplings sharing a joint add); a coupling set with one of its
 * joints, a value that is no number or is outside its coupling's range, a joint that cannot be
 * posed and one put past its limits are refused by name, as the engine refuses them.
 * @returns {Record<string, number[]>}
 */
function coupledValues(kinematics, controls, given, where) {
  const couplings = xbfCouplings(kinematics);
  const pairs = new Map(kinematics.pairs.map(pair => [pair.label, pair]));
  const unposable = xbfUnposable(kinematics);
  const moved = new Map(), by = new Map();
  for (const [name, value] of Object.entries(controls)) {
    const coupling = couplings[name];
    for (const [label] of coupling.terms) {
      if (label in given) throw new Error(`${where} sets coupling '${name}' and its joint '${label}': set one of them`);
      const why = unposable.get(label);
      if (why) throw new Error(`${where}: coupling '${name}' cannot be posed: its joint '${label}' cannot be: ${why}`);
    }
    const numbers = Array.isArray(value) ? value : [value];
    if (numbers.length !== 1 || typeof numbers[0] !== "number" || !Number.isFinite(numbers[0])) {
      throw new Error(`${where}: coupling '${name}' takes a number`);
    }
    const c = numbers[0];
    const [lower, upper] = rangeOf(coupling);
    if (c < lower - 1e-9 || c > upper + 1e-9) {
      throw new Error(`${where}: coupling '${name}' at ${c} is outside its range [${coupling.range[0] ?? "-inf"}, ${coupling.range[1] ?? "inf"}]`);
    }
    for (const [label, index, ratio] of coupling.terms) {
      if (!moved.has(label)) moved.set(label, asValues(kinematics.asBuilt[label]));
      moved.get(label)[index] += ratio * c;
      by.set(label, [...new Set([...(by.get(label) || []), `'${name}' at ${c}`])]);
    }
  }
  return Object.fromEntries([...moved].map(([label, row]) => [label,
    checked(pairs.get(label), row, `${where}: coupling${by.get(label).length > 1 ? "s" : ""} ${by.get(label).join(", ")}`)]));
}

/**
 * The values a pose sets every pair to: `pose` is null (as built), a configuration's name, or
 * `{ label: value }` (the rest as built), a label a joint's or a coupling's. What it names wrong is
 * refused by name, as the engine refuses it: a coupling's joint set alone among it.
 * @returns {Record<string, number[]>}
 */
export function xbfPoseValues(kinematics, pose = null) {
  const values = Object.fromEntries(Object.entries(kinematics.asBuilt || {}).map(([label, value]) => [label, asValues(value)]));
  const pairs = new Map(kinematics.pairs.map(pair => [pair.label, pair]));
  const couplings = xbfCouplings(kinematics);
  const coupled = xbfCoupledPairs(kinematics);
  let given = {}, where = "the pose";
  if (typeof pose === "string") {
    const configurations = kinematics.configurations || {};
    if (!(pose in configurations)) throw new Error(`the document has no configuration '${pose}'`);
    given = configurations[pose];
    where = `configuration '${pose}'`;
  } else if (pose) {
    given = pose;
  }
  const controls = {};
  for (const [label, value] of Object.entries(given)) {
    const pair = pairs.get(label);
    if (!pair && Object.hasOwn(couplings, label)) { controls[label] = value; continue; }
    if (!pair) throw new Error(`${where} names no joint '${label}'`);
    const unposable = xbfUnposable(kinematics).get(label);
    if (unposable) throw new Error(`${where}: joint '${label}' cannot be posed: ${unposable}`);
    if (coupled.has(label) && typeof pose !== "string") {
      throw new Error(`${where}: joint '${label}' moves only with its coupling '${coupled.get(label)}'; set '${coupled.get(label)}'`);
    }
    values[label] = checked(pair, asValues(value), where);
  }
  Object.assign(values, coupledValues(kinematics, controls, given, where));
  return values;
}

/**
 * Each link's placement at `values`: the ground where the document places it, every other link
 * by its pairs from the ground down. A mechanism whose pairs close a loop has no pose.
 * @returns {number[][]} 4x4, column-major, by link.
 */
export function xbfLinkPlacements(kinematics, values) {
  if (!kinematics.links.length) return [];
  const found = kinematics.links.map(() => null);
  found[kinematics.ground] = kinematics.links[kinematics.ground].matrix;
  let pending = kinematics.pairs.filter(pair => pair.frames);
  for (let progress = true; pending.length && progress;) {
    progress = false;
    pending = pending.filter((pair) => {
      const [first, second] = pair.links;
      const value = values[pair.label] || (kinematics.asBuilt[pair.label] != null ? asValues(kinematics.asBuilt[pair.label]) : null);
      // A pair with no value holds its two links as they stand as built.
      const [one, two] = !value ? [invert(kinematics.links[first].matrix), invert(kinematics.links[second].matrix)] : pair.frames;
      const moved = !value ? [...IDENTITY] : xbfPairMotion(pair.type, value);
      if (found[first] && !found[second]) found[second] = multiply(multiply(multiply(found[first], one), moved), invert(two));
      else if (found[second] && !found[first]) found[first] = multiply(multiply(multiply(found[second], two), invert(moved)), invert(one));
      else if (!found[first]) return true;
      progress = true;
      return false;
    });
  }
  return found.map((matrix, at) => matrix || kinematics.links[at].matrix);
}

/**
 * Every instance's world matrix (column-major) with the mechanism at `values`: each link's
 * placement at them over its placement at the values the instances stand at now (the structure's
 * `kinematics.pose`, where the engine served it posed, else as built), applied to its instances.
 */
export function xbfPosedMatrices(structure, values) {
  const kinematics = xbfKinematics(structure);
  const matrices = structure.instances.map(instance => instance.matrix);
  if (!kinematics) return matrices;
  const reference = Object.fromEntries(Object.entries({ ...kinematics.asBuilt, ...(kinematics.pose?.values || {}) })
    .map(([label, value]) => [label, asValues(value)]));
  const now = xbfLinkPlacements(kinematics, values);
  const then = xbfLinkPlacements(kinematics, reference);
  kinematics.links.forEach((link, at) => {
    const delta = multiply(now[at], invert(then[at]));
    if (delta.every((value, i) => Math.abs(value - IDENTITY[i]) < 1e-12)) return;
    for (const index of link.instances) matrices[index] = multiply(delta, matrices[index]);
  });
  return matrices;
}

/**
 * What a Position panel drives: one control per value of every posable pair no coupling drives,
 * within its limits (an unbounded side spans one turn or 100 mm from the other).
 * @returns {{ id: string, pair: string, index: number, label: string, unit: string, min: number, max: number }[]}
 */
export function xbfPoseControls(kinematics) {
  const unposable = xbfUnposable(kinematics);
  const coupled = xbfCoupledPairs(kinematics);
  const controls = [];
  for (const pair of kinematics?.pairs || []) {
    if (unposable.has(pair.label) || coupled.has(pair.label)) continue;
    const names = VALUE_NAMES[pair.type];
    for (let index = 0; index < XBF_PAIR_VALUES[pair.type]; index += 1) {
      const unit = pair.units?.[index] || "deg";
      const span = unit === "deg" ? 360 : 100;
      let [min, max] = pair.limits?.[index] || [null, null];
      if (min == null && max == null) [min, max] = unit === "deg" ? [-180, 180] : [-50, 50];
      else if (min == null) min = max - span;
      else if (max == null) max = min + span;
      controls.push({ id: names ? `${pair.label}.${names[index]}` : pair.label, pair: pair.label, index,
        label: names ? `${pair.label} ${names[index]}` : pair.label, unit, min, max });
    }
  }
  return controls;
}

/**
 * The couplings a Position panel drives: one control per coupling whose joints can all be posed,
 * over its range (0 as built), with the pairs it drives. A side nothing bounds spans what moves
 * its first value one turn or 100 mm from the other (half each way where neither is bounded).
 * @returns {{ id: string, coupling: string, label: string, unit: string, min: number, max: number, pairs: string[] }[]}
 */
export function xbfCouplingControls(kinematics) {
  const unposable = xbfUnposable(kinematics);
  const pairs = new Map((kinematics?.pairs || []).map(pair => [pair.label, pair]));
  return Object.entries(xbfCouplings(kinematics)).filter(([name]) => !unposable.has(name)).map(([name, coupling]) => {
    const [label, index, ratio] = (coupling.terms || []).find(([, , r]) => r) || [null, 0, 1];
    const span = ((pairs.get(label)?.units?.[index] || "deg") === "deg" ? 360 : 100) / Math.abs(ratio || 1);
    let [min, max] = coupling.range || [null, null];
    if (min == null && max == null) [min, max] = [-span / 2, span / 2];
    else if (min == null) min = Number(max) - span;
    else if (max == null) max = Number(min) + span;
    return { id: `coupling:${name}`, coupling: name, label: name, unit: "", min: Number(min), max: Number(max),
      pairs: [...new Set((coupling.terms || []).map(([pair]) => pair))] };
  });
}

// A coupled value without coupling `name`'s share: its as-built value plus every other coupling's
// ratio times its value (`couplings`).
function restOf(kinematics, couplings, name, label, index) {
  let found = asValues(kinematics.asBuilt?.[label] ?? [])[index] ?? 0;
  for (const [other, coupling] of Object.entries(xbfCouplings(kinematics))) {
    if (other === name) continue;
    for (const [at, value, ratio] of coupling.terms || []) if (at === label && value === index) found += ratio * (Number(couplings?.[other]) || 0);
  }
  return found;
}

/**
 * Every pair's values, and every coupling's, once coupling `name` is set to `next`: each joint it
 * drives at its as-built values plus every coupling's ratio times its value (couplings sharing a
 * joint add), `next` held within the coupling's range and where each such joint keeps within its
 * limits; the other joints as `values` has them. Null for no number, or no value that keeps them.
 * @returns {{ values: Record<string, number[]>, couplings: Record<string, number> } | null}
 */
export function xbfCouplingWrite(kinematics, values, couplings, name, next) {
  const coupling = xbfCouplings(kinematics)[name];
  const wanted = Number(next);
  if (!coupling || !Number.isFinite(wanted)) return null;
  const pairs = new Map((kinematics.pairs || []).map(pair => [pair.label, pair]));
  let [lower, upper] = rangeOf(coupling);
  for (const [label, index, ratio] of coupling.terms) {
    if (!ratio) continue;
    const rest = restOf(kinematics, couplings, name, label, index);
    const [low, high] = pairs.get(label)?.limits?.[index] || [null, null];
    const fromLow = low == null ? null : (low - rest) / ratio, fromHigh = high == null ? null : (high - rest) / ratio;
    if (ratio > 0) {
      if (fromLow != null) lower = Math.max(lower, fromLow);
      if (fromHigh != null) upper = Math.min(upper, fromHigh);
    } else {
      if (fromLow != null) upper = Math.min(upper, fromLow);
      if (fromHigh != null) lower = Math.max(lower, fromHigh);
    }
  }
  if (lower > upper) return null;
  const value = Math.min(Math.max(wanted, lower), upper);
  const written = { ...values };
  for (const [label, index, ratio] of coupling.terms) {
    const row = [...(written[label] || asValues(kinematics.asBuilt?.[label] ?? []))];
    row[index] = restOf(kinematics, couplings, name, label, index) + ratio * value;
    written[label] = row;
  }
  return { values: written, couplings: { ...couplings, [name]: value } };
}

/**
 * Where `values` stand on each coupling: the value at which every joint it drives is at its
 * as-built value plus its ratio times it, within the coupling's range; 0 for a pose off its line.
 * @returns {Record<string, number>}
 */
export function xbfCouplingValues(kinematics, values) {
  const found = {};
  for (const [name, coupling] of Object.entries(xbfCouplings(kinematics))) {
    let at = null, on = true;
    for (const [label, index, ratio] of coupling.terms || []) {
      if (!ratio) continue;
      const value = (Number(values?.[label]?.[index]) - asValues(kinematics.asBuilt?.[label] ?? [])[index]) / ratio;
      if (!Number.isFinite(value) || (at != null && Math.abs(value - at) > 1e-6 * Math.max(1, Math.abs(at)))) { on = false; break; }
      if (at == null) at = value;
    }
    const [lower, upper] = rangeOf(coupling);
    found[name] = on && at != null ? Math.min(Math.max(at, lower), upper) : 0;
  }
  return found;
}

/** Whether two sets of pair values are the same pose. */
export function xbfSamePose(left, right) {
  const labels = new Set([...Object.keys(left || {}), ...Object.keys(right || {})]);
  for (const label of labels) {
    const a = left?.[label] || [], b = right?.[label] || [];
    if (a.length !== b.length || a.some((value, at) => Math.abs(value - b[at]) > 1e-6)) return false;
  }
  return true;
}
