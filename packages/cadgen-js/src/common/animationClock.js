// The animation TRANSPORT, shared by every client (viewer Animation tab,
// the docs hero, any embed): which clip is active, where the clock
// is, and how fast it runs. Choreography itself lives in the sidecar's copied
// .anim.js text and is compiled by cadgen-js/common/animationRuntime; this module
// owns only the transport around it.
//
// Independence, restated in code: nothing here reads a step-module definition,
// a DOF, or a pose preset. The Pose tab and the Animation tab share a model and
// nothing else.

// Whether the transport drives the model is a GATE, not a selection: the
// Animation section's enable switch. With it off the evaluator never runs and
// the model shows exactly the pose the Pose tab set. The clip picker therefore
// carries the model's authored clips and nothing else -- a built-in "no clip"
// entry used to stand in for this gate, which read as an authored clip named
// after a state and collided with pose presets literally named `rest`.

export const ANIMATION_SPEED_MIN = 0.1;
export const ANIMATION_SPEED_MAX = 3;

function normalizeString(value) {
  return String(value == null ? "" : value).trim();
}

function clampNumber(value, min, max) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return min;
  }
  return Math.min(Math.max(numericValue, min), max);
}

export function clampAnimationSpeed(value) {
  return clampNumber(value, ANIMATION_SPEED_MIN, ANIMATION_SPEED_MAX);
}

export function animationClipDuration(clip) {
  return Math.max(Number(clip?.duration) || 0, 0.001);
}

/** Compiled clips (an id -> clip record map) as an ordered list for the UI. */
export function animationClipList(clips) {
  if (!clips || typeof clips !== "object") {
    return [];
  }
  return Object.values(clips)
    .filter((clip) => clip && typeof clip.update === "function")
    .map((clip) => ({
      id: String(clip.id),
      label: String(clip.label || clip.id),
      duration: animationClipDuration(clip),
      loop: clip.loop !== false
    }));
}

export function hasAnimationClips(clips) {
  return animationClipList(clips).length > 0;
}

/** The clip an id selects, or null for an id this model does not ship. */
export function findAnimationClip(clips, clipId) {
  const id = normalizeString(clipId);
  if (!id || !clips || typeof clips !== "object") {
    return null;
  }
  const clip = clips[id];
  return clip && typeof clip.update === "function" ? clip : null;
}

/** The clip the transport opens on: a model's first declared clip. */
export function firstAnimationClipId(clips) {
  return animationClipList(clips)[0]?.id || "";
}

/** One frozen frame from a `{clip, time}` request — the snapshot job's
 * `animation` field. The id resolves exactly as the viewer's transport resolves
 * its active clip (findAnimationClip), and the result is the same
 * `{clip, elapsedSec, playing}` the viewer hands its render pass, so a still at
 * time t IS the frame the viewer shows there. An unknown id fails with the
 * declared set — nothing renders a plausible rest frame under a typo. Time
 * passes through unclamped: looping and clamping belong to the evaluator, for
 * stills and playback alike. */
export function resolveAnimationFrame(clips, request) {
  const id = normalizeString(request?.clip);
  if (!id) {
    throw new Error("animation requires a clip name ({clip, time})");
  }
  const clip = findAnimationClip(clips, id);
  if (!clip) {
    const declared = animationClipList(clips).map((entry) => entry.id);
    throw new Error(
      declared.length
        ? `Unknown animation clip: ${id}. This model declares: ${declared.join(", ")}`
        : `Unknown animation clip: ${id}. This model declares no animation clips`
    );
  }
  const rawTime = request?.time;
  const time = rawTime === undefined || rawTime === null ? 0 : Number(rawTime);
  if (!Number.isFinite(time) || time < 0) {
    throw new Error(`animation time must be seconds >= 0, got ${JSON.stringify(rawTime)}`);
  }
  return { clip, elapsedSec: time, playing: false };
}

/** The transport a model opens on: its FIRST declared clip, gated on, paused at
 * zero. Selecting a clip is not the same act as running one, so the gate and the
 * selection are separate fields — `enabled` says whether the clip drives the
 * model, `playing` only says whether the clock is moving. Called before the
 * clips compile (the file-switch reset), `clips` is absent and the selection is
 * empty until the load effect restores against the real ones.
 *
 * The gate opens with the model, which is a deliberate reversal of what the
 * removed "no clip" entry gave: a model that merely SHIPS clips used to cost
 * nothing until the user picked one, and now it costs one evaluator pass at
 * t = 0 on open, and shows that frame rather than the authored placement when
 * the first clip's t = 0 is not identity. Selecting is what the picker does;
 * running is what the gate does, and a declared clip that nothing runs until a
 * switch is found reads as a broken tab. Turn the gate off to get the old
 * zero-cost open back — for THIS file, remembered. */
export function buildDefaultAnimationState(clips) {
  const clip = findAnimationClip(clips, firstAnimationClipId(clips));
  return {
    activeClipId: clip?.id || "",
    enabled: true,
    playing: false,
    elapsedSec: 0,
    speed: 1,
    // The opening clip's own loop preference, exactly as selecting it would set.
    loopEnabled: clip ? clip.loop !== false : true
  };
}

/** Restore a persisted slice against the clips this model actually has.
 * Playback never resumes on load (a session restore that starts animating on
 * its own is a surprise), and the transport preferences the slice recorded —
 * the gate, the speed, the loop — are its own: they survive every path here,
 * because a selection that no longer resolves says nothing about how fast the
 * clip should run or whether it should loop.
 *
 * Two different things arrive with no clip behind them and only ONE of them is
 * a user decision:
 *
 *   - NO selection recorded (`activeClipId: ""`). That is not a legacy
 *     sentinel — it is the state this module still returns before a model's
 *     clips compile, so the file-switch reset writes it and the debounced
 *     session save can persist it. It says nothing about the gate, so the model
 *     opens exactly as it would with no stored session at all: first clip,
 *     gate as recorded (on, for a slice written before the gate existed).
 *   - A selection this model NO LONGER SHIPS (a renamed or deleted clip, with
 *     other clips still compiled). That selection died: fall back to the first
 *     clip with the gate OFF, so the picker stays legible without the model
 *     silently animating something the user never picked. */
export function restoreAnimationState(stored, clips) {
  const defaults = buildDefaultAnimationState(clips);
  if (!stored || typeof stored !== "object") {
    return defaults;
  }
  const speed = clampAnimationSpeed(stored.speed ?? defaults.speed);
  const enabled = typeof stored.enabled === "boolean" ? stored.enabled : defaults.enabled;
  const clip = findAnimationClip(clips, stored.activeClipId);
  if (!clip) {
    const selectionDied = normalizeString(stored.activeClipId) !== "" && hasAnimationClips(clips);
    return {
      ...defaults,
      enabled: selectionDied ? false : enabled,
      speed,
      loopEnabled: typeof stored.loopEnabled === "boolean" ? stored.loopEnabled : defaults.loopEnabled
    };
  }
  return {
    activeClipId: clip.id,
    enabled,
    playing: false,
    elapsedSec: clampAnimationElapsed(stored.elapsedSec, animationClipDuration(clip)),
    speed,
    // The RESOLVED clip's own loop preference, not the opening clip's: a slice
    // that names clip B must not inherit clip A's default.
    loopEnabled: typeof stored.loopEnabled === "boolean" ? stored.loopEnabled : clip.loop !== false
  };
}

/** What the render pass draws for the animation system, or null when the
 * transport is not driving the model. Null IS the rest scene: with no frame the
 * evaluator never runs and the model shows exactly what the Pose tab set, which
 * is the one behaviour the section's gate switch has to reproduce. */
export function animationRenderFrame({
  enabled = true,
  clip = null,
  elapsedSec = 0,
  playing = false
} = {}) {
  if (enabled === false || !clip) {
    return null;
  }
  return { clip, elapsedSec, playing: playing === true };
}

export function clampAnimationElapsed(value, duration) {
  return clampNumber(value, 0, Math.max(Number(duration) || 0, 0));
}

/** Advance the clock one tick. Looping wraps; a non-looping clip stops at its
 * end, which is the one place playback ends on its own. */
export function advanceAnimationElapsed({
  elapsedSec = 0,
  deltaSec = 0,
  speed = 1,
  duration = 1,
  loopEnabled = true
} = {}) {
  const safeDuration = Math.max(Number(duration) || 0, 0.001);
  const next = Math.max(Number(elapsedSec) || 0, 0)
    + (Math.max(Number(deltaSec) || 0, 0) * clampAnimationSpeed(speed));
  if (loopEnabled) {
    return { elapsedSec: next % safeDuration, playing: true };
  }
  if (next >= safeDuration) {
    return { elapsedSec: safeDuration, playing: false };
  }
  return { elapsedSec: next, playing: true };
}

export function animationNowMs() {
  if (typeof performance !== "undefined" && typeof performance.now === "function") {
    return performance.now();
  }
  return Date.now();
}

// Frame pacing for playback.  The floor sits under a display frame so an
// unsaturated model publishes on every rAF; the ceiling stops a very heavy
// model from pacing itself below 4 fps.
export const MIN_ANIMATION_FRAME_MS = 8;
export const SATURATED_ANIMATION_FRAME_MS = 32;
export const MAX_ANIMATION_FRAME_MS = 250;

// How long to wait before publishing the next animation frame.
//
// Publishing costs far more than the tick that publishes it -- the store notify
// re-renders the render pane, re-evaluates the clip across every display record
// and redraws the scene.  On a large assembly that lands well over a display
// frame, so publishing on every rAF saturates the main thread: the clock keeps
// advancing but the browser never gets a slot to composite, and playback reads
// as frozen even though scrubbing the same clip still works (a scrub pays the
// cost once).
//
// The cost of a frame is measured as the gap to the following callback, which
// is the one number that includes the downstream render.  While that gap stays
// inside a couple of display frames nothing is overrunning -- rAF is simply
// running at the refresh rate -- so pace at the floor and publish every time.
// Once it climbs past that, frames ARE overrunning, so budget at twice what the
// last one cost: the browser gets roughly half the wall clock back for
// compositing and input, and playback degrades to a lower frame rate instead of
// locking up the tab.
//
// Budgeting at exactly the measured cost would do nothing -- the callback that
// measures a 73 ms frame arrives 73 ms after it, already clearing a 73 ms
// budget -- so the factor is what actually buys the idle time.
export function animationFrameBudgetMs(publishCostMs) {
  const cost = Number(publishCostMs);
  if (!Number.isFinite(cost) || cost <= SATURATED_ANIMATION_FRAME_MS) {
    return MIN_ANIMATION_FRAME_MS;
  }
  return Math.min(cost * 2, MAX_ANIMATION_FRAME_MS);
}

export function shouldPublishAnimationFrame({ timeMs, publishedAtMs, publishCostMs }) {
  if (!Number.isFinite(publishedAtMs)) {
    return true;
  }
  return (timeMs - publishedAtMs) >= animationFrameBudgetMs(publishCostMs);
}
