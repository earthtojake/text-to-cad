/**
 * Drop impact (lite): a part dropped onto a rigid floor, simulated through time, Tier 3. Its result
 * is a series of times after first contact (`39.6 µs`), evenly spaced plus the moment of the peak
 * stress, each frame's stress and displacement (relative to the part's travel) its own, with the
 * envelopes over the run beside them, and the plastic strain left at the end where plasticity was
 * given. Its verdict judges the peak stress, the peak g the floor gives it ("Peak g") and the
 * permanent strain, and choosing a check jumps the scrubber to when it peaked (`at.frame`); its
 * takeaway leads with "Rigid floor · " (the tier's limit word). A drop's stress grows with the
 * impact speed, not in step with the drop height, so there is no load control. What you see opens
 * on the Time scrubber, on the peak (the series' default), the field and the deformation; Play runs
 * the frames over three seconds. Its setup says how it was dropped ("1 m drop onto a rigid floor",
 * the way it falls and any friction its hint, the faces that landed under it) and what it is made of.
 */
import { plainNumber } from "../numbers.js";
import { droppedRows, forceDirection, madeOfRows } from "../setup.js";
import { PLAY, timeFieldAndDeformation } from "./transient.js";

export { PLAY };

/** The drop as the file echoes it: its friction and direction ride on it, which `readStudy` keeps no copy of. */
const rawDrop = (result) => result?.mesh?.userData?.study?.drop || {};

/** How it falls and slides, in words: "Falling down, no friction", "Falling along +X, friction 0.3". */
export function fallWords(result) {
  const drop = result.study.drop;
  const raw = rawDrop(result);
  const way = drop?.direction ? forceDirection(drop.direction) : "";
  const friction = Number(raw.friction) > 0 ? `friction ${plainNumber(Number(raw.friction))}` : "no friction";
  return [way ? `Falling ${way}` : "", friction].filter(Boolean).join(", ");
}

/**
 * Study's "Dropped" for an impact: one row, "1 m drop onto a rigid floor", how it falls and slides
 * its hint, the faces that met the floor under it; chosen, it carries the drop into a prompt.
 */
export function impactDroppedRows(result) {
  const hint = fallWords(result);
  return droppedRows(result).map((group) => ({
    ...group,
    children: group.children.map((row) => {
      const label = `${row.label} onto a rigid floor`;
      const summary = row.summary ? row.summary.replace(row.label, label) : row.summary;
      return { ...row, label, ...(hint ? { hint } : {}), ...(summary ? { summary } : {}) };
    }),
  }));
}

export default Object.freeze({
  name: "impact",
  tier: 3,
  word: "Drop impact",
  noun: "this drop",
  family: null,
  estimate: false,
  scalesWithLoad: false,
  checks: Object.freeze(["stress", "acceleration", "plastic_strain"]),
  checkLabels: Object.freeze({ acceleration: "Peak g" }),
  defaultControls: timeFieldAndDeformation,
  setupGroups: Object.freeze([impactDroppedRows, madeOfRows]),
  routine: (result) => (result?.series ? PLAY : null),
  markers: Object.freeze(["drop", "rigid_plane"]),
  displayTitle: "Drop and floor",
  limitWord: "Rigid floor",
});
