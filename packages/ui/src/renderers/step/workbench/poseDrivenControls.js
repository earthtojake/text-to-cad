// Back-drive routing for the Position panel's sliders.
//
// A coupling gears its member controls linearly and ADDITIVELY, and the state the
// viewer holds stays exactly that: plain {control: value}, member terms and coupling
// terms side by side. What this module adds is the other direction — a member the
// articulation says a coupling drives is shown at its joint row's value (own + ratio x
// coupling) and, when dragged, writes THROUGH the coupling instead of into itself.
// Sliding the sun of a gear train turns the whole train, because the slider moves the
// train's virtual control.
//
// Every decision is cadgen's (`articulation.handles`: which control a row's gesture
// writes, with what weight); this module only routes a slider to its handle and the
// player solves the write (`core/common/articulation.js`).

import {
  articulationHandles,
  controlWriteForHandle,
  handleForControl,
  handleRowValue
} from "@text-to-cad/core/common/articulation.js";

function articulationOf(definition) {
  return definition?.articulation || null;
}

/** { [controlId]: handle } for every control a coupling drives — a handle whose write
 * lands on another control. Empty for models with no couplings. */
export function poseDrivenDofs(definition) {
  const driven = {};
  for (const handle of articulationHandles(articulationOf(definition))) {
    if (handle.control && handle.control !== handle.id) driven[handle.id] = handle;
  }
  return driven;
}

/** The values the sliders SHOW: every handle's joint row value. Empty when there is
 * nothing to pose, in which case the raw values are already what a slider displays. */
export function poseDisplayValues(definition, values) {
  const articulation = articulationOf(definition);
  return Object.fromEntries(articulationHandles(articulation).map((handle) => [
    handle.id, handleRowValue(articulation, handle, values)
  ]));
}

/** What a slider shows for one control: its row's value for a driven member, the stored
 * value otherwise. */
export function poseControlDisplayValue({ driven, displayValues, values, parameter }) {
  const id = parameter?.id;
  if (driven?.[id] && Number.isFinite(Number(displayValues?.[id]))) {
    return Number(displayValues[id]);
  }
  return values?.[id] ?? parameter?.default;
}

/** Where a slider's input goes: {id, value}. For a driven member that is the COUPLING's
 * control, solved so the member's row hits the target while its own term stays put; for
 * everything else it is the control itself. */
export function poseControlWrite({ definition, values, parameterId, value }) {
  const id = String(parameterId || "");
  const articulation = articulationOf(definition);
  const handle = handleForControl(articulation, id);
  if (!handle || handle.control === id) {
    return { id, value };
  }
  return controlWriteForHandle(articulation, handle, values, value) || { id, value };
}
