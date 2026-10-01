const MAX_ORBIT_DELTA_SECONDS = 1;
export const PREVIEW_ORBIT_SECONDS_PER_TURN = 60;
export const PREVIEW_AUTO_ROTATE_SPEED = 60 / PREVIEW_ORBIT_SECONDS_PER_TURN;

function finiteTimestamp(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function orbitControlsDeltaSeconds(timestamp, previousTimestamp) {
  const current = finiteTimestamp(timestamp);
  const previous = finiteTimestamp(previousTimestamp);
  if (current === null || previous === null || previous <= 0 || current <= previous) {
    return null;
  }
  return Math.min((current - previous) / 1000, MAX_ORBIT_DELTA_SECONDS);
}

export function updateOrbitControls(controls, timestamp, state) {
  if (!controls || typeof controls.update !== "function") {
    return false;
  }

  if (!controls.autoRotate) {
    if (state) {
      state.orbitControlsLastTimestamp = 0;
    }
    return controls.update();
  }

  const current = finiteTimestamp(timestamp);
  const deltaSeconds = orbitControlsDeltaSeconds(current, state?.orbitControlsLastTimestamp);
  if (state) {
    state.orbitControlsLastTimestamp = current ?? 0;
  }
  return deltaSeconds === null ? controls.update() : controls.update(deltaSeconds);
}

/**
 * Drop the momentum a drag left in damped OrbitControls, so the next `update()` keeps the
 * camera where it was just PUT. With `enableDamping` on, `update()` keeps adding the
 * last drag's spherical delta, pan and dolly for a few hundred milliseconds; a camera
 * handed to the viewport in that window drifts several units off what was asked.
 * The fields are three's own (`_sphericalDelta`, `_panOffset`, `_scale`).
 */
export function stopOrbitMomentum(controls) {
  if (!controls) return false;
  controls._sphericalDelta?.set?.(0, 0, 0);
  controls._panOffset?.set?.(0, 0, 0);
  if ("_scale" in controls) controls._scale = 1;
  return true;
}
