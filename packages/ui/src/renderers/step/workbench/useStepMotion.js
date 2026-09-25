import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import {
  animationClipList,
  animationRenderFrame,
  buildDefaultAnimationState,
  findAnimationClip
} from "@hardcore/core/common/animationClock.js";
import {
  kinematicsModuleDefinitionFromSidecar,
  loadKinematicsModuleDefinition,
  previewKinematicsModuleDefinition
} from "@hardcore/core/common/kinematicsModule.js";
import { loadSourceAnimation, validateAnimationClips } from "@hardcore/core/common/renderModule.js";
import { validateSourceSidecar } from "@hardcore/core/common/sourceSidecar.js";
import { entryPoseUrl } from "@hardcore/core/lib/entryAssets.js";
import { tolerantAnimationClip } from "../components/workbench/hooks/packageProgressiveLoad.js";
import { useAnimationClockStore } from "./animationClockStore.js";
import { cadPathForEntry, fileKey as fileKeyOf } from "./entryPaths.js";
import { restoreMotionAnimation, restoreMotionParameters } from "./motionRestore.js";
import { buildParameterValuesCopyText, parseParameterValuesPasteText } from "./parameterControls.js";
import { restoredPoseValues } from "./stepSessionRecord.js";
import { resolveStepModuleLoad } from "./stepModuleLoad.js";
import { stepModuleRequiresTopology } from "./topologyCapabilities.js";
import { useStepMotionControls } from "./useStepMotionControls.js";

function sourceAnimationForEntry(entry) { return (entry?.editingPreview ? entry.previewAnimation : entry?.sourceSidecar?.animation) || null; }
function sourceAnimationKeyForEntry(entry) {
  return sourceAnimationForEntry(entry) ? `${fileKeyOf(entry)}:${entry?.animationHash || entry?.documentHash || entry?.hash || "animation"}` : "";
}

/**
 * Where a STEP entry's motion comes from: its kinematics module (an edit's preview, or the
 * sidecar's), the path the module poses, and the routine source embedded in the sidecar.
 */
export function stepMotionSources(entry) {
  const moduleUrl = entry?.editingPreview && entry.previewKinematics ? `preview:${entry.hash}` : entryPoseUrl(entry);
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
 * is not validated), and the stored record to restore from as the module and routines compile.
 * Out: what the Position tab and the playbar read and call, what the viewport draws a frame
 * from (`animationRuntime`), and `restore`, which the session record calls once before the
 * first paint.
 *
 * @param {{ entry: object, fileKey: string, resources: object, meshData: object | null, meshPartial: boolean,
 *   readStored: () => { pose: object | null, animation: object | null }, clipboard: object,
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

  const definition = stepModuleLoadState.url === moduleUrl ? stepModuleLoadState.definition : null;
  const clips = animationLoadState.url === animationKey ? animationLoadState.clips : null;
  const animationStatus = animationKey ? (animationLoadState.url === animationKey ? animationLoadState.status : "loading") : "idle";
  const animationLoadError = animationLoadState.url === animationKey ? animationLoadState.error : "";
  const status = moduleUrl ? (stepModuleLoadState.url === moduleUrl ? stepModuleLoadState.status : "loading") : "idle";
  const error = stepModuleLoadState.url === moduleUrl ? stepModuleLoadState.error : "";
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

    setStepModuleLoadState({
      url: moduleUrl,
      status: "loading",
      error: "",
      definition: null
    });
    stepModuleParameterValuesRef.current = {};
    setStepModuleParameterValues({});

    const loadMotionRevision = motionRevisionRef.current;
    const modulePromise = entry?.editingPreview
      ? Promise.resolve().then(() => previewKinematicsModuleDefinition(entry.previewKinematics, {
          cadPath: cadPath,
        }))
      : entry?.sourceSidecar
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
      const restoredSessionState = readStoredRef.current();
      // A sidecar with no kinematics section resolves to a NULL definition —
      // an animation-only model has a sidecar and lands here — so the ready
      // state is committed from one place that expects that (see
      // workbench/stepModuleLoad); the Position section is then absent, not empty.
      const resolved = resolveStepModuleLoad({
        url: moduleUrl,
        definition,
        restored: restoredSessionState.pose
      });
      setStepModuleLoadState(resolved.loadState);
      const parameterValues = restoreMotionParameters(definition, resolved.parameterValues,
        motionRevisionRef.current === loadMotionRevision ? restoredSessionState.animation : animationStateRef.current);
      stepModuleParameterValuesRef.current = parameterValues;
      setStepModuleParameterValues(parameterValues);
      setAppliedStepPoseName("");
    }).catch((error) => {
      if (cancelled) {
        return;
      }
      setStepModuleLoadState({
        url: moduleUrl,
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
  useEffect(() => {
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
        const restoredSessionState = readStoredRef.current();
        const nextState = restoreMotionAnimation(
          motionRevisionRef.current === loadMotionRevision ? restoredSessionState.animation : animationStateRef.current, clips);
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
  }, [fileKey, animationKey, entry, sourceAnimation]);


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

  // The stored record's motion, once, before the first paint (the session record calls it).
  // Definition normalization happens when the sidecar arrives; the animation slice restores
  // against the CLIPS this model actually compiled, which is why it is resolved through
  // restoreMotionAnimation rather than trusted as stored.
  const restore = (restored) => {
    const values = restoredPoseValues(restored);
    if (values) {
      stepModuleParameterValuesRef.current = values;
      setStepModuleParameterValues(values);
    }
    if (restored.animation) {
      const next = restoreMotionAnimation(restored.animation, animationLoadState.url === animationKey ? animationLoadState.clips : null);
      animationStateRef.current = next;
      setAnimationState(next);
      setAnimationClock(next.elapsedSec);
    }
  };

  // What the Position tab and the playbar read and call.
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
