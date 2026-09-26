import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import {
  advanceAnimationElapsed, animationNowMs, clampAnimationElapsed, clampAnimationSpeed
} from "@hardcore/core/common/animationClock.js";
import { createGlbAnimationRuntime, disposeGlbAnimationRuntime, setGlbAnimationTime } from "@hardcore/core/lib/render/glbAnimationRuntime.js";
import { createAnimationClock } from "../kit/tools/playbar/animationClock.js";
import { usePlaybackFrames } from "../kit/tools/playbar/usePlaybackFrames.js";

function clipRows(document) {
  return (document?.clips || []).map((clip, index) => ({
    id: `glb:${index}`,
    label: String(clip.name || `Clip ${index + 1}`),
    duration: Math.max(Number(clip.duration) || 0, 0.001),
    clip
  }));
}

const REST = Object.freeze({ activeClipId: "", enabled: false, playing: false, elapsedSec: 0, speed: 1, loopEnabled: true });

/**
 * The file's glTF clips as the kit playbar's runtime, driven by this renderer's
 * own clock: ONE `AnimationMixer` on the native scene, alive only while a routine
 * owns the pose. The file opens at rest with no mixer at all, so the playbar
 * appearing under the model changes nothing on screen; the mixer is built by the
 * first play, scrub or clip choice, and disposing it restores every animated
 * property to the value it had at rest.
 *
 * @param {object | null} document  The native GLB document on screen.
 * @param {() => void} requestRender  Asks the viewport for a frame.
 * @returns the playbar runtime, or null for a file without playable clips.
 */
export function useGlbAnimation(document, requestRender) {
  const clock = useMemo(() => createAnimationClock(), []);
  const clips = useMemo(() => clipRows(document), [document]);
  const [state, setState] = useState(REST);
  const stateRef = useRef(state);
  stateRef.current = state;
  const activeClip = clips.find((clip) => clip.id === state.activeClipId) || clips[0] || null;
  const requestRenderRef = useRef(requestRender);
  requestRenderRef.current = requestRender;

  const update = useCallback((patch) => {
    const next = { ...stateRef.current, ...patch };
    stateRef.current = next;
    setState(next);
  }, []);
  useEffect(() => {
    clock.resetAnimationClock();
    update({ ...REST, activeClipId: clips[0]?.id || "" });
  }, [document, clips, clock, update]);

  const onClipSelect = useCallback((id) => {
    if (!clips.some((clip) => clip.id === id)) return;
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
  const onScrub = useCallback((value) => {
    if (!activeClip) return;
    const elapsedSec = clampAnimationElapsed(value, activeClip.duration);
    clock.setAnimationClock(elapsedSec);
    update({ enabled: true, elapsedSec });
  }, [activeClip, clock, update]);

  // The clock advances on animation frames while playing; React hears about it when it stops.
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

  // The mixer exists exactly while a routine owns the pose.
  const clip = state.enabled ? activeClip?.clip || null : null;
  const mixerRef = useRef(null);
  const frameRef = useRef(null);
  usePlaybackFrames(clock, state.playing, frameRef);
  useEffect(() => {
    if (!document?.scene || !clip) return undefined;
    const mixer = createGlbAnimationRuntime(THREE, document.scene, clip);
    mixerRef.current = mixer;
    // One function, two callers: React for a scrub or a new clip, the clock per playing tick.
    frameRef.current = (elapsedSec) => {
      setGlbAnimationTime(mixer, elapsedSec);
      requestRenderRef.current?.();
    };
    frameRef.current(stateRef.current.elapsedSec);
    return () => {
      frameRef.current = null;
      mixerRef.current = null;
      disposeGlbAnimationRuntime(mixer);
      requestRenderRef.current?.();
    };
  }, [document, clip]);
  useEffect(() => { if (!state.playing) frameRef.current?.(state.elapsedSec); }, [state.elapsedSec, state.playing]);

  return useMemo(() => (clips.length ? {
    clips, activeClipId: activeClip?.id || "", enabled: state.enabled, playing: state.playing,
    elapsedSec: state.elapsedSec, speed: state.speed, loopEnabled: state.loopEnabled,
    clock, showRestart: false,
    onClipSelect, onPlayToggle, onRestart, onScrub,
    onSpeedChange: (speed) => update({ speed: clampAnimationSpeed(speed) }),
    onLoopToggle: (loopEnabled) => update({ loopEnabled: loopEnabled !== false })
  } : null), [clips, activeClip, state, clock, onClipSelect, onPlayToggle, onRestart, onScrub, update]);
}
