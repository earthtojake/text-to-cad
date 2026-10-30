import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { MousePointer2 } from "lucide-react";
import { clamp, finiteOr } from "@text-to-cad/core/common/numbers.js";
import { buildCadRefToken } from "@text-to-cad/core/lib/cadRefs.js";
import { formatPromptReference } from "@text-to-cad/core/prompt";
import { scenePartCount, viewFeaturesForKind } from "@text-to-cad/core/common/viewSettings.js";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { readFileView } from "../kit/shell/fileView.js";
import { usePreviewState, useRendererShell } from "../kit/shell/useRendererShell.js";
import { usePreviewScene } from "../kit/shell/usePreviewScene.js";
import { useMotionExclusion } from "../kit/tools/model-effects/motionExclusion.js";
import { useSceneToolState, useSceneTools } from "../kit/tools/sceneTools.jsx";
import { PointerPick } from "../kit/tools/select/usePointerPick.js";
import { useDeclinedSelectReference, workspaceLoadAlert } from "../workspace/useWorkspaceDocument.js";
import { useViewerHost } from "../../host/context.js";
import { useExportView } from "../../export/context.js";
import { TOOL_SHORTCUTS } from "../kit/tools/toolShortcuts.js";
import { useI18n } from "@text-to-cad/ui/i18n";
import { GLB_DECLINED_LIVE_COMMANDS, GLB_TOOL, GLB_TOOL_MODES } from "./tools.js";
import { useGlbAnimation } from "./useGlbAnimation.js";

const NO_CHOICE = Object.freeze({ field: null, scale: null, loadScale: null, markers: null });
// Where each control's value is kept in the file's view: the field and the deformation scale as they always were.
const DRIVE_KEYS = Object.freeze({ field: "field", deformation: "scale", load_scale: "loadScale" });
const EMPTY = Object.freeze([]);
// `refs`: what Quick Edit gets when it is not the faces' own (a part's or a joint's parts); `parts`: parts to tint.
const NO_FACES = Object.freeze({ result: null, id: "", faces: EMPTY, refs: EMPTY, parts: EMPTY, softParts: EMPTY, summary: "", picked: false });
// The markers' checkbox, and what it says it draws before they are built.
const MARKERS_TITLE = "Loads and fixtures";
const MARKER_GATE_KINDS = Object.freeze(["load", "fixture"]);
const SELECT_ICON = <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />;
const NO_REFERENCES = Object.freeze([]);
const EXPLODE_OFF = Object.freeze({ exploded: { enabled: false, amount: 0 } });
const CLIP_OFF = Object.freeze({ clip: { enabled: false, axis: "x", invert: false } });

/**
 * A GLB that carries an FEA result (`cadgen fea solve`), drawn on the same shell as any GLB (`GlbRenderer.jsx`) and with
 * its tools (Select, Annotate, Measure, Clip): the field in colour on the deformed shape, Study and an assembly's Parts
 * in the file sidebar, a face picked under Select as Quick Edit's chip (a reference into the STEP it was solved from),
 * where the study holds and loads it on the model, and its Load ramp in the sidebar's Animation and in Preview.
 * `fv`: the FEA viewer's chunk (`feaView.jsx`).
 */
export default function FeaSurface({ view, document, loaded, fv }) {
  const { t } = useI18n();
  const host = useViewerHost();
  const scene = loaded.scene;

  // An FEA result (cadgen fea solve) carries its fields and true displacement in the file; what is
  // shown of it is chosen in Study's What you see (`feaControls`: the field, the deformation and the load),
  // per tab. That choice is this renderer's one slice of the file's view (`kit/shell/fileView.js`), written
  // against the result's own fields and scale: a re-solved result opens at its own defaults. A result that
  // does not read (no checks or study in it) is the load's alert, over the model as the file colours it.
  const read = useMemo(() => {
    try { return { fea: fv ? fv.readFeaResult(scene?.document?.scene) : null, error: null }; }
    catch (error) { return { fea: null, error }; }
  }, [fv, scene]);
  const fea = read.fea;
  const loadAlert = useMemo(() => workspaceLoadAlert({
    catalogError: document.catalogError, error: loaded.error || read.error, modelKey: document.modelKey, hasScene: Boolean(scene), t
  }), [document.catalogError, loaded.error, read.error, document.modelKey, scene, t]);
  // The box the model is drawn in over its Load ramp (`feaBounds.js`), at the deformation and load it opens on, grown on
  // the scene before the shell frames it (Preview frames on it once): its `restBounds`, which the scene's `bounds` reads
  // at rest, so the camera's near and far planes, the floor and the shadows hold the part as drawn, larger than the
  // file's own exaggeration, never slicing it off.
  useMemo(() => {
    if (!fea) return;
    const opening = fv.feaControls(fea);
    const scale = opening.find((control) => control.drives === "deformation").defaultValue;
    const load = opening.find((control) => control.drives === "load_scale").defaultValue;
    const grown = fv.feaDrawnBounds(THREE, scene, fea, { scale, load });
    if (grown) scene.restBounds = grown;
  }, [scene, fea]);
  const controls = useMemo(() => (fea ? fv.feaControls(fea, t) : EMPTY), [fea, t]);
  const signature = fea ? `${fea.fields.map((entry) => entry.attribute).join(",")}:${fea.deformationScale}` : "";
  const [stored] = useState(() => view.state);
  const restored = useMemo(() => (fea ? { ...NO_CHOICE, ...readFileView(stored, { fea: signature }).renderer.fea } : NO_CHOICE), [fea, stored, signature]);
  const [edited, setEdited] = useState({ signature: "", ...NO_CHOICE });
  const choice = edited.signature === signature ? { ...restored, ...edited } : restored;
  // Every control's value, held to its own range and options whatever was written.
  const values = Object.fromEntries(controls.map((control) => [control.id, fv.controlValue(control, choice[DRIVE_KEYS[control.drives]])]));
  const activeField = fea ? fea.fields.find((entry) => entry.attribute === values.field) || fea.fields[0] : null;
  const activeScale = fea ? finiteOr(values.deformation, fea.deformationScale) : null;
  // The load as a multiple of the solved one (a linear study scales exactly).
  const loadScale = fea ? finiteOr(values.load_scale, 1) : 1;
  const markersOn = typeof choice.markers === "boolean" ? choice.markers : true;
  const choiceRef = useRef(choice);
  choiceRef.current = choice;
  const rendererState = useMemo(() => (fea
    ? { signatures: { fea: signature }, read: () => ({ fea: Object.fromEntries(Object.keys(NO_CHOICE).map((key) => [key, choiceRef.current[key]])) }) }
    : null), [fea, signature]);

  // What Study chose (a fixed face, a load, a load's face) or a press on the result picked: its faces
  // and what a prompt calls them.
  const [chosenFaces, setChosenFaces] = useState(NO_FACES);
  const clearChoice = useCallback(() => setChosenFaces(NO_FACES), []);
  const faces = fea && chosenFaces.result === fea ? chosenFaces : NO_FACES;
  // Study's setup and Details.
  const sections = useMemo(() => (fea ? fv.studySections(fea, t) : { setup: EMPTY, details: EMPTY }), [fea, t]);
  const rows = useMemo(() => [...sections.setup, ...sections.details], [sections]);
  // An assembly's parts, each with its joints, are a sidebar section of their own above Study, from six parts
  // up (`feaShowsParts`); a picked face's chip names its part.
  const parts = useMemo(() => (fea && fv.feaShowsParts(fea) ? fv.partRows(fea, loadScale, t) : EMPTY), [fea, loadScale, t]);
  // The answer at a glance, at the load shown: it follows the load control, and may change its word.
  const verdict = useMemo(() => (fea ? fv.feaVerdict(fea, loadScale, t) : null), [fea, loadScale, t]);
  const chooseFaces = useCallback((row) => {
    setChosenFaces({ result: fea, id: row.id, faces: row.faces || EMPTY, refs: row.refs || EMPTY, parts: row.parts || EMPTY, softParts: row.softParts || EMPTY,
      summary: row.summary, picked: row.picked === true });
  }, [fea]);
  // The view's Clip is the viewport's (`kit/tools/model-effects`): its plane in force is the runtime's (three.js's
  // clipping plane, what lies on its negative side cut away), read as a press or a label needs it.
  const runtimeRefRef = useRef(null);
  const cutPlane = useCallback(() => runtimeRefRef.current?.current?.activeClipPlanes?.[0] || null, []);
  const keptByCut = useCallback((at) => {
    const plane = cutPlane();
    return !plane || !fea || plane.distanceToPoint(new THREE.Vector3().fromArray(at).applyMatrix4(fea.mesh.matrixWorld)) >= -1e-6;
  }, [cutPlane, fea]);
  // A press on the result picks the face under it, called what Study calls it: never one Clip has cut away.
  const pickScene = useMemo(() => (fea ? { pick: (ray) => fv.pickFace(fea, ray, cutPlane()) } : null), [fea, cutPlane]);
  const pick = useCallback((hit) => {
    if (!hit) { clearChoice(); return; }
    const row = fv.faceRow(rows, hit.ref);
    chooseFaces({ id: row?.id || hit.ref, faces: [hit.ref], summary: fv.facePromptSummary(fea, hit.ref), picked: true });
  }, [fea, rows, chooseFaces, clearChoice]);
  // The part the result was solved from, the file a choice's references name.
  const source = useMemo(() => (fea ? fv.resultSourcePath(view.file.path, fea.document) : ""), [fea, view.file.path]);
  const references = useMemo(() => {
    if (!fea) return null;
    if (!source) return [];
    const reference = (selectors, summary) => (selectors.length ? [{ resource: { kind: "workspace-file", path: source },
      target: { kind: "cad-selector", selectors }, ...(summary ? { summary } : {}) }] : []);
    if (faces.refs.length) return reference(faces.refs.map(fv.findingSelector), faces.summary);
    return reference(faces.faces.map(fv.findingSelector), faces.summary);
  }, [fea, source, faces]);

  // A frame for what the routine and the controls change: the editor's, and Preview's while it is open (its own
  // scene over the same geometry, so the colours and the deformation drawn are the editor's).
  const requestRenderRef = useMemo(() => ({ current: null }), []);
  const preview = usePreviewState();
  const previewing = preview.previewing;
  // The Load ramp's share of the load put on (0 to 1) while it plays, or null while it does not; and the one pass
  // that draws the colours, the deformation and the markers for what is shown.
  const rampRef = useRef(null);
  const paintRef = useRef(null);
  // The result's routine: the Load ramp, the load going on from none to the load chosen, colours, deformation and
  // markers together.
  const ownClips = useMemo(() => {
    if (!fea) return EMPTY;
    const { id, key, duration } = fv.LOAD_RAMP;
    return [{
      id, label: t(key), duration,
      play: {
        apply(elapsedSec) { rampRef.current = clamp(elapsedSec / duration, 0, 1); paintRef.current?.(); },
        release() { rampRef.current = null; paintRef.current?.(); },
      },
    }];
  }, [fea, t]);
  const animation = useGlbAnimation(scene?.document || null, () => requestRenderRef.current?.(), ownClips);
  const shellRef = useRef(null);
  const choose = useCallback((patch) => {
    setEdited({ ...choiceRef.current, ...patch, signature });
    shellRef.current?.scheduleStateSave();
  }, [signature]);
  // The markers built for the result (below), whose kinds Study's gate for them names.
  const [markers, setMarkers] = useState(null);
  const chosenSomething = faces.faces.length > 0 || faces.refs.length > 0;

  // ---- tools: Select (the result's faces), Annotate, Measure and Clip --------------------------
  const tools = useSceneToolState({ toolModes: GLB_TOOL_MODES, previewing, fileKey: document.modelKey, revision: loaded.revision,
    measurable: true, resource: document.resource });
  const { measure } = tools;
  const measureRef = useRef(measure);
  measureRef.current = measure;
  const features = useMemo(() => viewFeaturesForKind("glb", { parts: scenePartCount(scene), explodeParts: scene?.explodeParts || 0 }), [scene]);
  const live = useMemo(() => ({ declined: GLB_DECLINED_LIVE_COMMANDS, commands: { clearSelection: () => clearChoice() } }), [clearChoice]);
  // Escape cancels a measurement in progress, then lets go of what is picked: a measurement, then what Study chose.
  const escape = useMemo(() => ({
    active: chosenSomething || measure.drafting || measure.selected.length > 0,
    handle: () => {
      const now = measureRef.current;
      if (now.drafting) { now.cancelDraft(); return true; }
      if (now.selected.length) { now.select([]); return true; }
      if (!chosenSomething) return false;
      clearChoice();
      return true;
    }
  }), [chosenSomething, measure.drafting, measure.selected.length, clearChoice]);
  const shell = useRendererShell({
    view, services: document.services, resource: document.resource, modelKey: document.modelKey, revisionKey: loaded.revision,
    features, toolModes: GLB_TOOL_MODES, tool: tools.tool, previewable: true, preview, scene, sceneEffects: true,
    load: { busy: loaded.busy && !scene, updating: loaded.busy && Boolean(scene), progress: loaded.progress, alert: loadAlert },
    animation, live, escape, rendererState, deleteSelection: measure.removeSelected
  });
  shellRef.current = shell;
  requestRenderRef.current = () => { shell.requestRender(); shell.frame.previewViewRef.current?.requestRender?.(); };
  useDeclinedSelectReference(document);

  // ---- one motion at a time: Explode, the routine and Clip --------------------------------
  const { view: viewSettings, store } = shell.viewSettings;
  useMotionExclusion(document.modelKey, {
    explode: { applied: Boolean(viewSettings.exploded?.enabled && viewSettings.exploded.amount > 0), reset: () => store.patch(EXPLODE_OFF) },
    clip: { applied: Boolean(viewSettings.clip?.enabled), reset: () => store.patch(CLIP_OFF) },
    animation: { applied: Boolean(animation?.enabled), reset: () => animation?.onRelease() }
  });
  // What Clip cuts moves the labels and what a press can pick: a frame for the labels when it changes.
  useEffect(() => { requestRenderRef.current?.(); }, [viewSettings.clip, requestRenderRef]);

  // The colours and the drawn displacement follow the choice, in place on the loaded geometry, with
  // the faces (or a part's triangles) chosen in Study, or picked, tinted over the field. At a load
  // other than the solved one, the values and the ramp's range are that load's and so is the
  // displacement drawn; while the Load ramp plays, the values and the displacement climb to it
  // under the range of the load chosen. The markers stand on the positions drawn.
  const tinted = useMemo(() => (fea ? fv.faceIndices(fea, faces.faces) : EMPTY), [fea, faces]);
  const markersRef = useRef(null);
  paintRef.current = () => {
    if (!fea) return;
    const shownLoad = rampRef.current === null ? loadScale : rampRef.current * loadScale;
    let changed = fv.recolorByField(fea.mesh, activeField, fea.ramp, tinted, faces.parts, faces.softParts,
      { valueScale: shownLoad, rangeScale: loadScale });
    if (fv.applyDeformation(fea.mesh, activeScale * shownLoad, fea.deformationScale)) {
      markersRef.current?.update(fea.mesh.geometry.getAttribute("position").array);
      changed = true;
    }
    if (changed) requestRenderRef.current?.();
  };
  useEffect(() => { paintRef.current?.(); }, [fea, activeField, tinted, faces.parts, faces.softParts, activeScale, loadScale]);

  // Where the study loads and holds the part, on the model (`feaMarkers.js`): built once per result,
  // standing on the positions drawn, the chosen load's or fixture's in the chosen colour.
  useEffect(() => {
    if (!fea) return undefined;
    const built = fv.createFeaMarkers(THREE, fea);
    if (!built.sites.length) { built.dispose(); return undefined; }
    fea.mesh.add(built.object3D);
    built.update(fea.mesh.geometry.getAttribute("position").array);
    markersRef.current = built;
    setMarkers(built);
    return () => {
      markersRef.current = null;
      setMarkers(null);
      built.dispose();
      requestRenderRef.current?.();
    };
  }, [fea, requestRenderRef]);
  const colours = fv?.MARKER_COLOURS[view.appearance?.colorScheme === "dark" ? "dark" : "light"] || null;
  useEffect(() => {
    if (!markers) return;
    markers.style({ colours, visible: markersOn, chosen: (site) => fv.markerChosen(faces, site) });
    requestRenderRef.current?.();
  }, [markers, colours, markersOn, faces, requestRenderRef]);
  // A label goes with its marker when Clip cuts away where the load acts (read each frame, as the cut is).
  const loadLabels = useCallback(() => (markers && markersOn
    ? markers.labels(loadScale).filter((label) => keptByCut(label.face || label.at)) : EMPTY), [markers, markersOn, loadScale, keptByCut]);

  // Select picks the result's faces; Study's rows choose them too.
  const selectActive = Boolean(fea) && !previewing && shell.toolMode === GLB_TOOL.SELECT;
  // One face chosen is Quick Edit's chip (its card: its ref, what the study does to it, its part), and the copy key copies it.
  const single = faces.faces.length === 1 && !faces.refs.length ? faces.faces[0] : "";
  const copyFace = useCallback(async () => {
    if (!single) return false;
    const selectors = [fv.findingSelector(single)];
    try { await host.clipboard.writeText(source ? buildCadRefToken({ cadPath: source, selectors }) : single); return true; }
    catch (error) { shellRef.current?.reportActionError(error instanceof Error ? error.message : "Could not copy reference"); return false; }
  }, [single, source, host.clipboard]);
  const copySelection = selectActive && single ? copyFace : null;
  // Study's What you see: each control writes its value.
  const resultControls = {
    controls, values,
    onChange: (id, value) => choose({ [DRIVE_KEYS[id]]: value }),
    // Where the study holds and loads the part, drawn on the model or not.
    markers: fea ? { title: MARKERS_TITLE, on: markersOn, onChange: (on) => choose({ markers: on }),
      text: fv.markerGateText(markers?.kinds?.length ? markers.kinds : MARKER_GATE_KINDS) } : null,
  };

  // ---- the file sidebar: Study, and an assembly's Parts above it ---------------------------
  const sidebar = fea ? <fv.FeaStudyPanel parts={parts} openPart={fv.weakestPartIndex(fea)} setup={sections.setup} details={sections.details}
    verdict={verdict} chosen={faces.id} onChoose={chooseFaces} result={resultControls} /> : null;

  // ---- Quick Edit: the faces chosen, as references into the part the result was solved from --------------
  // A row chosen in Study says on its chip what it is ("Bulkhead top sag fails: moves 1.03 mm, limit 0.5 mm"), the
  // sentence its prompt carries; a face picked on the model is named, its card saying what the study does to it.
  const chips = useMemo(() => {
    if (!fea || !references?.length) return NO_REFERENCES;
    // Its card's Study row: what the row chosen says about the face, whole; for a face picked, what the study does to it.
    const face = single ? { ref: single, role: faces.summary && !faces.picked ? faces.summary : fv.faceRole(fea, single),
      part: fv.facePartDetail(fea, single, loadScale) } : null;
    return [{ key: `fea:${faces.id}`, label: faces.summary && !faces.picked ? faces.summary : single ? fv.faceTitle(fea, single) : faces.summary || faces.id, glyph: "face", id: single || faces.id,
      copy: formatPromptReference(references[0]), card: face ? <fv.FaceCard face={face} /> : null, onRemove: clearChoice }];
  }, [fea, references, single, faces, loadScale, clearChoice]);
  const nameReference = useCallback((reference) => {
    const selector = reference?.resource?.path === source && reference.target?.kind === "cad-selector" ? reference.target.selectors[0] : "";
    const ref = selector ? `#${selector.replace(/^#/, "")}` : "";
    return fea && ref && fea.faces.includes(ref) ? { name: fv.faceTitle(fea, ref), kind: "face" } : "";
  }, [fea, source]);

  // ---- Preview: its own scene over the result's geometry, and its own routine ----------------
  // The Load ramp paints the geometry both scenes share, so Preview shows the field and the deformation it draws.
  const previewScene = usePreviewScene(scene, previewing);
  const previewAnimation = useGlbAnimation(previewScene?.document || null, () => requestRenderRef.current?.(), ownClips);
  const previewView = useMemo(() => ({
    scene: previewScene, animation: previewAnimation,
    overlay: () => (fea ? <fv.FeaColourBar result={fea} field={activeField} loadScale={loadScale} raised={Boolean(previewAnimation)} /> : null),
  }), [previewScene, previewAnimation, fea, activeField, loadScale]);

  // Export converts the result shown to the other mesh kinds, as a plain GLB's does (`GlbRenderer.jsx`).
  const exportView = useMemo(() => scene && loaded.revision && document.modelKey && !host.environment.compact ? {
    doc: document.modelKey, revision: loaded.revision, file: view.file.path, name: view.file.name
  } : null, [scene, loaded.revision, document.modelKey, host.environment.compact, view.file.path, view.file.name]);
  useExportView(exportView);
  const sceneTools = useSceneTools({ shell, scene, features, state: tools, measurable: true, clearParts: clearChoice });
  const strip = [shell.tools.own({ id: GLB_TOOL.SELECT, label: t("tool.select"), shortcut: TOOL_SHORTCUTS.select, icon: SELECT_ICON }), ...sceneTools.tools];
  const handlePick = useCallback((hit, modifiers) => {
    pick(hit);
    if (hit && !modifiers?.multiSelect) measureRef.current.select([]);
  }, [pick]);
  const overlay = (viewport) => {
    runtimeRefRef.current = viewport.runtimeRef;
    return <>
      {sceneTools.overlay(viewport)}
      {fea ? <>
        <fv.FeaFraming runtimeRef={viewport.runtimeRef} hostRef={viewport.hostRef} />
        <PointerPick viewport={viewport} scene={pickScene} enabled={selectActive} onPick={handlePick} />
        <fv.FeaColourBar result={fea} field={activeField} loadScale={loadScale} raised={false} />
        {markers ? <fv.FeaLoadLabels runtimeRef={viewport.runtimeRef} hostRef={viewport.hostRef} mesh={fea.mesh} labels={loadLabels}
          colours={{ ink: colours.load, halo: colours.halo }} /> : null}
      </> : null}
    </>;
  };
  return <RendererShell shell={shell} tools={strip} subToolbar={sceneTools.subToolbar} sidebar={sidebar} previewView={previewView}
    references={previewing ? NO_REFERENCES : references || NO_REFERENCES} referenceChips={previewing ? NO_REFERENCES : chips} nameReference={nameReference}
    onClearReferences={() => { clearChoice(); measure.select([]); }} copySelection={copySelection}
    onSelectPress={sceneTools.onSelectPress} onSelectHover={sceneTools.onSelectHover} viewportOverlay={overlay} />;
}
