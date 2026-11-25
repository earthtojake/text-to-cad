// The file's playback settings (`playback` of the file's view, `kit/shell/fileView.js`), remembered
// between leaving and re-entering Preview and across a reload of the tab: Preview's Orbit
// speed; once chosen in the playbar's Playback settings, the speed and the loop the routine
// plays with, while unset the routine's own authored values. Orbit on or off is not here: Preview opens
// still every time. (A record from before the Animation tab may say its playbar was put away, `collapsed`:
// there is no playbar in the tools view now, and it is dropped; one from before Autoplay went may carry `autoplay`,
// which is dropped too: a routine opens at rest.)
// Importing this module has no environmental effects.
import { clampAnimationSpeed } from "@cad/core/common/animationClock.js";

export const MAX_ORBIT_SPEED = 5;
export const DEFAULT_PLAYBACK = Object.freeze({ orbitSpeed: 1 });

const finite = value => typeof value === "number" && Number.isFinite(value);

/**
 * @param {unknown} value
 * @returns {{ orbitSpeed: number, speed?: number, loop?: boolean }}
 */
export function normalizePlayback(value) {
  const record = value && typeof value === "object" ? value : {};
  const playback = {
    orbitSpeed: finite(record.orbitSpeed) ? Math.min(MAX_ORBIT_SPEED, Math.max(0, record.orbitSpeed)) : DEFAULT_PLAYBACK.orbitSpeed
  };
  if (finite(record.speed) && record.speed > 0) playback.speed = clampAnimationSpeed(record.speed);
  if (typeof record.loop === "boolean") playback.loop = record.loop;
  return playback;
}
