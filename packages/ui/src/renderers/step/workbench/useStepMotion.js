import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  animationClipList,
  animationRenderFrame,
  buildDefaultAnimationState,
  findAnimationClip
} from "@text-to-cad/core/common/animationClock.js";
import { articulationControls } from "@text-to-cad/core/common/articulation.js";
import { loadSourceAnimation } from "@text-to-cad/core/common/animationRuntime.js";
import { entryPoseUrl } from "@text-to-cad/core/lib/entryAssets.js";
import { useAnimationClockStore } from "./animationClockStore.js";
import { fileKey as fileKeyOf } from "./entryPaths.js";
import { restoreMotionAnimation, restoreMotionParameters } from "./motionRestore.js";
import { buildParameterValuesCopyText, parseParameterValuesPasteText } from "./parameterControls.js";
import { resolvePoseLoad, stepPoseLogic } from "./poseLoad.js";
import { useStepMotionControls } from "./useStepMotionControls.js";

function sourceAnimationForEntry(entry) { return entry?.animation || null; }
// A routine that bends a tube plays cadgen's skins for the document's current bytes, which
// its URL names: a rebuild that moves the tube loads them again, from rest.
function sourceAnimationKeyForEntry(entry) {
  return sourceAnimationForEntry(entry)
    ? `${fileKeyOf(entry)}:${entry?.animationHash || entry?.documentHash || entry?.hash || "animation"}${entry?.tubeSkinsUrl ? `:${entry.tubeSkinsUrl}` : ""}`
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
 * In: the entry on screen, and the stored view to restore the pose from as the articulation
 * resolves.
 * Out: what the Position panel and the playbar read and call, what the viewport draws a frame
 * from (`animationRuntime`), and `restore`, which the file's view calls once before the
 * first paint. A routine is never restored: every open starts at rest, and the speed and
 * loop it plays with are the tab's (the playbar's Playback settings, the shell's).
 *
 * @param {{ entry: object, fileKey: string, resources: object,
 *   readStored: () => { pose: object | null }, clipboard: object,
 *   reportError: (message: string) => void }} options
 */
export function useStepMotion({ entry, fileKey, resources, readStored, clipboard, reportError }) {
  const animationClock = useAnimationClockStore();
  const { resetAnimationClock, setAnimationClock } = animationClock;
  const readStoredRef = useRef(readStored);
  readStoredRef.current = readStored;
  const reportErrorRef = useRef(reportError);
  reportErrorRef.current = reportError;
  const { moduleUrl, articulation, sourceAnimation, animationKey } = stepMotionSources(entry);

  const [stepModuleLoadState, setStepModuleLoadState] = useState({
    url: "",
    file: "",
    status: "idle",
    error: "",
    definition: null
  });
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

  // A rebuild writes this file's sidecar again (a new version, bound to the new document), and its
  // articulation arrives again: until it lands, what the last one declared stays in hand, so the
  // model stays posed and Position stays the tool. Whether the pose outlives it is the load's to say.
  const kinematicsInHand = stepModuleLoadState.url === moduleUrl ||
    (Boolean(moduleUrl) && stepModuleLoadState.file === fileKey && stepModuleLoadState.status === "ready");
  const definition = kinematicsInHand ? stepModuleLoadState.definition : null;
  // The routines the same way: a rebuild that changed them reads them again, and until the new ones
  // land the ones in hand stay, with the model at rest, so the Animation tool stays up and keeps
  // its routine.
  const animationInHand = animationLoadState.url === animationKey ||
    (Boolean(animationKey) && animationLoadState.file === fileKey && animationLoadState.status === "ready");
  const clips = animationInHand ? animationLoadState.clips : null;
  const animationStatus = animationKey ? (animationLoadState.url === animationKey ? animationLoadState.status : "loading") : "idle";
  const animationLoadError = animationLoadState.url === animationKey ? animationLoadState.error : "";
  const status = moduleUrl ? (kinematicsInHand ? stepModuleLoadState.status : "loading") : "idle";
  const error = kinematicsInHand ? stepModuleLoadState.error : "";
  const loading = Boolean(moduleUrl && status === "loading");

  // The pose the person PICKED, which the dropdown shows until they move a DOF. Without
  // it the name is re-derived from the values every frame, so a pose read as "None"
  // for the whole of its own transition and only became itself once it arrived.
  const [appliedPoseName, setAppliedStepPoseName] = useState("");

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    if (!moduleUrl) {
      setStepModuleLoadState({
        url: "",
        file: fileKey,
        status: "idle",
        error: "",
        definition: null
      });
      stepModuleParameterValuesRef.current = {};
      setStepModuleParameterValues({});
      return () => {
        cancelled = true;
        controller.abort();
      };
    }

    // The same file's sidecar read again keeps the last one's definition and values in hand
    // (above) while it loads; only a first load starts from nothing.
    const reloading = stepModuleLoadState.file === fileKey && stepModuleLoadState.status === "ready";
    const poseLogicInHand = reloading ? stepPoseLogic(stepModuleLoadState.definition) : "";
    if (!reloading) {
      setStepModuleLoadState({
        url: moduleUrl,
        file: fileKey,
        status: "loading",
        error: "",
        definition: null
      });
      stepModuleParameterValuesRef.current = {};
      setStepModuleParameterValues({});
    }

    // The articulation is cadgen's, inline on the entry: nothing is fetched or validated here.
    // It resolves on the next tick, as a load does, so a rebuild's pose carries over below.
    Promise.resolve().then(() => (articulation ? { url: moduleUrl, articulation } : null)).then((definition) => {
      if (cancelled) {
        return;
      }
      // A reload whose joints and named poses are unchanged keeps the values in hand, and the
      // named pose chosen with them; one that changed them starts at the new defaults, with no
      // attempt to fit the old pose onto the new joints. A first load reads the stored pose,
      // against the articulation as it is now.
      const kept = reloading && stepPoseLogic(definition) === poseLogicInHand;
      const restoredPose = kept ? { parameterValues: stepModuleParameterValuesRef.current }
        : reloading ? null : readStoredRef.current().pose;
      // An entry with no articulation resolves to a NULL definition — an animation-only model
      // has a sidecar and lands here — so the ready state is committed from one place that
      // expects that (workbench/poseLoad); the Position section is then absent, not empty.
      const resolved = resolvePoseLoad({
        url: moduleUrl,
        definition,
        restored: restoredPose
      });
      setStepModuleLoadState({ ...resolved.loadState, file: fileKey });
      // A first load restores the stored pose whatever the transport opened on: the clip a
      // model's routines open with is not a routine anyone ran, and whether the clips or the
      // kinematics load first is a race. Only a reload weighs a routine that owns the pose.
      const parameterValues = restoreMotionParameters(definition, resolved.parameterValues,
        reloading ? animationStateRef.current : null);
      stepModuleParameterValuesRef.current = parameterValues;
      setStepModuleParameterValues(parameterValues);
      if (!kept) setAppliedStepPoseName("");
    }).catch((error) => {
      if (cancelled) {
        return;
      }
      setStepModuleLoadState({
        url: moduleUrl,
        file: fileKey,
        status: "error",
        error: error instanceof Error ? error.message : String(error),
        definition: null
      });
      stepModuleParameterValuesRef.current = {};
      setStepModuleParameterValues({});
    });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [fileKey, entry, moduleUrl]);

  // The animation half loads the keyframes in the selected sidecar. A document
  // with no animation resolves to no clips and no Animation tool, and a broken
  // one reports its own error without disturbing Position.
  //
  // It is keyed on the animation's own identity (`animationKey`: the file and the hash of the
  // routines' keyframes), never on the entry: an update of the model that leaves its routines as
  // they were neither stops nor rewinds one that is playing, and only a changed routine is
  // loaded again, from rest. The keyframes are read when the key changes.
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
  // Progressive publish (design/viewer-memory.md §6): a STEP package paints
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

  // Copy and Paste of the Position values, as text a person can keep and paste back.
  const { applyStepModuleParameterValues } = commands;
  const copyParameters = useCallback(async () => {
    if (!articulationControls(definition?.articulation).length) {
      reportErrorRef.current("No STEP parameters to copy");
      return;
    }
    try {
      await clipboard.writeText(buildParameterValuesCopyText(definition, stepModuleParameterValues));
    } catch (error) {
      reportErrorRef.current(error instanceof Error ? error.message : "Clipboard write failed");
    }
  }, [clipboard, definition, stepModuleParameterValues]);
  const pasteParameters = useCallback(async () => {
    if (!articulationControls(definition?.articulation).length) {
      reportErrorRef.current("No STEP parameters to paste");
      return;
    }
    try {
      const clipboardText = await clipboard.readText();
      const { values } = parseParameterValuesPasteText(definition, clipboardText, {
        label: "STEP parameter",
        unknownLabel: "STEP parameter"
      });
      applyStepModuleParameterValues(values);
    } catch (error) {
      reportErrorRef.current(error instanceof Error ? error.message : "Clipboard paste failed");
    }
  }, [applyStepModuleParameterValues, clipboard, definition]);

  // The stored pose, once, before the first paint (the file's view calls it). The values are
  // normalized against the articulation when it resolves.
  const restore = (restored) => {
    const values = restored.pose?.parameterValues;
    if (values) {
      stepModuleParameterValuesRef.current = values;
      setStepModuleParameterValues(values);
    }
  };

  // What the Position panel and the playbar read and call.
  const positionControls = {
    status, error, definition,
    parameterValues: stepModuleParameterValues,
    onParameterChange: commands.handleStepModuleParameterChange,
    onResetParameters: commands.handleResetStepModuleParameters,
    onApplyPose: commands.handleApplyPose,
    activePose: animationState.enabled !== false ? "" : appliedPoseName,
    positionActive: !animationRuntime,
    onResetMotion: commands.resetMotion,
    onCopyParams: copyParameters,
    onPasteParams: pasteParameters
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
    resetModel: commands.resetMotion,
    // The kit's playbar reads its time from the runtime it is handed, not from a context: the
    // old STEP-only bar did, which is why this object never carried one. It is the same clock
    // the pose pass writes per frame, so the scrubber re-renders and nothing else does.
    clock: animationClock
  };

  return {
    definition, loading, parameterValues: stepModuleParameterValues,
    animationState, animationStateRef, animationRuntime, animationError, positionControls, animationControls,
    onParameterChange: commands.handleStepModuleParameterChange, onPlayToggle: commands.handleAnimationPlayToggle,
    releaseAnimation: commands.releaseAnimation, restore
  };
}
