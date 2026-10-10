// The file's playback settings (`playback` of the file's view, `kit/shell/fileView.js`), remembered
// between leaving and re-entering preview and across a reload of the tab: preview's Orbit on or off
// and its speed; Autoplay; and — once chosen in the Animation tool — the speed and the loop the
// tools view's routine plays with, while unset the routine's own authored values. Preview's own
// speed and loop are never here: they start at the routine's each time and are forgotten on leaving.
// Importing this module has no environmental effects.
import { clampAnimationSpeed } from "@text-to-cad/core/common/animationClock.js";

export const MAX_ORBIT_SPEED = 5;
export const DEFAULT_PLAYBACK = Object.freeze({ orbit: true, orbitSpeed: 1, autoplay: false });

const finite = value => typeof value === "number" && Number.isFinite(value);

/**
 * @param {unknown} value
 * @returns {{ orbit: boolean, orbitSpeed: number, autoplay: boolean, speed?: number, loop?: boolean }}
 */
export function normalizePlayback(value) {
  const record = value && typeof value === "object" ? value : {};
  const playback = {
    orbit: typeof record.orbit === "boolean" ? record.orbit : DEFAULT_PLAYBACK.orbit,
    orbitSpeed: finite(record.orbitSpeed) ? Math.min(MAX_ORBIT_SPEED, Math.max(0, record.orbitSpeed)) : DEFAULT_PLAYBACK.orbitSpeed,
    autoplay: record.autoplay === true
  };
  if (finite(record.speed) && record.speed > 0) playback.speed = clampAnimationSpeed(record.speed);
  if (typeof record.loop === "boolean") playback.loop = record.loop;
  return playback;
}
