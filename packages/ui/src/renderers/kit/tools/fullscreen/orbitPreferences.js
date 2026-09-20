// Global viewing preference, independent of a file's animation/session state.
// The host supplies storage; importing this module has no environmental effects.
export const ORBIT_STORAGE_KEY = "cad-viewer:orbit:v1";
export const DEFAULT_ORBIT = Object.freeze({ speed: 1 });
export const MAX_ORBIT_SPEED = 5;

export function normalizeOrbit(value) {
  const speed = value?.speed;
  return { speed: typeof speed === "number" && Number.isFinite(speed)
    ? Math.min(MAX_ORBIT_SPEED, Math.max(0, speed)) : DEFAULT_ORBIT.speed };
}

export function readOrbit(storage) {
  try { return normalizeOrbit(JSON.parse(storage?.getItem(ORBIT_STORAGE_KEY) || "null")); }
  catch { return { ...DEFAULT_ORBIT }; }
}

export function writeOrbit(storage, value) {
  try { storage?.setItem(ORBIT_STORAGE_KEY, JSON.stringify(normalizeOrbit(value))); }
  catch { /* A blocked preference store must not prevent camera navigation. */ }
}
