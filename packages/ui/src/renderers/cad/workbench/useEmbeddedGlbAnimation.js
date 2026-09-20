import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  advanceAnimationElapsed,
  animationNowMs,
  clampAnimationElapsed,
  clampAnimationSpeed
} from "@hardcore/core/common/animationClock.js";
import { useEmbeddedGlbAnimationClockStore } from "./embeddedGlbAnimationClockStore.js";

function clipRows(document) {
  return (document?.clips || []).map((clip, index) => ({
    id: `glb:${index}`,
    label: String(clip.name || `Clip ${index + 1}`),
    duration: Math.max(Number(clip.duration) || 0, 0.001),
    clip
  }));
}

export function useEmbeddedGlbAnimation(document) {
  const { getAnimationClock, resetAnimationClock, setAnimationClock } = useEmbeddedGlbAnimationClockStore();
  const clips = useMemo(() => clipRows(document), [document]);
  const [state, setState] = useState({ activeClipId: "", enabled: true, playing: false, elapsedSec: 0, speed: 1, loopEnabled: true });
  const stateRef = useRef(state);
  stateRef.current = state;
  const activeClip = clips.find((clip) => clip.id === state.activeClipId) || clips[0] || null;

  useEffect(() => {
    const next = { activeClipId: clips[0]?.id || "", enabled: true, playing: false, elapsedSec: 0, speed: 1, loopEnabled: true };
    stateRef.current = next;
    setState(next);
    resetAnimationClock();
  }, [document, clips, resetAnimationClock]);

  const update = useCallback((patch) => {
    const next = { ...stateRef.current, ...patch };
    stateRef.current = next;
    setState(next);
  }, []);
  const onClipSelect = useCallback((id) => {
    if (!clips.some((clip) => clip.id === id)) return;
    resetAnimationClock();
    update({ activeClipId: id, enabled: true, playing: false, elapsedSec: 0 });
  }, [clips, update, resetAnimationClock]);
  const onPlayToggle = useCallback(() => {
    if (!activeClip) return;
    if (stateRef.current.playing) {
      update({ playing: false, elapsedSec: clampAnimationElapsed(getAnimationClock(), activeClip.duration) });
      return;
    }
    const elapsedSec = stateRef.current.elapsedSec >= activeClip.duration ? 0 : stateRef.current.elapsedSec;
    setAnimationClock(elapsedSec);
    update({ enabled: true, playing: true, elapsedSec });
  }, [activeClip, update, getAnimationClock, setAnimationClock]);
  const onRestart = useCallback(() => {
    resetAnimationClock();
    update({ enabled: true, playing: false, elapsedSec: 0 });
  }, [update, resetAnimationClock]);
  const resetModel = useCallback(() => {
    resetAnimationClock();
    update({ activeClipId: clips[0]?.id || "", enabled: false, playing: false, elapsedSec: 0, speed: 1, loopEnabled: true });
  }, [clips, update, resetAnimationClock]);
  const onScrub = useCallback((value) => {
    if (!activeClip) return;
    const elapsedSec = clampAnimationElapsed(value, activeClip.duration);
    setAnimationClock(elapsedSec);
    update({ enabled: true, elapsedSec });
  }, [activeClip, update, setAnimationClock]);

  useEffect(() => {
    if (!activeClip || !state.playing || typeof window === "undefined" || typeof window.requestAnimationFrame !== "function") return undefined;
    let frameId = 0;
    let previous = animationNowMs();
    const tick = (now) => {
      const current = stateRef.current;
      if (!current.playing || current.activeClipId !== activeClip.id) return;
      const next = advanceAnimationElapsed({
        elapsedSec: getAnimationClock(), deltaSec: Math.max(now - previous, 0) / 1000,
        speed: current.speed, duration: activeClip.duration, loopEnabled: current.loopEnabled
      });
      previous = now;
      setAnimationClock(next.elapsedSec);
      if (!next.playing) {
        update({ playing: false, elapsedSec: next.elapsedSec });
        return;
      }
      frameId = window.requestAnimationFrame(tick);
    };
    frameId = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frameId);
  }, [activeClip, state.playing, update, getAnimationClock, setAnimationClock]);

  if (!clips.length) return null;
  return {
    clips, activeClipId: activeClip?.id || "", enabled: state.enabled, playing: state.playing,
    elapsedSec: state.elapsedSec, speed: state.speed, loopEnabled: state.loopEnabled,
    clockKind: "embedded-glb",
    showRestart: false,
    onClipSelect, onPlayToggle, onRestart, onScrub, resetModel,
    onSpeedChange: (speed) => update({ speed: clampAnimationSpeed(speed) }),
    onLoopToggle: (loopEnabled) => update({ loopEnabled: loopEnabled !== false }),
    render: { clip: state.enabled ? activeClip?.clip || null : null, elapsedSec: state.elapsedSec, playing: state.playing }
  };
}
