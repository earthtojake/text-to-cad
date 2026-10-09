import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import FeaStudyPanel from "./FeaStudyPanel.jsx";
import FeaColourBar from "./FeaColourBar.jsx";
import {
  applyDeformation, deformationRange, faceIndices, faceLabel, facePromptSummary, faceRole, findingSelector, pickFace, readFeaResult, recolorByField, resultSourcePath,
  ringTargets, studyRows
} from "./feaResult.js";
import { GLB_DECLINED_LIVE_COMMANDS, GLB_TOOL, GLB_TOOL_MODES } from "./tools.js";
import { useGlbAnimation } from "./useGlbAnimation.js";
import { useGlbScene } from "./useGlbScene.js";

const LIVE = Object.freeze({ declined: GLB_DECLINED_LIVE_COMMANDS });
const NO_CHOICE = Object.freeze({ field: null, scale: null });
const FINDING_HEADINGS = Object.freeze({ fix: "Fix before using", suggestions: "Suggestions" });
const EMPTY = Object.freeze([]);
const NO_FINDING = Object.freeze({ findings: null, index: -1 });
// `refs`: what Quick Edit gets when it is not the faces' own (a part's or a joint's parts); `parts`: parts to tint.
const NO_FACES = Object.freeze({ result: null, id: "", faces: EMPTY, refs: EMPTY, parts: EMPTY, summary: "" });
const SELECT_ICON = <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />;
// Select's own panel, Study, which a person can close; a result opens with it up, except on a phone.
const STUDY_PANEL = Object.freeze({ id: "tree", label: "Study", startsClosed: false });

/** Study's row for a face, where it has one (a fixed face, a loaded face), so a pick of it marks that row. */
function faceRow(rows, ref) {
  for (const row of rows) {
    const found = row.faces?.length === 1 && row.faces[0] === ref && !row.children && !row.refs ? row : row.children ? faceRow(row.children, ref) : null;
    if (found) return found;
  }
  return null;
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

  // An FEA result (cadgen fea solve) carries its fields and true displacement in the file; which
  // field is shown and how exaggerated the displacement is are chosen in Study, per tab. That
  // choice is this renderer's one slice of the file's view (`kit/shell/fileView.js`), written
  // against the result's own fields and scale: a re-solved result opens at its own defaults.
  const fea = useMemo(() => readFeaResult(scene?.document?.scene), [scene]);
  const signature = fea ? `${fea.fields.map((entry) => entry.attribute).join(",")}:${fea.deformationScale}` : "";
  const [stored] = useState(() => view.state);
  const restored = useMemo(() => (fea ? readFileView(stored, { fea: signature }).renderer.fea || NO_CHOICE : NO_CHOICE), [fea, stored, signature]);
  const [edited, setEdited] = useState({ signature: "", ...NO_CHOICE });
  const choice = edited.signature === signature ? { ...restored, ...edited } : restored;
  const activeField = fea ? fea.fields.find((entry) => entry.attribute === choice.field) || fea.fields[0] : null;
  // A stored scale is held to the slider's own range, whatever was written.
  const range = fea ? deformationRange(fea.deformationScale) : null;
  const activeScale = fea ? clamp(finiteOr(choice.scale, fea.deformationScale), range.min, range.max) : null;
  const choiceRef = useRef(choice);
  choiceRef.current = choice;
  const rendererState = useMemo(() => (fea
    ? { signatures: { fea: signature }, read: () => ({ fea: { field: choiceRef.current.field, scale: choiceRef.current.scale } }) }
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
  const chooseFaces = useCallback((row) => { setChosen(NO_FINDING); setChosenFaces({ result: fea, id: row.id, faces: row.faces || EMPTY, refs: row.refs || EMPTY, parts: row.parts || EMPTY, summary: row.summary }); }, [fea]);
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
  const animation = useGlbAnimation(scene?.document || null, () => requestRenderRef.current?.());
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
    animation, live: LIVE, rendererState,
    // Escape lets go of what is chosen, which a result with no source to edit has no Quick Edit to clear.
    escape: { active: chosenSomething, handle: () => { if (!chosenSomething) return false; clearChoice(); return true; } }
  });
  shellRef.current = shell;
  requestRenderRef.current = shell.requestRender;
  useDeclinedSelectReference(document);

  // The colours and the drawn displacement follow the choice, in place on the loaded geometry, with
  // the faces (or a part's triangles) chosen in Study, or picked, tinted over the field.
  const tinted = useMemo(() => (fea ? faceIndices(fea, faces.faces) : EMPTY), [fea, faces]);
  useEffect(() => {
    if (fea && recolorByField(fea.mesh, activeField, fea.ramp, tinted, faces.parts)) {
      requestRenderRef.current?.();
    }
  }, [fea, activeField, tinted, faces.parts, requestRenderRef]);
  useEffect(() => {
    if (fea && applyDeformation(fea.mesh, activeScale, fea.deformationScale)) {
      requestRenderRef.current?.();
    }
  }, [fea, activeScale, requestRenderRef]);

  // Select is an FEA result's one tool, and Study its panel; a GLB that is not a result has none.
  const selectActive = Boolean(fea) && !shell.previewing && shell.toolMode === GLB_TOOL.SELECT;
  const tools = fea ? [shell.tools.own({ id: GLB_TOOL.SELECT, label: "Select", icon: SELECT_ICON, panel: STUDY_PANEL })] : [];
  // One face chosen is the Reference's: its ref, what the study does to it, and Copy (the copy key too).
  const single = faces.faces.length === 1 && !faces.refs.length ? faces.faces[0] : "";
  const copyFace = useCallback(async () => {
    if (!single) return false;
    const selectors = [findingSelector(single)];
    try { await host.clipboard.writeText(source ? buildCadRefToken({ cadPath: source, selectors }) : single); return true; }
    catch (error) { shellRef.current?.reportActionError(error instanceof Error ? error.message : "Could not copy reference"); return false; }
  }, [single, source, host.clipboard]);
  const copySelection = selectActive && single ? copyFace : null;
  const toolPanels = fea ? <FeaStudyPanel active={selectActive} result={fea} rows={rows} chosen={faces.id} onChoose={chooseFaces}
    field={activeField} scale={activeScale} onFieldChange={(attribute) => choose({ field: attribute })} onScaleChange={(scale) => choose({ scale })}
    reference={single ? { title: faceLabel(single), ref: single, role: faceRole(fea, single) } : null} onClearSelection={clearChoice}
    copy={single ? { label: "Copy", shortcut: shell.frame.copyShortcut, onCopy: copyFace } : null} /> : null;

  const showingFindings = Boolean(card) && shell.frame.viewerAlert === card;
  const overlay = fea ? (viewport) => <>
    <PointerPick viewport={viewport} scene={pickScene} enabled={selectActive} onPick={pick} />
    <FeaColourBar result={fea} field={activeField} raised={Boolean(animation)} />
    {targets.length ? <FindingRings runtimeRef={viewport.runtimeRef} hostRef={viewport.hostRef} mesh={fea.mesh} targets={targets}
      severity={finding.severity} scale={activeScale} /> : null}
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
