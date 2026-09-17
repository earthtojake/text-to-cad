// How a model MOVES between two poses, for every kind of model that has poses.
//
// Applying a named pose is a jump in the data and a motion on screen: reading a
// mechanism means watching which DOF turns which way, and a snap answers nothing. The
// robot sheet already tweened; STEP did not, so the same act looked like two different
// features. This is the one setting both read, and it is a PREFERENCE — the person who
// wants the snap wants it in every file, not once per file.
//
// Off means off, not "very fast": a zero duration writes the target values in the same
// frame, so nothing has to interpolate through a pose nobody asked to see.

import { useCallback, useEffect, useRef, useMemo } from "react";
import {
  URDF_JOINT_ANIMATION_DURATION_MS,
  easeUrdfJointAnimation
} from "@hardcore/core/lib/urdf/jointAnimation.js";

export const POSE_TRANSITION_STORAGE_KEY = "cad-viewer:pose-transition:v1";

// The robot sheet's tween, which is the motion this setting generalizes -- taken from
// it rather than restated, so one number stays one number.
export const POSE_TRANSITION_BASE_MS = URDF_JOINT_ANIMATION_DURATION_MS;

export const POSE_TRANSITION_SPEEDS = Object.freeze([
  { value: "0.5", label: "0.5×" },
  { value: "1", label: "1×" },
  { value: "2", label: "2×" },
  { value: "4", label: "4×" }
]);

export const DEFAULT_POSE_TRANSITION = Object.freeze({ animate: true, speed: 1 });

function normalizeSpeed(value) {
  const speed = Number(value);
  if (!Number.isFinite(speed) || speed <= 0) {
    return DEFAULT_POSE_TRANSITION.speed;
  }
  // Only the offered speeds: a stored 0.001 would read as "animation is broken".
  const allowed = POSE_TRANSITION_SPEEDS.map((option) => Number(option.value));
  return allowed.includes(speed) ? speed : DEFAULT_POSE_TRANSITION.speed;
}

export function normalizePoseTransition(value) {
  return {
    animate: value?.animate !== false,
    speed: normalizeSpeed(value?.speed)
  };
}

// The duration one transition should take, in milliseconds. 0 means "write it now".
export function poseTransitionDurationMs(settings, baseMs = POSE_TRANSITION_BASE_MS) {
  const normalized = normalizePoseTransition(settings);
  if (!normalized.animate) {
    return 0;
  }
  const base = Number(baseMs);
  return Math.max(Math.round((Number.isFinite(base) && base > 0 ? base : POSE_TRANSITION_BASE_MS) / normalized.speed), 1);
}

export function readPoseTransition(storage) {
  try {
    const raw = storage?.getItem(POSE_TRANSITION_STORAGE_KEY);
    return normalizePoseTransition(raw ? JSON.parse(raw) : null);
  } catch {
    // A blocked or corrupt store is not a reason to stop animating.
    return { ...DEFAULT_POSE_TRANSITION };
  }
}

export function writePoseTransition(storage, settings) {
  try {
    storage?.setItem(POSE_TRANSITION_STORAGE_KEY, JSON.stringify(normalizePoseTransition(settings)));
  } catch {
    // Preference only: losing it costs the next session a default, nothing more.
  }
}

export function usePoseTransition(value, onChange) {
  const settings = useMemo(() => normalizePoseTransition(value), [value]);
  const setAnimate = useCallback((animate) => {
    onChange?.(normalizePoseTransition({ ...settings, animate: animate !== false }));
  }, [settings, onChange]);
  const setSpeed = useCallback((speed) => {
    onChange?.(normalizePoseTransition({ ...settings, speed }));
  }, [settings, onChange]);
  return {
    animate: settings.animate,
    speed: settings.speed,
    durationMs: poseTransitionDurationMs(settings),
    setAnimate,
    setSpeed
  };
}


// Walk a map of NUMBERS from start to target over durationMs, calling onFrame with the
// whole map each frame and exactly once with the target at the end.
//
// Values that are not numbers on both sides cannot be walked -- a boolean or an enum has
// no halfway -- so they are written on the first frame and left alone. Returns a cancel
// function; calling it stops the walk without writing the target, which is what a second
// pose click needs so two transitions do not fight over the same values.
export function animatePoseValues({ start, target, durationMs, onFrame }) {
  const finalValues = { ...target };
  const canAnimate = durationMs > 0 && typeof requestAnimationFrame === "function";
  const tweened = canAnimate
    ? Object.keys(finalValues).filter((key) => (
      typeof finalValues[key] === "number" && typeof start?.[key] === "number" && finalValues[key] !== start[key]
    ))
    : [];
  if (!tweened.length) {
    onFrame(finalValues);
    return () => {};
  }
  let cancelled = false;
  let startedAtMs = null;
  const step = (timestamp) => {
    if (cancelled) {
      return;
    }
    const now = Number.isFinite(timestamp) ? timestamp : performance.now();
    if (startedAtMs === null) {
      startedAtMs = now;
    }
    const progress = Math.min(Math.max(now - startedAtMs, 0) / durationMs, 1);
    if (progress >= 1) {
      onFrame(finalValues);
      return;
    }
    const eased = easeUrdfJointAnimation(progress);
    const frame = { ...finalValues };
    for (const key of tweened) {
      frame[key] = start[key] + (finalValues[key] - start[key]) * eased;
    }
    onFrame(frame);
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
  return () => { cancelled = true; };
}

// One transition at a time per surface: starting a new one cancels whatever was walking.
export function usePoseValueAnimation() {
  const cancelRef = useRef(null);
  const cancel = useCallback(() => {
    cancelRef.current?.();
    cancelRef.current = null;
  }, []);
  useEffect(() => cancel, [cancel]);
  const run = useCallback((options) => {
    cancelRef.current?.();
    cancelRef.current = animatePoseValues(options);
  }, []);
  return { run, cancel };
}
