// A cadgen engine document's motions as a page plays them: the structure's `kinematics.motions`
// (`cadgen/engine/mechanism.py`, `block`), each AP242's INTERPOLATED_CONFIGURATION_SEQUENCE: its
// keys' times (`t_parameter`), their states (a configuration's name, or pair values, a coupling's
// value already made its joints' by the engine) and one interpolation between them (`ease`):
// `linear` (`linear_interpolation_type`, constant speed) or `cubic`
// (`synchronous_interpolation_type`: each step eased in and out, every pair arriving at every key
// together). A function motion is its stored samples, `linear` between them. The last segment is
// discontinuous: a motion is a finite clip, which a player repeats.
//
// `values(t)` is the engine's `mechanism.Timeline.values`, the GLB baker's truth
// (`export/motion.py`), value for value: each key resolved to every pair's values (the rest as
// built), the moving ones interpolated per value, each held within its pair's limits. A coupling's
// joints move by their keys together and linearly in the step's progress, so between keys they
// keep their coupling's ratios. The page poses the values through its forward kinematics
// (`xbfKinematics.js`).

const asValues = value => (Array.isArray(value) ? value.map(Number) : [Number(value)]);

/**
 * Each motion of a document's mechanism, in the block's order: its name, its duration (seconds:
 * its last key's time) and its interpolation.
 * @returns {{ name: string, duration: number, ease: "linear" | "cubic" }[]}
 */
export function xbfMotions(kinematics) {
  const found = kinematics?.motions;
  if (!found || typeof found !== "object" || Array.isArray(found)) return [];
  return Object.entries(found).filter(([, motion]) => Array.isArray(motion?.keys) && motion.keys.length)
    .map(([name, motion]) => ({ name, duration: Number(motion.duration ?? motion.keys.at(-1).t) || 0,
      ease: motion.ease === "linear" ? "linear" : "cubic" }));
}

/** How far a step is along at `s` (0..1) under `ease`: linear, or synchronous (eased in and out). */
export function xbfMotionEase(ease, s) {
  return ease === "linear" ? s : s * s * (3 - 2 * s);
}

/**
 * One motion over time: `values(t)` is every pair's values at `t` seconds of its clip (before 0
 * its first key's, past its duration its last key's), every pair it does not move as built.
 * @returns {{ name: string, duration: number, ease: string, times: number[], labels: string[],
 *   values(t: number): Record<string, number[]> }}
 */
export function xbfMotionTimeline(kinematics, name) {
  const entry = kinematics?.motions?.[name];
  if (!entry || !Array.isArray(entry.keys) || !entry.keys.length) throw new Error(`the document has no motion '${name}'`);
  const ease = entry.ease === "linear" ? "linear" : "cubic";
  const asBuilt = Object.fromEntries(Object.entries(kinematics.asBuilt || {}).map(([label, value]) => [label, asValues(value)]));
  const configurations = kinematics.configurations || {};
  const pairs = new Map((kinematics.pairs || []).map(pair => [pair.label, pair]));
  const moving = new Set();
  const poses = entry.keys.map((key) => {
    const given = key.configuration != null ? configurations[key.configuration] : key.values;
    if (!given) throw new Error(`motion '${name}' names no configuration '${key.configuration}'`);
    for (const label of Object.keys(given)) moving.add(label);
    return { ...asBuilt, ...Object.fromEntries(Object.entries(given).map(([label, value]) => [label, asValues(value)])) };
  });
  const labels = [...moving].sort();
  const sizes = labels.map(label => poses[0][label]?.length || 1);
  const rows = poses.map(pose => labels.flatMap((label, at) => pose[label] || new Array(sizes[at]).fill(0)));
  const limits = labels.flatMap((label, at) => Array.from({ length: sizes[at] }, (_, index) => pairs.get(label)?.limits?.[index] || [null, null]));
  const lower = limits.map(([low]) => (low == null ? -Infinity : Number(low)));
  const upper = limits.map(([, high]) => (high == null ? Infinity : Number(high)));
  const times = entry.keys.map(key => Number(key.t));
  const last = times.length - 1;

  /** The moving values at `t`, flat in `labels`' order. */
  function flat(t) {
    if (!(t > times[0])) return rows[0];
    if (t >= times[last]) return rows[last];
    // The step `t` is in: from the last key at or before it.
    let lo = 0, hi = last;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (times[mid] <= t) lo = mid; else hi = mid; }
    const s = xbfMotionEase(ease, (t - times[lo]) / (times[lo + 1] - times[lo]));
    return rows[lo].map((value, at) => value + s * (rows[lo + 1][at] - value));
  }

  return {
    name, ease, times, labels,
    duration: Number(entry.duration ?? times[last]) || 0,
    values(t) {
      const found = { ...asBuilt };
      const row = flat(Number(t) || 0);
      let at = 0;
      labels.forEach((label, index) => {
        found[label] = row.slice(at, at + sizes[index]).map((value, k) => Math.min(Math.max(value, lower[at + k]), upper[at + k]));
        at += sizes[index];
      });
      return found;
    }
  };
}
