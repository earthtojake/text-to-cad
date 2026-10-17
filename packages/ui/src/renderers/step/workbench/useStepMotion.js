import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  animationClipList,
  animationRenderFrame,
  buildDefaultAnimationState,
  findAnimationClip
} from "@text-to-cad/core/common/animationClock.js";
import { loadSourceAnimation } from "@text-to-cad/core/common/animationRuntime.js";
import { entryPoseUrl } from "@text-to-cad/core/lib/entryAssets.js";
import { useAnimationClockStore } from "./animationClockStore.js";
import { jsonDigest } from "./canonicalJson.js";
import { fileKey as fileKeyOf } from "./entryPaths.js";
import { restoreMotionAnimation, restoreMotionParameters, stepPoseLogic } from "./motionRestore.js";
import { useStepMotionControls } from "./useStepMotionControls.js";

function sourceAnimationForEntry(entry) { return entry?.animation || null; }
// The routines are named by their keyframes: one digest of the baked clips themselves, so a
// build's preview and the file it saves, which carry the same keyframes, are one routine, and only
// a changed clip is read again. Digested once per animation object, which an entry keeps across
// renders. A routine that bends a tube plays cadgen's skins for the document's current bytes, which
// its URL names: a rebuild that moves the tube loads them again, from rest.
const animationDigests = new WeakMap();
function animationDigest(animation) {
  if (!animationDigests.has(animation)) animationDigests.set(animation, jsonDigest(animation));
  return animationDigests.get(animation);
}
function sourceAnimationKeyForEntry(entry) {
  const animation = sourceAnimationForEntry(entry);
  return animation
    ? `${fileKeyOf(entry)}:${animationDigest(animation)}${entry?.tubeSkinsUrl ? `:${entry.tubeSkinsUrl}` : ""}`
    : "";
}

/**
 * Where a STEP entry's motion comes from: the articulation cadgen resolved from its sidecar's
 * kinematics (inline on the entry, versioned by `poseUrl`), and the routines' baked keyframes.
 */
export function stepMotionSources(entry) {
  const moduleUrl = entryPoseUrl(entry);
  const sourceAnimation = sourceAnimationForEntry(entry);
  return {
    moduleUrl,
    articulation: moduleUrl && entry?.articulation && typeof entry.articulation === "object" ? entry.articulation : null,
    sourceAnimation,
    animationKey: sourceAnimation ? sourceAnimationKeyForEntry(entry) : ""
  };
}

/**
 * A STEP's motion: its articulation and the Position values over it, and its routines and
 * the playback over them — resolved and held apart (a model may ship either, both, or neither),
 * with one command boundary over both (`useStepMotionControls`).
 *
 * In: the entry on screen, and the stored view, whose pose the file's first articulation takes.
 * Out: what the Position panel and the playbar read and call, and what the viewport draws a
 * frame from (`animationRuntime`). A routine is never restored: every open starts at rest, and
 * the speed and loop it plays with are the shell's (the Animation tool's, the file's; preview's,
 * its own).
 *
 * @param {{ entry: object, fileKey: string, resources: object,
 *   readStored: () => { pose: object | null } }} options
 */
export function useStepMotion({ entry, fileKey, resources, readStored }) {
  const animationClock = useAnimationClockStore();
  const { resetAnimationClock, setAnimationClock } = animationClock;
  const readStoredRef = useRef(readStored);
  readStoredRef.current = readStored;
  const { moduleUrl, articulation, sourceAnimation, animationKey } = stepMotionSources(entry);

  // The articulation is cadgen's, inline on the entry: the definition is the entry's own, in hand
  // in the render the entry arrives in, so a rebuild never leaves Position without one.
  const definition = useMemo(() => (articulation ? { url: moduleUrl, articulation } : null), [moduleUrl, articulation]);
  const [stepModuleParameterValues, setStepModuleParameterValues] = useState({});
  // The ANIMATION system, loaded and held entirely apart from the kinematics
  // state above: kinematics and choreography are independent declarations in
  // the embedded source sidecar, and a model may ship either,
  // both, or neither.
  const [animationLoadState, setAnimationLoadState] = useState({
    url: "",
    file: "",
    status: "idle",
    error: "",
    clips: null
  });
  const [animationState, setAnimationState] = useState(buildDefaultAnimationState);
  const stepModuleParameterValuesRef = useRef(stepModuleParameterValues);
  const animationStateRef = useRef(animationState);
  const motionRevisionRef = useRef(0);

  // A rebuild that changed the routines reads them again, and until the new ones land the ones in
  // hand stay, with the model at rest, so the Animation tool stays up and keeps its routine.
  const animationInHand = animationLoadState.url === animationKey ||
    (Boolean(animationKey) && animationLoadState.file === fileKey && animationLoadState.status === "ready");
  const clips = animationInHand ? animationLoadState.clips : null;
  const animationStatus = animationKey ? (animationLoadState.url === animationKey ? animationLoadState.status : "loading") : "idle";
  const animationLoadError = animationLoadState.url === animationKey ? animationLoadState.error : "";

  // The pose the person PICKED, which the dropdown shows until they move a DOF. Without
  // it the name is re-derived from the values every frame, so a pose read as "None"
  // for the whole of its own transition and only became itself once it arrived.
  const [appliedPoseName, setAppliedStepPoseName] = useState("");

  // The values over the definition, fitted whenever it changes and before the paint that shows
  // it. A rebuild whose joints and named poses are unchanged keeps the values in hand, and the
  // named pose chosen with them; one that changed them starts at the new defaults, with no attempt
  // to fit the old pose onto the new joints. The file's first articulation takes the stored pose,
  // within its limits, whatever the transport opened on: the clip a model's routines open with is
  // not a routine anyone ran, so only a rebuild weighs a routine that owns the pose. An entry with
  // no articulation (an animation-only model) has no values, and no Position.
  const fittedRef = useRef(null);
  useLayoutEffect(() => {
    const previous = fittedRef.current;
    fittedRef.current = definition && { file: fileKey, definition };
    if (!definition) {
      stepModuleParameterValuesRef.current = {};
      setStepModuleParameterValues({});
      return;
    }
    const rebuilt = previous?.file === fileKey;
    const kept = rebuilt && stepPoseLogic(definition) === stepPoseLogic(previous.definition);
    const values = kept ? stepModuleParameterValuesRef.current
      : rebuilt ? null : readStoredRef.current().pose?.parameterValues;
    const parameterValues = restoreMotionParameters(definition, values, rebuilt ? animationStateRef.current : null);
    stepModuleParameterValuesRef.current = parameterValues;
    setStepModuleParameterValues(parameterValues);
    if (!kept) setAppliedStepPoseName("");
  }, [definition, fileKey]);

  // The animation half loads the keyframes in the selected sidecar. A document
  // with no animation resolves to no clips and no Animation tool, and a broken
  // one reports its own error without disturbing Position.
  //
  // It is keyed on the animation's own identity (`animationKey`: the file and a digest of the
  // routines' keyframes), never on the entry: an update of the model that leaves its routines as
  // they were -- a build's preview, and the save that confirms it -- neither stops nor rewinds one
  // that is playing, and only a changed routine is loaded again, from rest. The keyframes are read
  // when the key changes.
  const animationSourceRef = useRef({ sourceAnimation, entry, resources });
  animationSourceRef.current = { sourceAnimation, entry, resources };
  // Putting the routine down (`useStepMotionControls`), which a reload below does: bound once the
  // commands are made.
  const releaseAnimationRef = useRef(null);
  useEffect(() => {
    const { sourceAnimation, entry, resources } = animationSourceRef.current;
    let cancelled = false;
    const controller = new AbortController();
    const resetAnimation = () => {
      const nextState = buildDefaultAnimationState();
      animationStateRef.current = nextState;
      setAnimationState(nextState);
      resetAnimationClock();
    };
    // The same file's routines read again, because a rebuild changed or removed them: the model
    // goes to rest as it does when a routine is put down, Position's values back, and the routine
    // chosen keeps its place, with its speed and loop, for the new ones to restore against.
    const reloading = animationLoadState.file === fileKey && animationLoadState.status === "ready";
    if (reloading) releaseAnimationRef.current?.();

    if (!animationKey || !sourceAnimation) {
      setAnimationLoadState({ url: "", file: fileKey, status: "idle", error: "", clips: null });
      resetAnimation();
      return () => {
        cancelled = true;
        controller.abort();
      };
    }

    if (!reloading) {
      setAnimationLoadState({
        url: animationKey,
        file: fileKey,
        status: "loading",
        error: "",
        clips: null
      });
      resetAnimation();
    }

    loadSourceAnimation({ animation: sourceAnimation }, {
      signal: controller.signal, tubeSkinsUrl: entry?.tubeSkinsUrl || "", resources
    })
      .then((animationModule) => {
        if (cancelled) {
          return;
        }
        const clips = animationModule?.clips || {};
        setAnimationLoadState({
          url: animationKey,
          file: fileKey,
          status: "ready",
          error: "",
          clips
        });
        const nextState = restoreMotionAnimation(animationStateRef.current, clips);
        animationStateRef.current = nextState;
        setAnimationState(nextState);
        setAnimationClock(nextState.elapsedSec);
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        setAnimationLoadState({
          url: animationKey,
          file: fileKey,
          status: "error",
          error: error instanceof Error ? error.message : String(error),
          clips: null
        });
        resetAnimation();
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [fileKey, animationKey]);


  const clipList = useMemo(() => animationClipList(clips), [clips]);
  const activeClip = useMemo(() => findAnimationClip(clips, animationState.activeClipId), [clips, animationState.activeClipId]);
  // Progressive publish (packages/ui/docs/loading.md, section 2): a STEP package paints
  // while it loads, and the partial states carry assemblyInteractionReady=false.
  // Animation attaches on the FIRST publish and stays live: a track names
  // occurrence ids, so it drives the ones present and the rest as they arrive.
  // What the viewport needs to draw one animated frame: the clip and a
  // time. The render pane swaps in the live clock while playing; everything else
  // about playback stays out of the render path.
  //
  // `enabled` is internal pose ownership: paused animation holds its frame;
  // editing Position hands control back to kinematics. It is not a UI gate.
  const animationRuntime = useMemo(() => animationRenderFrame({
    enabled: animationState.enabled !== false,
    clip: activeClip,
    elapsedSec: animationState.elapsedSec,
    playing: animationState.playing
  }), [animationState.elapsedSec, animationState.enabled, animationState.playing, activeClip]);

  // A named pose is a full configuration, not a patch: every DOF the preset
  // does not mention returns to 0 (the artifact as written), so two presets in
  // a row can never leave a joint behind from the first.
  const commands = useStepMotionControls({
    selectedStepModuleDefinition: definition, selectedAnimationClips: clips, selectedActiveAnimationClip: activeClip,
    animationState, animationStateRef, setAnimationState, stepModuleParameterValuesRef,
    setStepModuleParameterValues, setAppliedStepPoseName, motionRevisionRef
  });
  releaseAnimationRef.current = commands.releaseAnimation;

  const animationError = animationLoadError;

  // What the Position panel and the playbar read and call.
  const positionControls = {
    definition,
    parameterValues: stepModuleParameterValues,
    onParameterChange: commands.handleStepModuleParameterChange,
    onResetParameters: commands.handleResetStepModuleParameters,
    onApplyPose: commands.handleApplyPose,
    activePose: animationState.enabled !== false ? "" : appliedPoseName,
    positionActive: !animationRuntime,
    onResetMotion: commands.resetMotion
  };
  const animationControls = {
    status: animationStatus,
    error: animationError,
    clips: clipList,
    activeClipId: animationState.activeClipId,
    enabled: animationState.enabled !== false,
    playing: animationState.playing,
    elapsedSec: animationState.elapsedSec,
    speed: animationState.speed,
    loopEnabled: animationState.loopEnabled,
    onClipSelect: commands.handleAnimationClipSelect,
    onPlayToggle: commands.handleAnimationPlayToggle,
    onRestart: commands.handleAnimationRestart,
    onScrub: commands.handleAnimationScrub,
    onSpeedChange: commands.handleAnimationSpeedChange,
    onLoopToggle: commands.handleAnimationLoopToggle,
    onRelease: commands.releaseAnimation,
    savePlayback: commands.savePlayback,
    resetPlayback: commands.resetPlayback,
    restorePlayback: commands.restorePlayback,
    resetModel: commands.resetMotion,
    // The kit's playbar reads its time from the runtime it is handed, not from a context: the
    // old STEP-only bar did, which is why this object never carried one. It is the same clock
    // the pose pass writes per frame, so the scrubber re-renders and nothing else does.
    clock: animationClock
  };

  return {
    definition, parameterValues: stepModuleParameterValues,
    animationState, animationStateRef, animationRuntime, animationError, positionControls, animationControls,
    onParameterChange: commands.handleStepModuleParameterChange, onPlayToggle: commands.handleAnimationPlayToggle,
    releaseAnimation: commands.releaseAnimation
  };
}
