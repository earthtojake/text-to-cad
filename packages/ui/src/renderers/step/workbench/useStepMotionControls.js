import { useCallback, useEffect, useRef } from "react";
import { advanceAnimationElapsed, animationClipDuration, animationNowMs,
  clampAnimationElapsed, clampAnimationSpeed, findAnimationClip, firstAnimationClipId,
  shouldPublishAnimationFrame } from "@hardcore/core/common/animationClock.js";
import { normalizeParameterValue, normalizeParameterValues } from "@hardcore/core/common/parameters.js";
import { poseValuesForPreset } from "../components/workbench/PoseControlsSection.js";
import { useAnimationClockStore } from "./animationClockStore.js";

// Single command boundary for STEP motion. Refs are published synchronously so
// queued playback callbacks cannot resurrect the previous motion owner.
export function useStepMotionControls({
  selectedStepModuleDefinition, selectedAnimationClips, selectedActiveAnimationClip,
  animationState, animationStateRef, setAnimationState, stepModuleParameterValuesRef,
  setStepModuleParameterValues, setAppliedStepPoseName, motionRevisionRef
}) {
  const { getAnimationClock, setAnimationClock, resetAnimationClock } = useAnimationClockStore();
  const writeParameters = useCallback((values) => {
    const current = stepModuleParameterValuesRef.current;
    // Scrubbing/speed edits must not reapply the kinematics tree on every event
    // after animation already owns an authored pose.
    if (current && Object.keys(current).length === Object.keys(values).length &&
      Object.keys(values).every(key => Object.is(current[key], values[key]))) return;
    stepModuleParameterValuesRef.current = values;
    setStepModuleParameterValues(values);
  }, [stepModuleParameterValuesRef, setStepModuleParameterValues]);
  const resetPosition = useCallback(() => {
    setAppliedStepPoseName("");
    writeParameters(normalizeParameterValues(selectedStepModuleDefinition,
      selectedStepModuleDefinition?.defaultParameterValues || {}));
  }, [selectedStepModuleDefinition, setAppliedStepPoseName, writeParameters]);
  // What Position had set when a routine took the pose. A routine plays from the model at rest,
  // so taking the pose puts Position's values aside rather than throwing them away; handing
  // the pose back (leaving Animate, or touching Position) puts them back first.
  const heldPositionRef = useRef(null);
  useEffect(() => { heldPositionRef.current = null; }, [selectedStepModuleDefinition]);
  // Handing the pose to Position stops the routine and rewinds its clock, and nothing more: the
  // transport preferences Animate's corner menu set (the routine, its speed, the loop) are the
  // person's, and a joint nudge or a trip to another tool keeps them for the next play.
  const activatePositionControls = useCallback(() => {
    motionRevisionRef.current += 1;
    const next = { ...animationStateRef.current, enabled: false, playing: false, elapsedSec: 0 };
    animationStateRef.current = next;
    setAnimationState(next);
    resetAnimationClock();
    const held = heldPositionRef.current;
    heldPositionRef.current = null;
    if (held) writeParameters(normalizeParameterValues(selectedStepModuleDefinition, held));
  }, [resetAnimationClock, selectedStepModuleDefinition, writeParameters]);
  const activateAnimationControls = useCallback(() => {
    motionRevisionRef.current += 1;
    heldPositionRef.current ||= { ...stepModuleParameterValuesRef.current };
    resetPosition();
  }, [resetPosition]);
  const resetMotion = useCallback(() => {
    activatePositionControls();
    resetPosition();
  }, [activatePositionControls, resetPosition]);
  const handleStepModuleParameterChange = useCallback((parameterId, value) => {
    const id = String(parameterId || "").trim();
    const parameter = selectedStepModuleDefinition?.parameterMap?.[id];
    if (!parameter) {
      return;
    }
    activatePositionControls();
    // Moving a DOF by hand leaves the named pose behind, so the dropdown stops claiming
    // it and goes back to reading the values (the robot's group state does the same).
    setAppliedStepPoseName("");
    writeParameters({ ...stepModuleParameterValuesRef.current, [id]: normalizeParameterValue(parameter, value) });
  }, [activatePositionControls, selectedStepModuleDefinition, writeParameters]);

  const applyStepModuleParameterValues = useCallback((values) => {
    if (!selectedStepModuleDefinition) return;
    activatePositionControls();
    setAppliedStepPoseName("");
    writeParameters(normalizeParameterValues(selectedStepModuleDefinition,
      { ...stepModuleParameterValuesRef.current, ...values }));
  }, [activatePositionControls, selectedStepModuleDefinition, writeParameters]);
  const handleResetStepModuleParameters = resetMotion;

  const handleApplyPose = useCallback((poseName) => {
    if (!selectedStepModuleDefinition?.manifest?.poses?.[poseName]) {
      return;
    }
    activatePositionControls();
    const nextParameterValues = normalizeParameterValues(
      selectedStepModuleDefinition,
      poseValuesForPreset(selectedStepModuleDefinition, poseName)
    );
    setAppliedStepPoseName(String(poseName || ""));
    // A pose is written like any other value: where the mechanism is from this
    // frame on. Motion over time belongs to the Animate tool.
    writeParameters(nextParameterValues);
  }, [activatePositionControls, selectedStepModuleDefinition, setAppliedStepPoseName, writeParameters]);

  // Every animation command claims ownership before publishing its frame.
  const handleAnimationClipSelect = useCallback((clipId) => {
    const clip = findAnimationClip(selectedAnimationClips, clipId);
    if (!clip) {
      // The picker only ever offers clips this model ships, so an id that does
      // not resolve is a stale event, not a request to idle the transport —
      // pausing is handled by the transport.
      return;
    }
    activateAnimationControls();
    const nextState = {
      ...animationStateRef.current,
      activeClipId: clip.id,
      enabled: true,
      playing: false,
      elapsedSec: 0,
      // The loop preference follows the newly-selected clip's own default.
      loopEnabled: clip.loop !== false
    };
    animationStateRef.current = nextState;
    setAnimationState(nextState);
    resetAnimationClock();
  }, [selectedAnimationClips, activateAnimationControls]);

  const handleAnimationPlayToggle = useCallback(() => {
    const currentState = animationStateRef.current;
    // A GUARD, not a UI path: once the clips compile the selection is always one
    // of them (the default picks clip 0, a restore falls back to clip 0, and the
    // picker only offers ids that resolve), and before they compile there are no
    // clips to find at all, so both lookups miss and this returns below. It
    // stays because Play doing nothing would be the silent failure — if a
    // selection ever went empty with clips in hand, Play should start the first
    // one rather than shrug.
    const clip = findAnimationClip(selectedAnimationClips, currentState.activeClipId)
      || findAnimationClip(selectedAnimationClips, firstAnimationClipId(selectedAnimationClips));
    if (!clip) {
      return;
    }
    activateAnimationControls();
    const duration = animationClipDuration(clip);
    if (currentState.playing) {
      const nextState = {
        ...currentState,
        activeClipId: clip.id,
        elapsedSec: clampAnimationElapsed(getAnimationClock(), duration),
        playing: false
      };
      animationStateRef.current = nextState;
      setAnimationState(nextState);
      return;
    }
    // Resuming from the end of a non-looping clip restarts it; there is nowhere
    // else for the clock to go.
    const elapsedSec = currentState.elapsedSec >= duration
      ? 0
      : clampAnimationElapsed(currentState.elapsedSec, duration);
    // Play takes ownership of the pose from the independent Position controls.
    const nextState = {
      ...currentState,
      activeClipId: clip.id,
      enabled: true,
      elapsedSec,
      playing: true
    };
    animationStateRef.current = nextState;
    setAnimationState(nextState);
    setAnimationClock(elapsedSec);
  }, [selectedAnimationClips, activateAnimationControls]);

  const handleAnimationRestart = useCallback(() => {
    if (!selectedActiveAnimationClip) return;
    activateAnimationControls();
    const nextState = {
      ...animationStateRef.current,
      enabled: true,
      elapsedSec: 0,
      playing: false
    };
    animationStateRef.current = nextState;
    setAnimationState(nextState);
    resetAnimationClock();
  }, [selectedActiveAnimationClip, activateAnimationControls]);

  const handleAnimationScrub = useCallback((elapsedSec) => {
    const clip = selectedActiveAnimationClip;
    if (!clip) {
      return;
    }
    activateAnimationControls();
    const clampedElapsedSec = clampAnimationElapsed(elapsedSec, animationClipDuration(clip));
    const nextState = {
      ...animationStateRef.current,
      enabled: true,
      elapsedSec: clampedElapsedSec
    };
    animationStateRef.current = nextState;
    setAnimationState(nextState);
    setAnimationClock(clampedElapsedSec);
  }, [selectedActiveAnimationClip, activateAnimationControls]);

  const handleAnimationSpeedChange = useCallback((speed) => {
    if (!selectedActiveAnimationClip) return;
    activateAnimationControls();
    const nextState = {
      ...animationStateRef.current,
      enabled: true,
      speed: clampAnimationSpeed(speed)
    };
    animationStateRef.current = nextState;
    setAnimationState(nextState);
  }, [selectedActiveAnimationClip, activateAnimationControls]);

  const handleAnimationLoopToggle = useCallback((nextLoopEnabled) => {
    if (!selectedActiveAnimationClip) return;
    activateAnimationControls();
    const currentState = animationStateRef.current;
    const nextState = {
      ...currentState,
      enabled: true,
      loopEnabled: typeof nextLoopEnabled === "boolean" ? nextLoopEnabled : !currentState.loopEnabled
    };
    animationStateRef.current = nextState;
    setAnimationState(nextState);
  }, [selectedActiveAnimationClip, activateAnimationControls]);

  // The playback loop. The clock is published through the external store rather
  // than React state so a playing clip re-renders only the render pane and the
  // time slider; the paused elapsed time is written back to React state once,
  // when playback stops. Frame pacing (shouldPublishAnimationFrame) keeps a
  // heavy assembly from saturating the main thread.
  useEffect(() => {
    if (
      !selectedActiveAnimationClip ||
      animationState.enabled === false ||
      !animationState.playing ||
      typeof window === "undefined" ||
      typeof window.requestAnimationFrame !== "function"
    ) {
      return undefined;
    }

    const clip = selectedActiveAnimationClip;
    const duration = animationClipDuration(clip);
    let frameId = 0;
    let cancelled = false;
    let previousTimeMs = animationNowMs();
    // A published frame is measured by the gap to the next callback, which
    // includes the downstream render, and the next publish waits that long
    // again. previousTimeMs only advances on a publish, so time skipped this way
    // still lands in the next delta and playback stays wall-clock accurate.
    let publishedAtMs = NaN;
    let publishCostMs = 0;
    let measuringPublish = false;
    setAnimationClock(clampAnimationElapsed(animationStateRef.current.elapsedSec, duration));

    const tick = (timeMs) => {
      const currentState = animationStateRef.current;
      if (cancelled || currentState.enabled === false || !currentState.playing || currentState.activeClipId !== clip.id) {
        return;
      }
      if (measuringPublish) {
        publishCostMs = timeMs - publishedAtMs;
        measuringPublish = false;
      }
      if (!shouldPublishAnimationFrame({ timeMs, publishedAtMs, publishCostMs })) {
        frameId = window.requestAnimationFrame(tick);
        return;
      }
      const deltaSec = Math.max((timeMs - previousTimeMs) / 1000, 0);
      previousTimeMs = timeMs;
      publishedAtMs = timeMs;
      measuringPublish = true;
      const { elapsedSec, playing } = advanceAnimationElapsed({
        elapsedSec: getAnimationClock(),
        deltaSec,
        speed: currentState.speed,
        duration,
        loopEnabled: currentState.loopEnabled !== false
      });
      setAnimationClock(elapsedSec);
      if (!playing) {
        // A non-looping clip ran out: settle the clock into React state so the
        // paused transport and the session snapshot agree with the viewport.
        const nextState = { ...currentState, elapsedSec, playing: false };
        animationStateRef.current = nextState;
        setAnimationState(nextState);
        return;
      }
      frameId = window.requestAnimationFrame(tick);
    };

    frameId = window.requestAnimationFrame(tick);
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frameId);
    };
  }, [animationState.enabled, animationState.playing, selectedActiveAnimationClip]);

  return { handleStepModuleParameterChange, applyStepModuleParameterValues, handleResetStepModuleParameters,
    handleApplyPose, handleAnimationClipSelect, handleAnimationPlayToggle, handleAnimationRestart,
    handleAnimationScrub, handleAnimationSpeedChange, handleAnimationLoopToggle, resetMotion, resetPosition,
    // Leaving Animate: the clip hands the pose back to Position, as Position left it, and keeps
    // nothing of where it was — only the transport preferences, for the next play.
    releaseAnimation: activatePositionControls };
}
