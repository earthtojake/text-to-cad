import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  advanceAnimationElapsed, animationNowMs, clampAnimationElapsed, clampAnimationSpeed
} from "@text-to-cad/core/common/animationClock.js";
import { xbfMotions, xbfMotionTimeline } from "@text-to-cad/core/lib/xbf/xbfMotion.js";
import { createAnimationClock } from "../kit/tools/playbar/animationClock.js";
import { playbackFrameTime, usePlaybackFrames } from "../kit/tools/playbar/usePlaybackFrames.js";

const REST = Object.freeze({ activeClipId: "", enabled: false, playing: false, elapsedSec: 0, speed: 1, loopEnabled: true });

/** Each motion of the mechanism as the transport lists it, with its timeline. */
function motionRows(kinematics) {
  if (!kinematics) return [];
  return xbfMotions(kinematics).flatMap((motion) => {
    try {
      return [{ id: `motion:${motion.name}`, label: motion.name, duration: Math.max(motion.duration, 0.001),
        timeline: xbfMotionTimeline(kinematics, motion.name) }];
    } catch {
      return [];
    }
  });
}

/**
 * An engine document's motions (AP242's interpolated configuration sequences, `xbfMotion.js`) as
 * the kit's routine runtime: what the file sidebar's section (`AnimationSection.jsx`, headed
 * "Motion") and Preview's playbar drive, on this renderer's own clock. Each frame is the motion's
 * pair values at the clock's time, handed to `pose`, which poses the scene through the page's
 * forward kinematics.
 *
 * The motion owns the posed state while it is `enabled`: from the first play, scrub or choice of a
 * motion until Reset lets go of it; paused, its frame stays on the model. Letting go calls
 * `pose(null)`: the scene is posed as Position now holds it, which taking the motion up put at rest
 * (one motion at a time, nothing set aside: `motionExclusion.js`).
 * The file opens with no motion owning anything, and so does each new revision of the model.
 *
 * @param {object | null} kinematics  The scene's mechanism (`xbfKinematics.js`).
 * @param {(values: Record<string, number[]> | null) => void} pose  Poses the scene at a frame's
 *   values; null gives the pose back.
 * @returns the routine runtime, or null for a document with no motions. Beyond the kit's contract,
 *   `noun` ("Motion") names it, and `valuesAt(t)` is the motion in hand's values at `t`.
 */
export function useXbfMotion(kinematics, pose) {
  const clock = useMemo(() => createAnimationClock(), []);
  const clips = useMemo(() => motionRows(kinematics), [kinematics]);
  const [state, setState] = useState(REST);
  const stateRef = useRef(state);
  stateRef.current = state;
  const activeClip = clips.find(clip => clip.id === state.activeClipId) || clips[0] || null;
  const poseRef = useRef(pose);
  poseRef.current = pose;

  const update = useCallback((patch) => {
    const next = { ...stateRef.current, ...patch };
    stateRef.current = next;
    setState(next);
  }, []);
  // At rest for every mechanism (a new revision's included), its first motion in hand. Every motion
  // opens looping: a motion is a finite clip, and the player repeats it.
  useLayoutEffect(() => {
    clock.resetAnimationClock();
    update({ ...REST, activeClipId: clips[0]?.id || "" });
  }, [clips, clock, update]);

  const onClipSelect = useCallback((id) => {
    if (!clips.some(clip => clip.id === id)) return;
    clock.resetAnimationClock();
    update({ activeClipId: id, enabled: true, playing: false, elapsedSec: 0 });
  }, [clips, clock, update]);
  const onPlayToggle = useCallback(() => {
    if (!activeClip) return;
    if (stateRef.current.playing) {
      update({ playing: false, elapsedSec: clampAnimationElapsed(clock.getAnimationClock(), activeClip.duration) });
      return;
    }
    const elapsedSec = stateRef.current.elapsedSec >= activeClip.duration ? 0 : stateRef.current.elapsedSec;
    clock.setAnimationClock(elapsedSec);
    update({ enabled: true, playing: true, elapsedSec });
  }, [activeClip, clock, update]);
  const onRestart = useCallback(() => {
    clock.resetAnimationClock();
    update({ enabled: true, playing: false, elapsedSec: 0 });
  }, [clock, update]);
  // Stop: stopped, rewound and let go of; the motion in hand, Speed and Loop stay.
  const onRelease = useCallback(() => {
    if (!stateRef.current.enabled && !stateRef.current.playing) return;
    clock.resetAnimationClock();
    update({ enabled: false, playing: false, elapsedSec: 0 });
  }, [clock, update]);
  const onScrub = useCallback((value) => {
    if (!activeClip) return;
    const elapsedSec = clampAnimationElapsed(value, activeClip.duration);
    clock.setAnimationClock(elapsedSec);
    update({ enabled: true, elapsedSec });
  }, [activeClip, clock, update]);

  // The clock advances on animation frames while playing; React hears of it when it stops.
  useEffect(() => {
    if (!activeClip || !state.playing) return undefined;
    let frameId = 0;
    let previous = animationNowMs();
    const tick = (now) => {
      const current = stateRef.current;
      if (!current.playing || current.activeClipId !== activeClip.id) return;
      const next = advanceAnimationElapsed({
        elapsedSec: clock.getAnimationClock(), deltaSec: Math.max(now - previous, 0) / 1000,
        speed: current.speed, duration: activeClip.duration, loopEnabled: current.loopEnabled
      });
      previous = now;
      clock.setAnimationClock(next.elapsedSec);
      if (!next.playing) { update({ playing: false, elapsedSec: next.elapsedSec }); return; }
      frameId = window.requestAnimationFrame(tick);
    };
    frameId = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frameId);
  }, [activeClip, state.playing, clock, update]);

  // The motion poses the scene exactly while it is enabled; letting go hands the scene back.
  const timeline = state.enabled ? activeClip?.timeline || null : null;
  const frameRef = useRef(null);
  usePlaybackFrames(clock, state.playing, frameRef);
  useEffect(() => {
    if (!timeline) return undefined;
    // One function, two callers: React for a scrub or a new motion, the clock per playing tick.
    frameRef.current = elapsedSec => poseRef.current?.(timeline.values(elapsedSec));
    frameRef.current(playbackFrameTime(clock, stateRef.current));
    return () => {
      frameRef.current = null;
      poseRef.current?.(null);
    };
  }, [timeline, clock]);
  // A scrub, a pause, and a play's first frame (from the start again, when it played from the end).
  useEffect(() => { frameRef.current?.(playbackFrameTime(clock, stateRef.current)); }, [state.elapsedSec, state.playing, clock]);

  const valuesAt = useCallback(t => activeClip?.timeline.values(t) || null, [activeClip]);
  return useMemo(() => (clips.length ? {
    noun: "Motion", clips, activeClipId: activeClip?.id || "", enabled: state.enabled, playing: state.playing,
    elapsedSec: state.elapsedSec, speed: state.speed, loopEnabled: state.loopEnabled, clock, showRestart: false,
    onClipSelect, onPlayToggle, onRestart, onScrub, onRelease, valuesAt,
    onSpeedChange: speed => update({ speed: clampAnimationSpeed(speed) }),
    onLoopToggle: loopEnabled => update({ loopEnabled: loopEnabled !== false })
  } : null), [clips, activeClip, state, clock, onClipSelect, onPlayToggle, onRestart, onScrub, onRelease, valuesAt, update]);
}
