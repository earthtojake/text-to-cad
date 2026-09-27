import assert from "node:assert/strict";
import { test } from "node:test";

import {
  MAX_ANIMATION_FRAME_MS,
  MIN_ANIMATION_FRAME_MS,
  advanceAnimationElapsed,
  animationClipList,
  animationFrameBudgetMs,
  animationRenderFrame,
  buildDefaultAnimationState,
  findAnimationClip,
  firstAnimationClipId,
  hasAnimationClips,
  resolveAnimationFrame,
  restoreAnimationState,
  shouldPublishAnimationFrame
} from "./animationClock.js";

const CLIPS = {
  meshCycle: { id: "meshCycle", label: "Mesh cycle", duration: 6, loop: true, update() {} },
  inspectExplode: { id: "inspectExplode", label: "Explode inspect", duration: 5, loop: true, update() {} }
};

test("clips list in declaration order with their transport metadata", () => {
  assert.deepEqual(animationClipList(CLIPS), [
    { id: "meshCycle", label: "Mesh cycle", duration: 6, loop: true },
    { id: "inspectExplode", label: "Explode inspect", duration: 5, loop: true }
  ]);
  assert.equal(hasAnimationClips(CLIPS), true);
  assert.equal(hasAnimationClips({}), false);
  assert.equal(firstAnimationClipId(CLIPS), "meshCycle");
});

test("a model opens on its first declared clip, gated on and paused", () => {
  // There is no "no clip" selection any more: the transport's idle state is the
  // Animation section's gate switch, so the picker always names a real clip and
  // the default selection is the model's first one.
  assert.deepEqual(buildDefaultAnimationState(CLIPS), {
    activeClipId: "meshCycle",
    enabled: true,
    playing: false,
    elapsedSec: 0,
    speed: 1,
    loopEnabled: true
  });
  // The opening clip's own loop preference comes with it, exactly as picking it
  // from the select would set.
  assert.equal(
    buildDefaultAnimationState({
      once: { id: "once", label: "Once", duration: 2, loop: false, update() {} }
    }).loopEnabled,
    false
  );
  // Called before the clips compile (the file-switch reset) there is nothing to
  // select yet, and the load effect restores against the real clips.
  assert.equal(buildDefaultAnimationState().activeClipId, "");
  assert.equal(findAnimationClip(CLIPS, ""), null);
  assert.equal(findAnimationClip(CLIPS, "meshCycle")?.id, "meshCycle");
});

test("the gate, not the selection, decides whether a clip drives the model", () => {
  // The render pass gets a frame or it gets null, and null IS the rest scene:
  // the evaluator never runs and the model shows exactly what the Pose tab set.
  // That is the behaviour the removed "No clip" entry used to produce, now on a
  // switch, so turning animation off costs the render path no new code.
  assert.deepEqual(
    animationRenderFrame({ enabled: true, clip: CLIPS.meshCycle, elapsedSec: 2, playing: true }),
    { clip: CLIPS.meshCycle, elapsedSec: 2, playing: true }
  );
  assert.equal(
    animationRenderFrame({ enabled: false, clip: CLIPS.meshCycle, elapsedSec: 2, playing: true }),
    null
  );
  // A selection with no clip behind it (clips still compiling) draws nothing either.
  assert.equal(animationRenderFrame({ enabled: true, clip: null }), null);
});

test("a still-frame request resolves to the viewer's own render-pass shape", () => {
  // The snapshot's `animation: {clip, time}` becomes exactly what the viewer's
  // Animation tab hands its effects pass — the same clip record, the time as
  // elapsedSec, not playing — so the still IS the frame the viewer shows there.
  assert.deepEqual(
    resolveAnimationFrame(CLIPS, { clip: "inspectExplode", time: 2.5 }),
    { clip: CLIPS.inspectExplode, elapsedSec: 2.5, playing: false }
  );
  // Time defaults to the start of the clip, and is NOT clamped or wrapped here:
  // looping and clamping belong to the evaluator, for stills and playback alike.
  assert.equal(resolveAnimationFrame(CLIPS, { clip: "meshCycle" }).elapsedSec, 0);
  assert.equal(resolveAnimationFrame(CLIPS, { clip: "meshCycle", time: 99 }).elapsedSec, 99);
});

test("a still-frame request for an unknown clip names the declared clips", () => {
  assert.throws(
    () => resolveAnimationFrame(CLIPS, { clip: "orbit" }),
    /Unknown animation clip: orbit\. This model declares: meshCycle, inspectExplode/
  );
  assert.throws(
    () => resolveAnimationFrame({}, { clip: "orbit" }),
    /Unknown animation clip: orbit\. This model declares no animation clips/
  );
  // A nameless request is a bug, not a request for a rest frame.
  assert.throws(() => resolveAnimationFrame(CLIPS, {}), /requires a clip name/);
  assert.throws(() => resolveAnimationFrame(CLIPS, { clip: "meshCycle", time: -1 }), /seconds >= 0/);
  assert.throws(() => resolveAnimationFrame(CLIPS, { clip: "meshCycle", time: "soon" }), /seconds >= 0/);
});

test("a restored session keeps the clock but never resumes playback", () => {
  assert.deepEqual(
    restoreAnimationState({ activeClipId: "meshCycle", playing: true, elapsedSec: 2.5, speed: 9, loopEnabled: false }, CLIPS),
    { activeClipId: "meshCycle", enabled: true, playing: false, elapsedSec: 2.5, speed: 3, loopEnabled: false }
  );
  // The gate is restored with the rest of the transport: a file the user
  // switched to rest must not reopen animating.
  assert.equal(
    restoreAnimationState({ activeClipId: "meshCycle", enabled: false }, CLIPS).enabled,
    false
  );
  // A clip the model no longer ships used to fall back to rest. Rest is a gate
  // now, so a selection that DIED falls back to the first clip WITH THE GATE
  // OFF: the selection stays legible and the model still does not animate
  // something the user never picked.
  assert.deepEqual(
    restoreAnimationState({ activeClipId: "gone", elapsedSec: 4 }, CLIPS),
    { activeClipId: "meshCycle", enabled: false, playing: false, elapsedSec: 0, speed: 1, loopEnabled: true }
  );
  // Elapsed past the clip's end clamps to its duration.
  assert.equal(restoreAnimationState({ activeClipId: "inspectExplode", elapsedSec: 99 }, CLIPS).elapsedSec, 5);
});

test("a slice with no selection recorded opens the model normally", () => {
  // `activeClipId: ""` is NOT a dead clip and not a retired sentinel: it is what
  // this module returns before a model's clips compile, so the file-switch reset
  // holds it and the debounced session save can persist it mid-load. Reading it
  // as "the user chose rest" gated a model's FIRST open off — clips that take
  // longer than the save debounce to compile opened switched off, and the off
  // was then persisted. It says nothing about the gate, so the model opens
  // exactly as it would with no session at all. A slice written before the gate
  // existed lands here too, and opens gated ON.
  assert.deepEqual(
    restoreAnimationState({ activeClipId: "", elapsedSec: 4 }, CLIPS),
    { activeClipId: "meshCycle", enabled: true, playing: false, elapsedSec: 0, speed: 1, loopEnabled: true }
  );
  // The gate the slice DID record still wins on that path.
  assert.equal(restoreAnimationState({ activeClipId: "", enabled: false }, CLIPS).enabled, false);
});

test("transport preferences survive a selection that does not resolve", () => {
  // Speed and loop belong to the slice, not to the clip: whether the stored id
  // resolves says nothing about how fast playback runs or whether it repeats.
  // Both are reachable with no clip in hand — a file switch restores against
  // null clips on purpose, because the previous file's are still loaded.
  for (const clips of [CLIPS, null]) {
    assert.deepEqual(
      restoreAnimationState({ activeClipId: "gone", speed: 2.5, loopEnabled: false }, clips),
      {
        activeClipId: clips ? "meshCycle" : "",
        enabled: clips ? false : true,
        playing: false,
        elapsedSec: 0,
        speed: 2.5,
        loopEnabled: false
      }
    );
  }
  // With no clips at all there is nothing to call dead, so the gate is the
  // slice's own and the real clips decide the selection once they compile.
  assert.equal(
    restoreAnimationState({ activeClipId: "meshCycle", enabled: true }, null).enabled,
    true
  );
});

test("a restored clip carries its OWN loop preference, not the opening clip's", () => {
  const clips = {
    meshCycle: CLIPS.meshCycle,
    once: { id: "once", label: "Once", duration: 2, loop: false, update() {} }
  };
  // The slice names `once`, which declares loop: false. Falling back to the
  // FIRST clip's preference here would loop a clip authored not to.
  assert.equal(restoreAnimationState({ activeClipId: "once" }, clips).loopEnabled, false);
  assert.equal(restoreAnimationState({ activeClipId: "meshCycle" }, clips).loopEnabled, true);
  // A recorded preference still wins over the clip's default.
  assert.equal(
    restoreAnimationState({ activeClipId: "once", loopEnabled: true }, clips).loopEnabled,
    true
  );
});

test("the clock wraps when looping and stops at the end when not", () => {
  assert.deepEqual(
    advanceAnimationElapsed({ elapsedSec: 5.5, deltaSec: 1, speed: 1, duration: 6, loopEnabled: true }),
    { elapsedSec: 0.5, playing: true }
  );
  assert.deepEqual(
    advanceAnimationElapsed({ elapsedSec: 5.5, deltaSec: 1, speed: 1, duration: 6, loopEnabled: false }),
    { elapsedSec: 6, playing: false }
  );
  // Speed scales the delta, and is clamped to the transport's range.
  assert.equal(
    advanceAnimationElapsed({ elapsedSec: 0, deltaSec: 1, speed: 9, duration: 100, loopEnabled: false }).elapsedSec,
    3
  );
});

// Frame pacing exists because publishing a frame costs far more than the tick
// that publishes it: on a large assembly the store notify re-renders the render
// pane, re-evaluates the clip across every display record and redraws the
// scene. Measured on the F-14D teardown (2,392 display records) a published
// frame cost ~73 ms of main-thread work, so publishing on every rAF left the
// thread saturated -- the clock advanced but the browser never got a slot to
// composite, and playback read as frozen while scrubbing the same clip still
// worked, because a scrub pays that cost once.

test("an unsaturated model publishes on every display frame", () => {
  // A 16.7 ms gap is rAF running at the refresh rate, not work overrunning, so
  // the budget floors and every callback publishes. Pacing must not cost fps to
  // the models that never had a problem.
  const publishCostMs = 16.7;
  assert.equal(animationFrameBudgetMs(publishCostMs), MIN_ANIMATION_FRAME_MS);
  assert.equal(
    shouldPublishAnimationFrame({ timeMs: 16.7, publishedAtMs: 0, publishCostMs }),
    true
  );
});

test("a saturated model idles about as long as its last frame cost", () => {
  const publishCostMs = 73;
  assert.equal(animationFrameBudgetMs(publishCostMs), 146);
  // The callback that measures the cost arrives at +73 ms and must NOT publish:
  // budgeting at exactly the measured cost would insert no idle time at all.
  assert.equal(
    shouldPublishAnimationFrame({ timeMs: 73, publishedAtMs: 0, publishCostMs }),
    false
  );
  // Publishing resumes once the thread has had a comparable stretch free.
  assert.equal(
    shouldPublishAnimationFrame({ timeMs: 150, publishedAtMs: 0, publishCostMs }),
    true
  );
});

test("the first frame of a playback publishes immediately", () => {
  // publishedAtMs starts unset: there is no previous frame to pace against, and
  // waiting a budget before the first one would stall the opening of every clip.
  assert.equal(
    shouldPublishAnimationFrame({ timeMs: 0, publishedAtMs: NaN, publishCostMs: 0 }),
    true
  );
});

test("a catastrophic frame still leaves the clip advancing", () => {
  // Without a ceiling, one 2 s hitch would pace the next frame 4 s out and the
  // animation would look stopped rather than slow.
  assert.equal(animationFrameBudgetMs(2000), MAX_ANIMATION_FRAME_MS);
  assert.equal(
    shouldPublishAnimationFrame({ timeMs: 260, publishedAtMs: 0, publishCostMs: 2000 }),
    true
  );
});

test("an unmeasured frame cost falls back to the floor", () => {
  // publishCostMs is 0 until the first publish has been measured, and a NaN gap
  // must not park the budget at NaN and block playback forever.
  assert.equal(animationFrameBudgetMs(0), MIN_ANIMATION_FRAME_MS);
  assert.equal(animationFrameBudgetMs(NaN), MIN_ANIMATION_FRAME_MS);
  assert.equal(animationFrameBudgetMs(-5), MIN_ANIMATION_FRAME_MS);
});
