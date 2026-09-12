// Back-drive routing for the POSE tab's sliders.
//
// A coupling gears its member DOFs linearly and ADDITIVELY, and the state the
// viewer holds stays exactly that: plain {dof: value}, member terms and
// coupling terms side by side. What this module adds is the other direction —
// a member the coupling drives is shown at its EFFECTIVE value (own + ratio x
// coupling) and, when dragged, writes THROUGH the coupling instead of into
// itself. Sliding the sun of a gear train turns the whole train, because the
// slider moves the train's virtual DOF.
//
// Nothing new is persisted: the write lands on the coupling's existing DOF, the
// member's own term is left exactly as a preset or --kinematics JSON set it,
// and a member geared by two couplings stays independent (see
// kinematicsDrivenDofs — an underdetermined inverse is refused, not guessed).

import {
  couplingValueForDrivenDof,
  effectiveDofValues,
  kinematicsDrivenDofs
} from "@hardcore/core/common/kinematicsRuntime.js";

function kinematicsBlock(definition) {
  const block = definition?.manifest?.kinematics;
  return block && typeof block === "object" && !Array.isArray(block) ? block : null;
}

/** { [dofId]: { coupling, ratio, limits } } for this pose definition — empty
 * for authored modules and for models with no couplings. */
export function poseDrivenDofs(definition) {
  const block = kinematicsBlock(definition);
  return block ? kinematicsDrivenDofs(block) : {};
}

/** The values the sliders SHOW: every mate DOF's effective value. Empty when
 * there is nothing geared, in which case the raw parameter values are already
 * what a slider should display. */
export function poseDisplayValues(definition, values) {
  const block = kinematicsBlock(definition);
  if (!block) {
    return {};
  }
  return effectiveDofValues(block, values);
}

/** What a slider shows for one DOF: the effective value for a driven member,
 * the stored value otherwise. */
export function poseControlDisplayValue({ driven, displayValues, values, parameter }) {
  const id = parameter?.id;
  const driver = driven?.[id];
  if (driver && Number.isFinite(Number(displayValues?.[id]))) {
    return Number(displayValues[id]);
  }
  return values?.[id] ?? parameter?.defaultValue;
}

/** Where a slider's input goes: {id, value}. For a driven member that is the
 * COUPLING's DOF, solved so the member's effective value hits the target while
 * its own term stays put; for everything else it is the DOF itself. */
export function poseControlWrite({ driven, values, parameterId, value }) {
  const id = String(parameterId || "");
  const driver = driven?.[id];
  if (!driver) {
    return { id, value };
  }
  const ownValue = Number(values?.[id]) || 0;
  const couplingValue = couplingValueForDrivenDof(driver, value, ownValue);
  if (couplingValue === null) {
    return { id, value };
  }
  return { id: driver.coupling, value: couplingValue };
}
