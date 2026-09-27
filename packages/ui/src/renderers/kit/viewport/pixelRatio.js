// Device-pixel-ratio caps: full quality at rest, a lower cap while the camera moves,
// and how long after the last input the viewport counts as at rest.
export const IDLE_PIXEL_RATIO_CAP = 2;

export const INTERACTION_PIXEL_RATIO_CAP = 1.25;

export const INTERACTION_IDLE_DELAY_MS = 140;

export function getPixelRatioCap(cap) {
  if (typeof window === "undefined") {
    return 1;
  }
  return Math.min(window.devicePixelRatio || 1, cap);
}
