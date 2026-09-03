import { normalizeStepModuleParameterValues } from "cadgen-js/common/stepModule.js";

// What the Kinematics tab commits once a model's sidecar has resolved.
//
// A NULL definition is a documented outcome, not a failure: a sidecar with no
// `kinematics` section compiles to null ("nothing to pose", see
// cadgen-js/common/kinematicsModule). The sidecar URL is set whenever a sidecar
// exists at all, and an ANIMATION-ONLY model has one, so this resolves for a
// model that will never have a pose. Reading the definition's defaults there
// threw a TypeError that the load effect's own .catch() turned into an error
// row rendered inside a Kinematics tab which should not have existed — the tab
// appeared only because the error made it non-empty.
//
// So null resolves to a ready state with no pose values, and the tab is then
// absent on its own terms: a model with no mates has no Kinematics tab, exactly
// as a model with no clips has no Animation tab.
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
    ),
    enabled: restored ? restored.enabled !== false : true
  };
}
