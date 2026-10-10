import { useCallback, useEffect, useMemo, useRef } from "react";
import { advanceAnimationElapsed, animationClipDuration, animationNowMs,
  clampAnimationElapsed, clampAnimationSpeed, createAnimationFramePacer, findAnimationClip,
  firstAnimationClipId } from "@text-to-cad/core/common/animationClock.js";
import {
  articulationControl, articulationPoses, clampControlValue, normalizeControlValues, poseControlValues
} from "@text-to-cad/core/common/articulation.js";
import { useAnimationClockStore } from "./animationClockStore.js";
import { stepPoseLogic } from "./poseLoad.js";

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
  const articulation = selectedStepModuleDefinition?.articulation || null;
  const resetPosition = useCallback(() => {
    setAppliedStepPoseName("");
    writeParameters(normalizeControlValues(articulation, null));
  }, [articulation, setAppliedStepPoseName, writeParameters]);
  // What Position had set when a routine took the pose. A routine plays from the model at rest,
  // so taking the pose puts Position's values aside rather than throwing them away; handing
  // the pose back (leaving preview or the Animation tool, or touching Position) puts them back first. They are a pose
  // like any other: an update whose joints and named poses are unchanged keeps them (a routine
  // may play on through it), and one that changed them drops them.
  const heldPositionRef = useRef(null);
  const poseLogic = useMemo(() => stepPoseLogic(selectedStepModuleDefinition), [selectedStepModuleDefinition]);
  useEffect(() => { heldPositionRef.current = null; }, [poseLogic]);
  // Handing the pose to Position stops the routine and rewinds its clock, and nothing more: the
  // transport preferences the Animation tool and preview's playbar set (the routine, its speed, the
  // loop) are the person's, and a joint nudge or a trip to another tool keeps them for the next play.
  const activatePositionControls = useCallback(() => {
    motionRevisionRef.current += 1;
    const next = { ...animationStateRef.current, enabled: false, playing: false, elapsedSec: 0 };
    animationStateRef.current = next;
    setAnimationState(next);
    resetAnimationClock();
    const held = heldPositionRef.current;
    heldPositionRef.current = null;
    if (held) writeParameters(normalizeControlValues(articulation, held));
  }, [resetAnimationClock, articulation, writeParameters]);
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
    const control = articulationControl(articulation, id);
    if (!control) {
      return;
    }
    activatePositionControls();
    // Moving a control by hand leaves the named pose behind, so the dropdown stops claiming
    // it and goes back to reading the values (the robot's group state does the same).
    setAppliedStepPoseName("");
    writeParameters({ ...stepModuleParameterValuesRef.current, [id]: clampControlValue(control, value) });
  }, [activatePositionControls, articulation, writeParameters]);

  const applyStepModuleParameterValues = useCallback((values) => {
    if (!articulation) return;
    activatePositionControls();
    setAppliedStepPoseName("");
    writeParameters(normalizeControlValues(articulation, { ...stepModuleParameterValuesRef.current, ...values }));
  }, [activatePositionControls, articulation, writeParameters]);
  const handleResetStepModuleParameters = resetMotion;

  const handleApplyPose = useCallback((poseName) => {
    if (!articulationPoses(articulation)[poseName]) {
      return;
    }
    activatePositionControls();
    const nextParameterValues = poseControlValues(articulation, poseName);
    setAppliedStepPoseName(String(poseName || ""));
    // A pose is written like any other value: where the mechanism is from this
    // frame on. Motion over time belongs to preview mode.
    writeParameters(nextParameterValues);
  }, [activatePositionControls, articulation, setAppliedStepPoseName, writeParameters]);

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
  // when playback stops. Frame pacing (createAnimationFramePacer) keeps a heavy
  // assembly from saturating the main thread, and only a run of overrunning
  // frames is saturation: one that misses a vsync publishes on.
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
    // includes the downstream render; once the last few all overran, the next
    // publish waits about twice that. previousTimeMs only advances on a publish,
    // so time skipped this way still lands in the next delta and playback stays
    // wall-clock accurate.
    const pacer = createAnimationFramePacer();
    setAnimationClock(clampAnimationElapsed(animationStateRef.current.elapsedSec, duration));

    const tick = (timeMs) => {
      const currentState = animationStateRef.current;
      if (cancelled || currentState.enabled === false || !currentState.playing || currentState.activeClipId !== clip.id) {
        return;
      }
      if (!pacer.shouldPublish(timeMs)) {
        frameId = window.requestAnimationFrame(tick);
        return;
      }
      const deltaSec = Math.max((timeMs - previousTimeMs) / 1000, 0);
      previousTimeMs = timeMs;
      pacer.published(timeMs);
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

  // Leaving preview or the Animation tool: the clip hands the pose back to Position, as Position
  // left it, and keeps nothing of where it was — only the transport preferences, for the next play.
  // A routine already at rest, with nothing of Position's set aside, has nothing to hand back.
  const releaseAnimation = useCallback(() => {
    const current = animationStateRef.current;
    if (current.enabled === false && !current.playing && !current.elapsedSec && !heldPositionRef.current) return;
    activatePositionControls();
  }, [activatePositionControls]);
  // Preview's routine is its own (`kit/shell/useRendererShell.js`): the tools view's is saved as it
  // stands — which routine, where its clock is, whether it plays, its Speed and Loop — and handed
  // back as it was. A routine that owned the pose takes it again, Position's values set aside as before.
  const savePlayback = useCallback(() => {
    const { activeClipId, enabled, playing, elapsedSec, speed, loopEnabled } = animationStateRef.current;
    return { activeClipId, enabled, playing, elapsedSec: playing ? getAnimationClock() : elapsedSec, speed, loopEnabled };
  }, [getAnimationClock]);
  // Preview opens on the routine at rest, at its own Speed and Loop, whatever the tools view chose.
  const resetPlayback = useCallback(() => {
    releaseAnimation();
    const clip = findAnimationClip(selectedAnimationClips, animationStateRef.current.activeClipId);
    const nextState = { ...animationStateRef.current, speed: 1, loopEnabled: clip ? clip.loop !== false : true };
    animationStateRef.current = nextState;
    setAnimationState(nextState);
  }, [releaseAnimation, selectedAnimationClips]);
  const restorePlayback = useCallback((saved) => {
    const clip = findAnimationClip(selectedAnimationClips, saved?.activeClipId);
    if (!clip) return;
    const elapsedSec = clampAnimationElapsed(saved.elapsedSec, animationClipDuration(clip));
    if (saved.enabled !== false) activateAnimationControls();
    else motionRevisionRef.current += 1;
    const nextState = { ...animationStateRef.current, activeClipId: clip.id, enabled: saved.enabled !== false,
      playing: saved.enabled !== false && saved.playing === true, elapsedSec,
      speed: clampAnimationSpeed(saved.speed), loopEnabled: saved.loopEnabled !== false };
    animationStateRef.current = nextState;
    setAnimationState(nextState);
    setAnimationClock(elapsedSec);
  }, [selectedAnimationClips, activateAnimationControls]);

  return { handleStepModuleParameterChange, applyStepModuleParameterValues, handleResetStepModuleParameters,
    handleApplyPose, handleAnimationClipSelect, handleAnimationPlayToggle, handleAnimationRestart,
    handleAnimationScrub, handleAnimationSpeedChange, handleAnimationLoopToggle, resetMotion, resetPosition,
    releaseAnimation, savePlayback, resetPlayback, restorePlayback };
}
