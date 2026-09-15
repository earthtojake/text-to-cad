import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  advanceAnimationElapsed,
  animationNowMs,
  clampAnimationElapsed,
  clampAnimationSpeed
} from "cadgen-js/common/animationClock";
import {
  getEmbeddedGlbAnimationClock as getAnimationClock,
  resetEmbeddedGlbAnimationClock as resetAnimationClock,
  setEmbeddedGlbAnimationClock as setAnimationClock
} from "./embeddedGlbAnimationClockStore";

function clipRows(document) {
  return (document?.clips || []).map((clip, index) => ({
    id: `glb:${index}`,
    label: String(clip.name || `Clip ${index + 1}`),
    duration: Math.max(Number(clip.duration) || 0, 0.001),
    clip
  }));
}

export function useEmbeddedGlbAnimation(document) {
  const clips = useMemo(() => clipRows(document), [document]);
  const [state, setState] = useState({ activeClipId: "", playing: false, elapsedSec: 0, speed: 1, loopEnabled: true });
  const stateRef = useRef(state);
  stateRef.current = state;
  const activeClip = clips.find((clip) => clip.id === state.activeClipId) || clips[0] || null;

  useEffect(() => {
    const next = { activeClipId: clips[0]?.id || "", playing: false, elapsedSec: 0, speed: 1, loopEnabled: true };
    stateRef.current = next;
    setState(next);
    resetAnimationClock();
  }, [document, clips]);

  const update = useCallback((patch) => {
    const next = { ...stateRef.current, ...patch };
    stateRef.current = next;
    setState(next);
  }, []);
  const onClipSelect = useCallback((id) => {
    if (!clips.some((clip) => clip.id === id)) return;
    resetAnimationClock();
    update({ activeClipId: id, playing: false, elapsedSec: 0 });
  }, [clips, update]);
  const onPlayToggle = useCallback(() => {
    if (!activeClip) return;
    if (stateRef.current.playing) {
      update({ playing: false, elapsedSec: clampAnimationElapsed(getAnimationClock(), activeClip.duration) });
      return;
    }
    const elapsedSec = stateRef.current.elapsedSec >= activeClip.duration ? 0 : stateRef.current.elapsedSec;
    setAnimationClock(elapsedSec);
    update({ playing: true, elapsedSec });
  }, [activeClip, update]);
  const onRestart = useCallback(() => {
    resetAnimationClock();
    update({ playing: false, elapsedSec: 0 });
  }, [update]);
  const onScrub = useCallback((value) => {
    if (!activeClip) return;
    const elapsedSec = clampAnimationElapsed(value, activeClip.duration);
    setAnimationClock(elapsedSec);
    update({ elapsedSec });
  }, [activeClip, update]);

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
  }, [activeClip, state.playing, update]);

  if (!clips.length) return null;
  return {
    clips, activeClipId: activeClip?.id || "", playing: state.playing,
    elapsedSec: state.elapsedSec, speed: state.speed, loopEnabled: state.loopEnabled,
    clockKind: "embedded-glb",
    showEnableToggle: false,
    showRestart: false,
    onClipSelect, onPlayToggle, onRestart, onScrub,
    onSpeedChange: (speed) => update({ speed: clampAnimationSpeed(speed) }),
    onLoopToggle: (loopEnabled) => update({ loopEnabled: loopEnabled !== false }),
    render: { clip: activeClip?.clip || null, elapsedSec: state.elapsedSec, playing: state.playing }
  };
}
