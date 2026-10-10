import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { MousePointer2 } from "lucide-react";
import { clamp, finiteOr } from "@text-to-cad/core/common/numbers.js";
import { buildCadRefToken } from "@text-to-cad/core/lib/cadRefs.js";
import { EDGELESS_VIEW_FEATURES } from "@text-to-cad/core/common/viewSettings.js";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { readFileView } from "../kit/shell/fileView.js";
import { useRendererShell } from "../kit/shell/useRendererShell.js";
import { useDeclinedSelectReference, useWorkspaceDocument, workspaceLoadAlert } from "../workspace/useWorkspaceDocument.js";
import { useViewerHost } from "../../host/context.js";
import { PointerPick } from "../kit/tools/select/usePointerPick.js";
import FindingsList, { findingsAlert } from "../kit/status/findings.jsx";
import FindingRings from "./FindingRings.jsx";
import FeaStudyPanel, { FEA_PARTS_PANEL_ID, FEA_STUDY_PANEL_ID } from "./FeaStudyPanel.jsx";
import FeaColourBar from "./FeaColourBar.jsx";
import FeaLoadLabels from "./FeaLoadLabels.jsx";
import { FileSheetStatusText } from "../kit/inspector/FileSheet.js";
import { DEFAULT_POSE_VALUE, NO_PRESET_VALUE, positionValuesAreDefault } from "../kit/inspector/kinematicsControls.jsx";
import {
  applyDeformation, faceIndices, facePartDetail, faceTitle, facePromptSummary, faceRole, feaControls, feaDefaults, feaMarkerShow, feaPresets, feaShowsParts, feaVerdict, findingSelector, pickFace,
  readFeaResult, recolorByField, resultSourcePath, partRows, ringTargets, studyRows, weakestPartIndex
} from "./feaResult.js";
import { createFeaMarkers } from "./feaMarkers.js";
import { GLB_DECLINED_LIVE_COMMANDS, GLB_TOOL, GLB_TOOL_MODES } from "./tools.js";
import { useGlbAnimation } from "./useGlbAnimation.js";
import { useGlbScene } from "./useGlbScene.js";

const LIVE = Object.freeze({ declined: GLB_DECLINED_LIVE_COMMANDS });
const NO_CHOICE = Object.freeze({ field: null, scale: null, loadScale: null, threshold: null, preset: null, markers: null });
// Where each control's value is kept in the file's view: the field and the deformation scale as they always were.
const DRIVE_KEYS = Object.freeze({ field: "field", deformation: "scale", load_scale: "loadScale", threshold: "threshold" });
const NO_VALUES = Object.freeze({ field: null, scale: null, loadScale: null, threshold: null });
// The Load ramp: the load going on, from none to all of it, over this long.
const LOAD_RAMP_SECONDS = 2;
// What the markers are drawn in. The theme has no colour of its own to spare: every saturated hue is
// the ramp's or the chosen faces' magenta, so a load is the ink and a fixture a muted grey.
const MARKER_COLOURS = Object.freeze({
  light: Object.freeze({ load: "#18181b", fixture: "#71717a", halo: "rgba(255, 255, 255, 0.9)" }),
  dark: Object.freeze({ load: "#fafafa", fixture: "#a1a1aa", halo: "rgba(18, 19, 21, 0.9)" }),
});
const FINDING_HEADINGS = Object.freeze({ fix: "Fix before using", suggestions: "Suggestions" });
const EMPTY = Object.freeze([]);
const NO_FINDING = Object.freeze({ findings: null, index: -1 });
// `refs`: what Quick Edit gets when it is not the faces' own (a part's or a joint's parts); `parts`: parts to tint.
const NO_FACES = Object.freeze({ result: null, id: "", faces: EMPTY, refs: EMPTY, parts: EMPTY, softParts: EMPTY, summary: "" });
const SELECT_ICON = <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />;
// Select's own panels, which a person can close: Study, and above it an assembly's Parts. A result
// opens with them up, except on a phone.
const STUDY_PANEL = Object.freeze({ id: FEA_STUDY_PANEL_ID, label: "Study", startsClosed: false });
const ASSEMBLY_PANELS = Object.freeze([Object.freeze({ id: FEA_PARTS_PANEL_ID, label: "Parts", startsClosed: false }), STUDY_PANEL]);

/** Study's row for a face, where it has one (a fixed face, a loaded face), so a pick of it marks that row. */
function faceRow(rows, ref) {
  for (const row of rows) {
    const found = row.faces?.length === 1 && row.faces[0] === ref && !row.children ? row : row.children ? faceRow(row.children, ref) : null;
    if (found) return found;
  }
  return null;
}

/** A short, stable name for a view, for its slice's signature. */
function viewKey(view) {
  const text = JSON.stringify(view);
  let hash = 5381;
  for (let i = 0; i < text.length; i += 1) hash = ((hash * 33) ^ text.charCodeAt(i)) >>> 0;
  return hash.toString(36);
}

/** A control's value: what was chosen, where it is still one of the control's; else its default. */
function controlValue(control, chosen) {
  if (control.type === "enum") return control.options.some((option) => option.value === chosen) ? chosen : control.defaultValue;
  return Number.isFinite(chosen) ? clamp(chosen, control.min, control.max) : control.defaultValue;
}

/**
 * Whether a marker is of what Study chose: a load row's arrows (that load, on its faces), a fixed
 * row's cones, and both on a face picked on the result. A part or a joint has none.
 */
function markerChosen(faces, site) {
  if (!faces.faces.includes(site.ref)) return false;
  const [kind, group] = String(faces.id).split(":");
  if (kind === "load") return site.kind === "load" && Number(group) === site.group;
  if (kind === "fixed") return site.kind === "fixture" && Number(group) === site.group;
  return kind !== "joint";
}

/** The card's body, mounted only while the card is up: a card brought back from its icon starts with no finding chosen. */
function FindingsBody({ onShown, ...list }) {
  useEffect(() => { onShown(); }, [onShown]);
  return <FindingsList {...list} />;
}

function GlbSurface({ view, data }) {
  const host = useViewerHost();
  const document = useWorkspaceDocument({ view, data });
  const loaded = useGlbScene({ entry: document.entry, resources: document.client.resources });
  const scene = loaded.scene;
  const loadAlert = useMemo(() => workspaceLoadAlert({
    catalogError: document.catalogError, error: loaded.error, modelKey: document.modelKey, hasScene: Boolean(scene)
  }), [document.catalogError, loaded.error, document.modelKey, scene]);

  // An FEA result (cadgen fea solve) carries its fields and true displacement in the file; what is
  // shown of it is chosen in Study's What you see, with the controls the study's view names (`feaControls`;
  // by default the field and the deformation), per tab. That choice is this renderer's one slice of
  // the file's view (`kit/shell/fileView.js`), written against the result's own fields, scale and
  // view: a re-solved result opens at its own defaults.
  const fea = useMemo(() => readFeaResult(scene?.document?.scene), [scene]);
  const controls = useMemo(() => (fea ? feaControls(fea) : EMPTY), [fea]);
  const presets = useMemo(() => (fea ? feaPresets(fea, controls) : EMPTY), [fea, controls]);
  const markerShow = useMemo(() => (fea ? feaMarkerShow(fea) : null), [fea]);
  const signature = fea ? `${fea.fields.map((entry) => entry.attribute).join(",")}:${fea.deformationScale}${fea.view ? `:${viewKey(fea.view)}` : ""}` : "";
  const [stored] = useState(() => view.state);
  const restored = useMemo(() => (fea ? { ...NO_CHOICE, ...readFileView(stored, { fea: signature }).renderer.fea } : NO_CHOICE), [fea, stored, signature]);
  const [edited, setEdited] = useState({ signature: "", ...NO_CHOICE });
  const choice = edited.signature === signature ? { ...restored, ...edited } : restored;
  // Every control's value, held to its own range and options whatever was written.
  const values = Object.fromEntries(controls.map((control) => [control.id, controlValue(control, choice[DRIVE_KEYS[control.drives]])]));
  const activeField = fea ? fea.fields.find((entry) => entry.attribute === values.field) || fea.fields[0] : null;
  const activeScale = fea ? finiteOr(values.deformation, fea.deformationScale) : null;
  // The load as a multiple of the solved one (a linear study scales exactly), and what is drawn grey under a threshold.
  const loadScale = finiteOr(values.load_scale, 1);
  const thresholdControl = controls.find((control) => control.drives === "threshold");
  const thresholdField = fea && thresholdControl ? fea.fields.find((entry) => entry.attribute === thresholdControl.field) : null;
  const thresholdValue = thresholdField ? values.threshold : null;
  const markersOn = Boolean(markerShow) && (typeof choice.markers === "boolean" ? choice.markers : markerShow.on);
  const defaults = useMemo(() => feaDefaults(controls), [controls]);
  const activePreset = presets.some((preset) => preset.value === choice.preset) ? choice.preset
    : positionValuesAreDefault(values, defaults) ? DEFAULT_POSE_VALUE : NO_PRESET_VALUE;
  const choiceRef = useRef(choice);
  choiceRef.current = choice;
  const rendererState = useMemo(() => (fea
    ? { signatures: { fea: signature }, read: () => ({ fea: Object.fromEntries(Object.keys(NO_CHOICE).map((key) => [key, choiceRef.current[key]])) }) }
    : null), [fea, signature]);

  // What the result's checks found is the viewer's alert card, as a board's are (`kit/status/findings.jsx`):
  // open over the view while something must be fixed, put away (its icon in the navbar) for suggestions
  // alone. A failure to load owns the card; the findings have it otherwise.
  const compact = Boolean(view.appearance?.compact);
  const findings = fea && !compact && fea.findings.length ? fea.findings : null;
  const card = useMemo(() => findingsAlert(findings), [findings]);
  const [chosen, setChosen] = useState(NO_FINDING);
  // What Study chose (a fixed face, a load, a load's face) or a press on the result picked: its faces
  // and what a prompt calls them. One choice at a time: a finding or faces.
  const [chosenFaces, setChosenFaces] = useState(NO_FACES);
  const clearFinding = useCallback(() => setChosen(NO_FINDING), []);
  const clearChoice = useCallback(() => { setChosen(NO_FINDING); setChosenFaces(NO_FACES); }, []);
  const finding = findings && chosen.findings === findings ? findings.find((entry) => entry.index === chosen.index) || null : null;
  const faces = fea && chosenFaces.result === fea ? chosenFaces : NO_FACES;
  const rows = useMemo(() => (fea ? studyRows(fea) : EMPTY), [fea]);
  // An assembly's parts, each with its joints, are a panel of their own above Study, from six parts
  // up unless the view says (`feaShowsParts`); under that a picked face's Reference names its part.
  const parts = useMemo(() => (fea && feaShowsParts(fea) ? partRows(fea, loadScale) : EMPTY), [fea, loadScale]);
  // The answer at a glance, at the load shown: it follows the load control, and may change its word.
  const verdict = useMemo(() => (fea ? feaVerdict(fea, loadScale) : null), [fea, loadScale]);
  const chooseFaces = useCallback((row) => { setChosen(NO_FINDING); setChosenFaces({ result: fea, id: row.id, faces: row.faces || EMPTY, refs: row.refs || EMPTY, parts: row.parts || EMPTY, softParts: row.softParts || EMPTY, summary: row.summary }); }, [fea]);
  // A press on the result picks the face under it, called what Study calls it.
  const pickScene = useMemo(() => (fea ? { pick: (ray) => pickFace(fea, ray) } : null), [fea]);
  const pick = useCallback((hit) => {
    if (!hit) { clearChoice(); return; }
    const row = faceRow(rows, hit.ref);
    chooseFaces({ id: row?.id || hit.ref, faces: [hit.ref], summary: facePromptSummary(fea, hit.ref) });
  }, [fea, rows, chooseFaces, clearChoice]);
  // The part the result was solved from, the file a choice's references name.
  const source = useMemo(() => (fea ? resultSourcePath(view.file.path, fea.document) : ""), [fea, view.file.path]);
  const references = useMemo(() => {
    if (!fea) return null;
    if (!source) return [];
    const reference = (selectors, summary) => (selectors.length ? [{ resource: { kind: "workspace-file", path: source },
      target: { kind: "cad-selector", selectors }, ...(summary ? { summary } : {}) }] : []);
    if (faces.refs.length) return reference(faces.refs.map(findingSelector), faces.summary);
    if (faces.faces.length) return reference(faces.faces.map(findingSelector), faces.summary);
    if (!finding) return [];
    const refs = [...new Set(finding.items.map((item) => item.ref).filter(Boolean).map(findingSelector))];
    // A finding about no face is about the whole part.
    return reference(refs.length ? refs : fea.occurrence ? [fea.occurrence] : [], finding.summary);
  }, [fea, source, faces, finding]);
  // The places it names, in the mesh's space with the displacement there, ringed over the view.
  const targets = useMemo(() => (finding && fea ? ringTargets(fea, finding.items.map((item) => item.at).filter(Boolean)) : EMPTY),
    [finding, fea]);

  const requestRenderRef = useMemo(() => ({ current: null }), []);
  // How much of the load a playing Load ramp has put on (0 to 1), or null while none plays; and the
  // one pass that draws the colours, the deformation and the markers for the load shown.
  const rampRef = useRef(null);
  const paintRef = useRef(null);
  // A result's own routine: the load going on, from none to the load chosen, colours, deformation and markers together.
  const loadRamp = useMemo(() => (fea ? [{
    id: "fea:load-ramp", label: "Load ramp", duration: LOAD_RAMP_SECONDS,
    play: {
      apply(elapsedSec) { rampRef.current = clamp(elapsedSec / LOAD_RAMP_SECONDS, 0, 1); paintRef.current?.(); },
      release() { rampRef.current = null; paintRef.current?.(); },
    },
  }] : EMPTY), [fea]);
  const animation = useGlbAnimation(scene?.document || null, () => requestRenderRef.current?.(), loadRamp);
  const shellRef = useRef(null);
  const choose = useCallback((patch) => {
    setEdited({ ...choiceRef.current, ...patch, signature });
    shellRef.current?.scheduleStateSave();
  }, [signature]);
  const chosenSomething = Boolean(finding) || faces.faces.length > 0 || faces.refs.length > 0;
  const shell = useRendererShell({
    view, services: document.services, resource: document.resource, modelKey: document.modelKey, revisionKey: loaded.revision,
    features: EDGELESS_VIEW_FEATURES, toolModes: GLB_TOOL_MODES, previewable: true, scene,
    load: { busy: loaded.busy && !scene, updating: loaded.busy && Boolean(scene), progress: loaded.progress, alert: loadAlert || card },
    animation, live: LIVE, rendererState, displaySections: markerShow ? [{
      id: "fea-markers", title: "Loads and fixtures", enabled: markersOn, onEnabledChange: (on) => choose({ markers: on }),
      content: <FileSheetStatusText>Arrows where the study loads the part, cones where it holds it.</FileSheetStatusText>,
    }] : null,
    // Escape lets go of what is chosen, which a result with no source to edit has no Quick Edit to clear.
    escape: { active: chosenSomething, handle: () => { if (!chosenSomething) return false; clearChoice(); return true; } }
  });
  shellRef.current = shell;
  requestRenderRef.current = shell.requestRender;
  useDeclinedSelectReference(document);

  // The colours and the drawn displacement follow the choice, in place on the loaded geometry, with
  // the faces (or a part's triangles) chosen in Study, or picked, tinted over the field. At a load
  // other than the solved one, the values and the ramp's range are that load's and so is the
  // displacement drawn; while the Load ramp plays, the values and the displacement climb to it
  // under the range of the load chosen. The markers stand on the positions drawn.
  const tinted = useMemo(() => (fea ? faceIndices(fea, faces.faces) : EMPTY), [fea, faces]);
  const markersRef = useRef(null);
  paintRef.current = () => {
    if (!fea) return;
    const shownLoad = rampRef.current === null ? loadScale : rampRef.current * loadScale;
    const threshold = thresholdField ? { field: thresholdField, value: thresholdValue, scale: shownLoad } : null;
    let changed = recolorByField(fea.mesh, activeField, fea.ramp, tinted, faces.parts, faces.softParts, { valueScale: shownLoad, rangeScale: loadScale, threshold });
    if (applyDeformation(fea.mesh, activeScale * shownLoad, fea.deformationScale)) {
      markersRef.current?.update(fea.mesh.geometry.getAttribute("position").array);
      changed = true;
    }
    if (changed) requestRenderRef.current?.();
  };
  useEffect(() => { paintRef.current?.(); }, [fea, activeField, tinted, faces.parts, faces.softParts, activeScale, loadScale, thresholdField, thresholdValue]);

  // Where the study loads and holds the part, on the model (`feaMarkers.js`): built once per result,
  // standing on the positions drawn, the chosen load's or fixture's in the chosen colour.
  const [markers, setMarkers] = useState(null);
  useEffect(() => {
    if (!fea?.study) return undefined;
    const built = createFeaMarkers(THREE, fea);
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
  const colours = view.appearance?.colorScheme === "dark" ? MARKER_COLOURS.dark : MARKER_COLOURS.light;
  useEffect(() => {
    if (!markers) return;
    markers.style({ colours, visible: { loads: markersOn && markerShow.loads, fixtures: markersOn && markerShow.fixtures },
      chosen: (site) => markerChosen(faces, site) });
    requestRenderRef.current?.();
  }, [markers, colours, markersOn, markerShow, faces, requestRenderRef]);
  const loadLabels = useCallback(() => (markers && markersOn && markerShow.loads ? markers.labels(loadScale) : EMPTY),
    [markers, markersOn, markerShow, loadScale]);

  // Select is an FEA result's one tool, with Study (and an assembly's Parts) its panels; a GLB that is not a result has none.
  const selectActive = Boolean(fea) && !shell.previewing && shell.toolMode === GLB_TOOL.SELECT;
  const tools = fea ? [shell.tools.own({ id: GLB_TOOL.SELECT, label: "Select", icon: SELECT_ICON, panel: parts.length ? ASSEMBLY_PANELS : STUDY_PANEL })] : [];
  // One face chosen is the Reference's: its ref, what the study does to it, and Copy (the copy key too).
  const single = faces.faces.length === 1 && !faces.refs.length ? faces.faces[0] : "";
  const copyFace = useCallback(async () => {
    if (!single) return false;
    const selectors = [findingSelector(single)];
    try { await host.clipboard.writeText(source ? buildCadRefToken({ cadPath: source, selectors }) : single); return true; }
    catch (error) { shellRef.current?.reportActionError(error instanceof Error ? error.message : "Could not copy reference"); return false; }
  }, [single, source, host.clipboard]);
  const copySelection = selectActive && single ? copyFace : null;
  // Study's What you see: each control writes its value, and a moved control leaves the preset (Custom).
  const resultControls = {
    controls, values, presets, preset: activePreset,
    onChange: (id, value) => choose({ [DRIVE_KEYS[id]]: value, preset: null }),
    onPreset: (value) => {
      const preset = presets.find((entry) => entry.value === value);
      if (preset) choose({ ...Object.fromEntries(Object.entries(preset.values).map(([id, entry]) => [DRIVE_KEYS[id], entry])), preset: value });
    },
    onReset: () => choose({ ...NO_VALUES, preset: null }),
  };
  const toolPanels = fea ? <FeaStudyPanel active={selectActive} parts={parts} openPart={weakestPartIndex(fea)} rows={rows} verdict={verdict} chosen={faces.id} onChoose={chooseFaces}
    result={resultControls}
    reference={single ? { title: faceTitle(fea, single), ref: single, role: faceRole(fea, single), part: facePartDetail(fea, single, loadScale) } : null} onClearSelection={clearChoice}
    copy={single ? { label: "Copy", shortcut: shell.frame.copyShortcut, onCopy: copyFace } : null} /> : null;

  const showingFindings = Boolean(card) && shell.frame.viewerAlert === card;
  const overlay = fea ? (viewport) => <>
    <PointerPick viewport={viewport} scene={pickScene} enabled={selectActive} onPick={pick} />
    <FeaColourBar result={fea} field={activeField} loadScale={loadScale} raised={Boolean(animation) && shell.previewing} />
    {markers ? <FeaLoadLabels runtimeRef={viewport.runtimeRef} hostRef={viewport.hostRef} mesh={fea.mesh} labels={loadLabels}
      colours={{ ink: colours.load, halo: colours.halo }} /> : null}
    {targets.length ? <FindingRings runtimeRef={viewport.runtimeRef} hostRef={viewport.hostRef} mesh={fea.mesh} targets={targets}
      severity={finding.severity} scale={activeScale * loadScale} /> : null}
  </> : null;
  // A finding chosen in the card puts it away and rings what it names, with its sentence in Quick Edit.
  const chooseFinding = (dismiss) => (entry) => { setChosenFaces(NO_FACES); setChosen({ findings, index: entry.index }); dismiss(); };
  return <RendererShell shell={shell} tools={tools} toolPanels={toolPanels} viewportOverlay={overlay} references={references}
    onClearReferences={clearChoice} copySelection={copySelection}
    alertBody={showingFindings ? (dismiss) => <FindingsBody onShown={clearFinding} findings={findings} headings={FINDING_HEADINGS} onChoose={chooseFinding(dismiss)} /> : null}
    alertStartsDismissed={showingFindings && card.severity === "warning"} />;
}

export default function GlbRenderer(props) {
  const { data, ...view } = props;
  return <GlbSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
