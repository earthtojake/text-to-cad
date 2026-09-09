// The frame SCHEDULE a `{fps, seconds, start}` request implies over one clip.
//
// Two consumers, one arithmetic: the snapshot page renders a span of a clip to
// video (headlessRenderEntry), and the GLB export door SAMPLES the same span
// into baked keyframes (lib/export/packageAnimation.js). fps means a different
// thing to each — a playback rate there, a sampling rate here — but where the
// samples fall does not, and two derivations of "which moments of the clip" is
// exactly the pair that drifts by one frame and loops with a stutter.
//
// `label` is the word the errors use, because the same wrong number is a bad
// video request in one caller and a bad animation request in the other, and an
// error that names the flag the user did not pass sends them to the wrong page.

import { animationClipDuration } from "./animationClock.js";

export const FRAME_PLAN_FPS_MIN = 1;
export const FRAME_PLAN_FPS_MAX = 120;
// The ceiling that actually bounds the work, because the count is fps TIMES
// seconds: an fps bound alone still lets `{fps: 30, seconds: 3000}` — a caller
// writing milliseconds — schedule 90,000 samples. For a video every one is a
// full-size PNG on disk before ffmpeg sees it; for a GLB every one is a TRS
// keyframe per moving occurrence in the file. 7200 is four minutes at 30 fps;
// past that the request is a typo, not a schedule. cadgen enforces the same
// ceiling on the side it can (snapshot_video.MAX_VIDEO_FRAMES,
// mesh_animation.MAX_ANIMATION_SAMPLES) — only an EXPLICIT span, because the
// clip-duration default is resolved here, where the clip is.
export const FRAME_PLAN_MAX_FRAMES = 7200;

function formatSeconds(value) {
  return `${Number(value.toFixed(3))}s`;
}

/** The frame schedule a `{fps, seconds, start}` request implies over one clip.
 *
 * `seconds` defaults to the span the clip still HAS from `start`, and the frame
 * count is `seconds * fps` rounded, so the last frame sits one interval BEFORE
 * `start + seconds`. That is what makes a looping clip loop cleanly: the frame
 * at `start + seconds` is the frame at `start` again, and rendering both
 * stutters on every repeat.
 *
 * Every time is measured against the clip, because `evaluateAnimationClip`
 * ANSWERS a time past the end rather than refusing it: a non-looping clip
 * clamps, so the tail is one still image repeated, and a looping one wraps, so
 * it covers a different span than the one asked for. Both are exit-0 wrong
 * answers that nothing downstream can tell from a right one. */
export function resolveFramePlan(request, clip, { label = "frame" } = {}) {
  const raw = request && typeof request === "object" ? request : {};
  const fps = Number(raw.fps ?? 30);
  if (!Number.isInteger(fps) || fps < FRAME_PLAN_FPS_MIN || fps > FRAME_PLAN_FPS_MAX) {
    throw new Error(`${label} fps must be a whole number ${FRAME_PLAN_FPS_MIN}..${FRAME_PLAN_FPS_MAX}, got ${JSON.stringify(raw.fps)}`);
  }
  const start = raw.start === undefined || raw.start === null ? 0 : Number(raw.start);
  if (!Number.isFinite(start) || start < 0) {
    throw new Error(`${label} start must be seconds >= 0, got ${JSON.stringify(raw.start)}`);
  }
  const duration = animationClipDuration(clip);
  if (start >= duration) {
    throw new Error(
      `${label} start ${formatSeconds(start)} is at or past the end of a ${formatSeconds(duration)} clip: `
      + "every frame would be the same one"
    );
  }
  const looping = clip?.loop !== false;
  const seconds = raw.seconds === undefined || raw.seconds === null
    // A looping clip's default is one whole cycle from wherever it starts; a
    // clip that stops at its end has only the part of it that is left.
    ? (looping ? duration : duration - start)
    : Number(raw.seconds);
  if (!Number.isFinite(seconds) || seconds <= 0) {
    throw new Error(`${label} seconds must be a positive number, got ${JSON.stringify(raw.seconds)}`);
  }
  const frameCount = Math.max(1, Math.round(seconds * fps));
  if (frameCount > FRAME_PLAN_MAX_FRAMES) {
    throw new Error(
      `${label} ${formatSeconds(seconds)} at ${fps} fps schedules ${frameCount} frames, `
      + `past the ${FRAME_PLAN_MAX_FRAMES}-frame ceiling`
    );
  }
  const warnings = [];
  // An explicit span that overruns a clip which does not loop is the caller's
  // to make, but the frames it buys past the end are all the final pose, and
  // nothing in the finished file says so.
  if (!looping && (start + seconds) - duration > 1e-9) {
    warnings.push(
      `${label} covers ${formatSeconds(start)}..${formatSeconds(start + seconds)} of a `
      + `${formatSeconds(duration)} clip that does not loop: every frame past its end is the same final pose`
    );
  }
  return { fps, seconds, start, frameCount, warnings };
}

/** The moment of the CLIP frame `index` of the plan samples. */
export function framePlanElapsedSec(plan, index) {
  return plan.start + (index / plan.fps);
}
