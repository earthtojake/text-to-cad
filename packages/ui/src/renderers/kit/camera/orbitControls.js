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
