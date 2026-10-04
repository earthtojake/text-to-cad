import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import {
  animationClipList,
  animationRenderFrame,
  buildDefaultAnimationState,
  findAnimationClip
} from "@text-to-cad/core/common/animationClock.js";
import {
  kinematicsModuleDefinitionFromSidecar,
  loadKinematicsModuleDefinition
} from "@text-to-cad/core/common/kinematicsModule.js";
import { loadSourceAnimation, validateAnimationClips } from "@text-to-cad/core/common/renderModule.js";
import { validateSourceSidecar } from "@text-to-cad/core/common/sourceSidecar.js";
import { entryPoseUrl } from "@text-to-cad/core/lib/entryAssets.js";
import { tolerantAnimationClip } from "../components/workbench/hooks/packageProgressiveLoad.js";
import { useAnimationClockStore } from "./animationClockStore.js";
import { cadPathForEntry, fileKey as fileKeyOf } from "./entryPaths.js";
import { restoreMotionAnimation, restoreMotionParameters } from "./motionRestore.js";
import { buildParameterValuesCopyText, parseParameterValuesPasteText } from "./parameterControls.js";
import { resolveStepModuleLoad, stepPoseLogic } from "./stepModuleLoad.js";
import { stepModuleRequiresTopology } from "./topologyCapabilities.js";
import { useStepMotionControls } from "./useStepMotionControls.js";

function sourceAnimationForEntry(entry) { return entry?.sourceSidecar?.animation || null; }
function sourceAnimationKeyForEntry(entry) {
  return sourceAnimationForEntry(entry) ? `${fileKeyOf(entry)}:${entry?.animationHash || entry?.documentHash || entry?.hash || "animation"}` : "";
}

/**
 * Where a STEP entry's motion comes from: its sidecar's kinematics module, the path the module
 * poses, and the routine source embedded in the sidecar.
 */
export function stepMotionSources(entry) {
  const moduleUrl = entryPoseUrl(entry);
  const sourceAnimation = sourceAnimationForEntry(entry);
  return {
    moduleUrl,
    cadPath: moduleUrl ? cadPathForEntry(entry) : "",
    sourceAnimation,
    animationKey: sourceAnimation ? sourceAnimationKeyForEntry(entry) : ""
  };
}

/**
 * A STEP's motion: its kinematics module and the Position values over it, and its routines and
 * the playback over them — loaded and held apart (a model may ship either, both, or neither),
 * with one command boundary over both (`useStepMotionControls`).
 *
 * In: the entry on screen, the model it moves (a partial progressive model plays tolerantly and
 * is not validated), and the stored view to restore the pose from as the sidecar compiles.
 * Out: what the Position panel and the playbar read and call, what the viewport draws a frame
 * from (`animationRuntime`), and `restore`, which the file's view calls once before the
 * first paint. A routine is never restored: every open starts at rest, and the speed and
 * loop it plays with are the tab's (the shell's Playback settings).
 *
 * @param {{ entry: object, fileKey: string, resources: object, meshData: object | null, meshPartial: boolean,
 *   readStored: () => { pose: object | null }, clipboard: object,
 *   reportError: (message: string) => void }} options
 */
export function useStepMotion({ entry, fileKey, resources, meshData, meshPartial, readStored, clipboard, reportError }) {
  const animationClock = useAnimationClockStore();
  const { resetAnimationClock, setAnimationClock } = animationClock;
  const readStoredRef = useRef(readStored);
  readStoredRef.current = readStored;
  const reportErrorRef = useRef(reportError);
  reportErrorRef.current = reportError;
  const { moduleUrl, cadPath, sourceAnimation, animationKey } = stepMotionSources(entry);

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
    status: "idle",
    error: "",
    clips: null
  });
  const [animationState, setAnimationState] = useState(buildDefaultAnimationState);
  const stepModuleParameterValuesRef = useRef(stepModuleParameterValues);
  const animationStateRef = useRef(animationState);
  const motionRevisionRef = useRef(0);

  // A rebuild writes this file's sidecar again (a new version, bound to the new document), and it is
  // read again: until it lands, what the last one declared stays in hand, so the model stays posed
  // and Position stays the tool while it loads. Whether the pose outlives it is the load's to say.
  const kinematicsInHand = stepModuleLoadState.url === moduleUrl ||
    (Boolean(moduleUrl) && stepModuleLoadState.file === fileKey && stepModuleLoadState.status === "ready");
  const definition = kinematicsInHand ? stepModuleLoadState.definition : null;
  const clips = animationLoadState.url === animationKey ? animationLoadState.clips : null;
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

    const loadMotionRevision = motionRevisionRef.current;
    const modulePromise = entry?.sourceSidecar
      ? Promise.resolve().then(() => kinematicsModuleDefinitionFromSidecar(
          validateSourceSidecar(entry.sourceSidecar, {
            url: moduleUrl || entry.file,
            documentHash: entry.documentHash,
          }),
          { cadPath: cadPath, url: moduleUrl }
        ))
      : loadKinematicsModuleDefinition(moduleUrl, {
          signal: controller.signal, resources: resources, cadPath: cadPath, documentHash: entry?.documentHash,
        });
    modulePromise.then((definition) => {
      if (cancelled) {
        return;
      }
      // A reload whose joints and named poses are unchanged keeps the values in hand, and the
      // named pose chosen with them; one that changed them starts at the new defaults, with no
      // attempt to fit the old pose onto the new joints. A first load reads the stored pose,
      // against the sidecar as it is now.
      const kept = reloading && stepPoseLogic(definition) === poseLogicInHand;
      const restoredPose = kept ? { parameterValues: stepModuleParameterValuesRef.current }
        : reloading ? null : readStoredRef.current().pose;
      // A sidecar with no kinematics section resolves to a NULL definition —
      // an animation-only model has a sidecar and lands here — so the ready
      // state is committed from one place that expects that (see
      // workbench/stepModuleLoad); the Position section is then absent, not empty.
      const resolved = resolveStepModuleLoad({
        url: moduleUrl,
        definition,
        restored: restoredPose
      });
      setStepModuleLoadState({ ...resolved.loadState, file: fileKey });
      const parameterValues = restoreMotionParameters(definition, resolved.parameterValues, animationStateRef.current);
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
  }, [fileKey, entry, cadPath, moduleUrl]);

  // The animation half compiles the exact source embedded in the selected
  // sidecar. A document with no animation resolves to no clips and no
  // Animation tab, and a broken one reports its own error without disturbing
  // the Pose tab.
  //
  // It is keyed on the animation's own identity (`animationKey`: the file and the hash of the
  // routine source), never on the entry: an update of the model that leaves its routines as
  // they were neither stops nor rewinds one that is playing, and only a changed routine is
  // compiled again, from rest. The source and the file's name are read when the key changes.
  const animationSourceRef = useRef({ sourceAnimation, entry });
  animationSourceRef.current = { sourceAnimation, entry };
  useEffect(() => {
    const { sourceAnimation, entry } = animationSourceRef.current;
    let cancelled = false;
    const controller = new AbortController();
    const resetAnimation = () => {
      const nextState = buildDefaultAnimationState();
      animationStateRef.current = nextState;
      setAnimationState(nextState);
      resetAnimationClock();
    };

    if (!animationKey || !sourceAnimation) {
      setAnimationLoadState({ url: "", status: "idle", error: "", clips: null });
      resetAnimation();
      return () => {
        cancelled = true;
        controller.abort();
      };
    }

    setAnimationLoadState({
      url: animationKey,
      status: "loading",
      error: "",
      clips: null
    });
    resetAnimation();

    const loadMotionRevision = motionRevisionRef.current;
    loadSourceAnimation({ animation: sourceAnimation }, {
      signal: controller.signal,
      name: `${fileKeyOf(entry) || "STEP"} animation`
    })
      .then((animationModule) => {
        if (cancelled) {
          return;
        }
        const clips = animationModule?.clips || {};
        setAnimationLoadState({
          url: animationKey,
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
  // Embedded animation attaches on the FIRST publish and stays live: the viewer
  // re-runs its setup on every meshData change (the same path a LOD swap
  // takes), so occurrences bind as they arrive. Pose and animation controls
  // act on whatever is present; only clip validation waits for the complete
  // model, and a partial model's clip tolerates labels not yet loaded.
  // What the viewport needs to draw one animated frame: the compiled clip and a
  // time. The render pane swaps in the live clock while playing; everything else
  // about playback stays out of the render path.
  //
  // `enabled` is internal pose ownership: paused animation holds its frame;
  // editing Position hands control back to kinematics. It is not a UI gate.
  const playableClip = useMemo(() => (meshPartial ? tolerantAnimationClip(activeClip) : activeClip), [activeClip, meshPartial]);
  const animationRuntime = useMemo(() => animationRenderFrame({
    enabled: animationState.enabled !== false,
    clip: playableClip,
    elapsedSec: animationState.elapsedSec,
    playing: animationState.playing
  }), [animationState.elapsedSec, animationState.enabled, animationState.playing, playableClip]);

  // A named pose is a full configuration, not a patch: every DOF the preset
  // does not mention returns to 0 (the artifact as written), so two presets in
  // a row can never leave a joint behind from the first.
  const commands = useStepMotionControls({
    selectedStepModuleDefinition: definition, selectedAnimationClips: clips, selectedActiveAnimationClip: activeClip,
    animationState, animationStateRef, setAnimationState, stepModuleParameterValuesRef,
    setStepModuleParameterValues, setAppliedStepPoseName, motionRevisionRef
  });

  // Embedded animation clips are checked against the compiled tree once it is
  // in hand: a target no part carries fails HERE, in the Status tab, not the
  // first time playback reaches that frame.
  const validationError = useMemo(() => {
    if (!clips || !Array.isArray(meshData?.parts) || !meshData.parts.length) {
      return "";
    }
    // A partial progressive state lacks occurrences by design; validating
    // against it would report every not-yet-loaded label as a clip error, so
    // validation runs on the complete model only.
    if (meshPartial) {
      return "";
    }
    return validateAnimationClips(THREE, meshData, clips)
      .map((problem) => `${problem.clip}: ${problem.error}`)
      .join("\n");
  }, [clips, meshData, meshPartial]);
  const animationError = animationLoadError || validationError;

  // Copy and Paste of the Position values, as text a person can keep and paste back.
  const { applyStepModuleParameterValues } = commands;
  const copyParameters = useCallback(async () => {
    if (!definition?.parameters?.length) {
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
    if (!definition?.parameters?.length) {
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

  // The stored pose, once, before the first paint (the file's view calls it). Definition
  // normalization happens when the sidecar arrives.
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
    definition, loading, topologyRequired: stepModuleRequiresTopology(definition), parameterValues: stepModuleParameterValues,
    animationState, animationStateRef, animationRuntime, animationError, positionControls, animationControls,
    onParameterChange: commands.handleStepModuleParameterChange, onPlayToggle: commands.handleAnimationPlayToggle,
    releaseAnimation: commands.releaseAnimation, restore
  };
}
