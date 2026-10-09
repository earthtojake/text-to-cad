import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { clamp, finiteOr } from "@text-to-cad/core/common/numbers.js";
import { EDGELESS_VIEW_FEATURES } from "@text-to-cad/core/common/viewSettings.js";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { readFileView } from "../kit/shell/fileView.js";
import { useRendererShell } from "../kit/shell/useRendererShell.js";
import { useDeclinedSelectReference, useWorkspaceDocument, workspaceLoadAlert } from "../workspace/useWorkspaceDocument.js";
import FindingsList, { findingsAlert } from "../kit/status/findings.jsx";
import FindingRings from "./FindingRings.jsx";
import { feaAnalysisSection } from "./FeaAnalysisSection.jsx";
import FeaColourBar from "./FeaColourBar.jsx";
import { applyDeformation, deformationRange, findingSelector, readFeaResult, recolorByField, resultSourcePath, ringTargets } from "./feaResult.js";
import { GLB_DECLINED_LIVE_COMMANDS } from "./tools.js";
import { useGlbAnimation } from "./useGlbAnimation.js";
import { useGlbScene } from "./useGlbScene.js";

const LIVE = Object.freeze({ declined: GLB_DECLINED_LIVE_COMMANDS });
const NO_CHOICE = Object.freeze({ field: null, scale: null });
const FINDING_HEADINGS = Object.freeze({ fix: "Fix before using", suggestions: "Suggestions" });
const NO_TARGETS = Object.freeze([]);
const NO_FINDING = Object.freeze({ findings: null, index: -1 });

/** The card's body, mounted only while the card is up: a card brought back from its icon starts with no finding chosen. */
function FindingsBody({ onShown, ...list }) {
  useEffect(() => { onShown(); }, [onShown]);
  return <FindingsList {...list} />;
}

function GlbSurface({ view, data }) {
  const document = useWorkspaceDocument({ view, data });
  const loaded = useGlbScene({ entry: document.entry, resources: document.client.resources });
  const scene = loaded.scene;
  const loadAlert = useMemo(() => workspaceLoadAlert({
    catalogError: document.catalogError, error: loaded.error, modelKey: document.modelKey, hasScene: Boolean(scene)
  }), [document.catalogError, loaded.error, document.modelKey, scene]);

  // An FEA result (cadgen fea solve) carries its fields and true displacement in the file; which
  // field is shown and how exaggerated the displacement is are chosen in Display, per tab. That
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
  const clearChoice = useCallback(() => setChosen(NO_FINDING), []);
  const finding = findings && chosen.findings === findings ? findings.find((entry) => entry.index === chosen.index) || null : null;
  // The part the result was solved from, the file a chosen finding's references name.
  const source = useMemo(() => (fea ? resultSourcePath(view.file.path, fea.document) : ""), [fea, view.file.path]);
  const references = useMemo(() => {
    if (!findings) return null;
    if (!finding || !source) return [];
    const refs = [...new Set(finding.items.map((item) => item.ref).filter(Boolean).map(findingSelector))];
    // A finding about no face is about the whole part.
    const selectors = refs.length ? refs : fea.occurrence ? [fea.occurrence] : [];
    return selectors.length ? [{ resource: { kind: "workspace-file", path: source }, target: { kind: "cad-selector", selectors },
      ...(finding.summary ? { summary: finding.summary } : {}) }] : [];
  }, [findings, finding, source, fea]);
  // The places it names, in the mesh's space with the displacement there, ringed over the view.
  const targets = useMemo(() => (finding && fea ? ringTargets(fea, finding.items.map((item) => item.at).filter(Boolean)) : NO_TARGETS),
    [finding, fea]);

  const requestRenderRef = useMemo(() => ({ current: null }), []);
  const animation = useGlbAnimation(scene?.document || null, () => requestRenderRef.current?.());
  const shellRef = useRef(null);
  const choose = useCallback((patch) => {
    setEdited({ ...choiceRef.current, ...patch, signature });
    shellRef.current?.scheduleStateSave();
  }, [signature]);
  const displaySections = useMemo(() => (fea ? [feaAnalysisSection({
    result: fea, field: activeField, scale: activeScale,
    onFieldChange: (attribute) => choose({ field: attribute }), onScaleChange: (scale) => choose({ scale })
  })] : undefined), [fea, activeField, activeScale, choose]);
  const shell = useRendererShell({
    view, services: document.services, resource: document.resource, modelKey: document.modelKey, revisionKey: loaded.revision,
    features: EDGELESS_VIEW_FEATURES, previewable: true, scene,
    load: { busy: loaded.busy && !scene, updating: loaded.busy && Boolean(scene), progress: loaded.progress, alert: loadAlert || card },
    animation, live: LIVE, rendererState, displaySections,
    // Escape lets go of a chosen finding's ring, which a result with no source to edit has no Quick Edit to clear.
    escape: { active: Boolean(finding), handle: () => { if (!finding) return false; clearChoice(); return true; } }
  });
  shellRef.current = shell;
  requestRenderRef.current = shell.requestRender;
  useDeclinedSelectReference(document);

  // The colours and the drawn displacement follow the choice, in place on the loaded geometry.
  useEffect(() => {
    if (fea && recolorByField(fea.mesh, activeField, fea.ramp)) {
      requestRenderRef.current?.();
    }
  }, [fea, activeField, requestRenderRef]);
  useEffect(() => {
    if (fea && applyDeformation(fea.mesh, activeScale, fea.deformationScale)) {
      requestRenderRef.current?.();
    }
  }, [fea, activeScale, requestRenderRef]);

  const showingFindings = Boolean(card) && shell.frame.viewerAlert === card;
  const overlay = fea ? (viewport) => <>
    <FeaColourBar result={fea} field={activeField} raised={Boolean(animation)} />
    {targets.length ? <FindingRings runtimeRef={viewport.runtimeRef} hostRef={viewport.hostRef} mesh={fea.mesh} targets={targets}
      severity={finding.severity} scale={activeScale} /> : null}
  </> : null;
  // A finding chosen in the card puts it away and rings what it names, with its sentence in Quick Edit.
  const chooseFinding = (dismiss) => (entry) => { setChosen({ findings, index: entry.index }); dismiss(); };
  return <RendererShell shell={shell} tools={[]} viewportOverlay={overlay} references={references}
    onClearReferences={clearChoice}
    alertBody={showingFindings ? (dismiss) => <FindingsBody onShown={clearChoice} findings={findings} headings={FINDING_HEADINGS} onChoose={chooseFinding(dismiss)} /> : null}
    alertStartsDismissed={showingFindings && card.severity === "warning"} />;
}

export default function GlbRenderer(props) {
  const { data, ...view } = props;
  return <GlbSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
