// The unit a family's file measures in, against the coordinates its scene is drawn in. A STEP
// is drawn in its millimetres. A GLB is drawn in millimetres too, from glTF's metres (its root
// scales by 1000: `glbMeshData.js`); a robot in its own metres (URDF and SDF, REP 103); a 3MF
// in the unit its model declares, unscaled; an STL in its bare numbers, which name no unit.
//
// Every number a person reads or writes about such a scene is in the FILE's unit: a measured
// length, and where Clip's plane stands (`clip.at`), in the viewer and in a snapshot alike.

/**
 * @typedef {{ unit: string, perWorld: number }} SceneUnits
 *   `unit`: the file's unit as it is written ("m", "mm", "in"…), or "" for a format that names
 *   none (STL). `perWorld`: how many of that unit one scene coordinate is.
 */

/** @type {SceneUnits} */
export const GLB_SCENE_UNITS = Object.freeze({ unit: "m", perWorld: 0.001 });
/** @type {SceneUnits} */
export const ROBOT_SCENE_UNITS = Object.freeze({ unit: "m", perWorld: 1 });
/** @type {SceneUnits} */
export const UNITLESS_SCENE_UNITS = Object.freeze({ unit: "", perWorld: 1 });

// 3MF Core Specification, `model@unit` (ST_Unit), and how each is written; millimeter when absent.
const THREE_MF_UNITS = Object.freeze({ micron: "µm", millimeter: "mm", centimeter: "cm", inch: "in", foot: "ft", meter: "m" });

/** A 3MF's declared unit (`<model unit="…">`) as a scene's: its coordinates are in that unit. @returns {SceneUnits} */
export function threeMfSceneUnits(declared) {
  const unit = THREE_MF_UNITS[String(declared || "millimeter").trim().toLowerCase()];
  if (!unit) throw new Error(`3MF model unit "${declared}" is not one the 3MF specification defines (${Object.keys(THREE_MF_UNITS).join(", ")})`);
  return Object.freeze({ unit, perWorld: 1 });
}

const scale = (value, factor) => (typeof value?.length === "number" ? Array.from(value, v => Number(v) * factor) : value);

/** `bounds` (scene coordinates) in the file's unit. */
export function boundsInUnits(bounds, units) {
  const perWorld = units?.perWorld ?? 1;
  return bounds && perWorld !== 1 ? { min: scale(bounds.min, perWorld), max: scale(bounds.max, perWorld) } : bounds;
}

/** Clip's settings (`at` in the file's unit) as the scene's coordinates say them. */
export function clipInWorld(clip, units) {
  const perWorld = units?.perWorld ?? 1;
  return clip && typeof clip.at === "number" && perWorld !== 1 ? { ...clip, at: clip.at / perWorld } : clip;
}
