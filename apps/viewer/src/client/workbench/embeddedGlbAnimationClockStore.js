import { useSyncExternalStore } from "react";

const listeners = new Set();
let elapsedSec = 0;
const snapshot = () => elapsedSec;
const subscribe = (listener) => { listeners.add(listener); return () => listeners.delete(listener); };

export function setEmbeddedGlbAnimationClock(value) {
  const numeric = Number(value);
  const next = Number.isFinite(numeric) && numeric > 0 ? numeric : 0;
  if (next === elapsedSec) return;
  elapsedSec = next;
  for (const listener of listeners) listener();
}

export function getEmbeddedGlbAnimationClock() { return elapsedSec; }
export function resetEmbeddedGlbAnimationClock() { setEmbeddedGlbAnimationClock(0); }
export function useEmbeddedGlbAnimationClock() {
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}
