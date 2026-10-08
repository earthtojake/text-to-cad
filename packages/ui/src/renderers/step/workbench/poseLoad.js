import { normalizeControlValues } from "@text-to-cad/core/common/articulation.js";

const canonical = value => (Array.isArray(value) ? value.map(canonical)
  : value && typeof value === "object" ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]))
    : value);

// What a STEP's pose is made of: the controls its joints are driven by (each one's id, unit,
// range and rest value) and its named poses, as one comparable string ("" for nothing to pose).
// A rebuild whose articulation declares the same keeps the pose in hand; one that declares
// anything else starts at the new defaults, since a pose is never fitted onto joints that
// changed. The definition's `url` is not part of it: a rebuild writes the sidecar again under a
// new version.
export function stepPoseLogic(definition) {
  const articulation = definition?.articulation;
  return articulation ? JSON.stringify(canonical([articulation.controls || [], articulation.poses || {}])) : "";
}

// What the Position section commits once a model's catalog entry has resolved.
//
// A NULL definition is a documented outcome, not a failure: an entry with no articulation
// (an animation-only model has a sidecar, and so a load, but nothing to pose) resolves to a
// ready state with no pose values, and the section is then absent on its own terms: a model
// with no mates has no Position section, exactly as a model with no clips has no playbar in
// preview.
export function resolvePoseLoad({ url = "", definition = null, restored = null } = {}) {
  return {
    loadState: {
      url,
      status: "ready",
      error: "",
      definition: definition || null
    },
    parameterValues: definition
      ? normalizeControlValues(definition.articulation, restored?.parameterValues || null)
      : {}
  };
}
