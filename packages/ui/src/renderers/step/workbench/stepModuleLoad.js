import { normalizeStepModuleParameterValues } from "@text-to-cad/core/common/stepModule.js";

const canonical = value => (Array.isArray(value) ? value.map(canonical)
  : value && typeof value === "object" ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]))
    : value);

// What a STEP's pose is made of: the parameters its joints are driven by (each one's id, kind,
// range, default and unit) and its named poses, as one comparable string ("" for nothing to pose).
// A rebuild whose sidecar declares the same keeps the pose in hand; one that declares anything
// else starts at the new defaults, since a pose is never fitted onto joints that changed. The
// definition's `url` is not part of it: a rebuild writes the sidecar again under a new version.
export function stepPoseLogic(definition) {
  return definition ? JSON.stringify(canonical([definition.parameters || [], definition.manifest?.poses || {}])) : "";
}

// What the Position section commits once a model's sidecar has resolved.
//
// A NULL definition is a documented outcome, not a failure: a sidecar with no
// `kinematics` section compiles to null ("nothing to pose", see
// @text-to-cad/core/common/kinematicsModule). The sidecar URL is set whenever a sidecar
// exists at all, and an ANIMATION-ONLY model has one, so this resolves for a
// model that will never have a pose. Reading the definition's defaults there
// threw a TypeError that the load effect's own .catch() turned into an error
// row rendered inside a Position section which should not have existed — the
// section appeared only because the error made it non-empty.
//
// So null resolves to a ready state with no pose values, and the section is
// then absent on its own terms: a model with no mates has no Position section,
// exactly as a model with no clips has no playbar in preview.
export function resolveStepModuleLoad({ url = "", definition = null, restored = null } = {}) {
  return {
    loadState: {
      url,
      status: "ready",
      error: "",
      definition: definition || null
    },
    parameterValues: normalizeStepModuleParameterValues(
      definition,
      restored?.parameterValues || definition?.defaultParameterValues
    )
  };
}
