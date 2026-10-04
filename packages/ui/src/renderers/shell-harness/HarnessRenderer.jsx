import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import * as THREE from "three";
import { EDGELESS_VIEW_FEATURES } from "@text-to-cad/core/common/viewSettings.js";
import { createSurfaceLook } from "@text-to-cad/core/lib/viewer/surfaceLook.js";
import { createPromptContext, referencePart, textPart } from "@text-to-cad/core/prompt";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { SHELL_TOOL, useRendererShell } from "../kit/shell/useRendererShell.js";
import { createToolModes } from "../kit/tools/toolModes.js";
import ToolPanel, { ToolPanelClose } from "../kit/tools/ToolPanel.jsx";

// TEST SCAFFOLDING. This renderer is never registered in a product: it exists so
// the shell's own tools can be driven in a real browser under a frame that is
// nothing else. The only shipping tool the shell owns is Draw, and the only
// format that has it is STEP, which is still the pre-shell renderer — so without
// this there is nowhere to exercise shell-level Draw behaviour (a fullscreen drag
// while a sketch is open, say) that STEP cannot reach yet. It draws one triangle,
// reads no bytes and talks to no backend.
//
// It also stands in for a renderer that USES the shell surfaces STEP will need
// when it moves: a viewport context menu of its own (and word of when it is up), the
// host's capture request (its own snapshot builder), the camera-settled report,
// a scene that ARRIVES in place (`complete`, `viewport.commitScene()`), and what
// happens to the WebGL runtime under it (`runtimeLifecycle`). Each is exercised here
// against the real shell in a real browser.
//
// It is registered by `harness/index.tsx` alone (`*.harness` files) and lives
// here rather than under `renderers/harness/` only because the library build
// does not compile a `harness` directory, and a browser test must drive the
// COMPILED package. When STEP moves onto the shell, delete this and drive those
// cases through STEP.

// Draw and nothing else: with no tool taken up, "" is the mode, exactly as the
// shell records for a renderer that hands over no tools at all.
const HARNESS_TOOL_MODES = createToolModes({ defaultMode: "", modes: { [SHELL_TOOL.DRAW]: { toggles: true } } });
// A file with a tool stack (`panel*.harness`) opens in Select, as STEP and robots do: the tool
// whose tree a person can close, and whose press while it is up opens it again.
const SELECT_TOOL = "select";
const PANEL_TOOL_MODES = createToolModes({ defaultMode: SELECT_TOOL, modes: { [SELECT_TOOL]: {}, [SHELL_TOOL.DRAW]: { toggles: true } } });
const LIVE = Object.freeze({ declined: {
  select: "The shell harness has nothing to select: it draws one triangle and reads no file.",
  clearSelection: "The shell harness has no selection to clear."
} });

// A renderer whose OWN context the whole frame is mounted under: both halves of the
// shell read it, so it cannot be a viewport overlay (`frameProvider`).
const HarnessFrameContext = createContext("");
const EMPTY_COMMANDS = Object.freeze({});
const NO_COMMANDS = () => EMPTY_COMMANDS;
const NO_SUBSCRIPTION = () => () => {};
function FrameContextNote() {
  return <span data-harness-frame-context>{useContext(HarnessFrameContext)}</span>;
}

// The state a document that is EDITED while it is open moves through. Every one of
// these is optional to the shell: `idle` is a renderer that only downloads its file.
const LOAD_STAGES = Object.freeze({
  idle: { load: {} },
  finding: { load: { busy: true, finding: true } },
  // Queued work of the person's own, with nothing of it on screen yet.
  editing: { load: { editPending: true } },
  // A newer revision failed and the model on screen survives it: the viewport's card says
  // so, and can be put away, because the previous version is still there to use.
  failed: {
    load: { alert: { severity: "error", blocking: false, summary: "Update failed", title: "Harness update failed",
      message: "The harness could not load its latest revision. The existing model remains visible.",
      details: "harness detail", reload: true } }
  },
  // A load the model did not survive: nothing on screen is the file's to work on.
  broken: {
    load: { alert: { severity: "error", summary: "Load failed", title: "Couldn’t load the harness model",
      message: "The harness file could not be loaded.", reload: true } }
  },
  // Not loading, and no scene to work on yet: the chrome is up, and idle.
  unready: { load: {}, scene: false }
});

/** One triangle, as the kit's scene contract (`kit/scene.js`) sees it. */
function createTriangleScene() {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array([0, 0, 0, 20, 0, 0, 0, 20, 0]), 3));
  geometry.computeVertexNormals();
  const material = new THREE.MeshPhysicalMaterial({ color: 0x8899aa, side: THREE.DoubleSide });
  const root = new THREE.Group();
  root.name = "harness-document";
  root.add(new THREE.Mesh(geometry, material));
  const look = createSurfaceLook(THREE, root);
  const bounds = { min: [0, 0, 0], max: [20, 20, 0] };
  return {
    object3D: root, bounds, restBounds: bounds,
    // It opens ARRIVING, with no box declared for the whole of it: the viewport frames what is
    // there, and frames it once more when `arrive(true)` says the box can grow no more.
    complete: false,
    // This scene's one surface never takes a shadow, whatever the view says: it is TOLD the
    // setting and keeps its own rule, so the viewport must not set its meshes itself.
    setShadowReception(receives) { this.onShadowReception?.(`${receives}:${root.children[0].receiveShadow}`); },
    // The same identity, changed in place: more of the scene "arrives" (it grows fourfold)
    // while it is still incomplete, and then it is whole.
    arrive(complete) {
      const size = 80;
      root.scale.setScalar(size / 20);
      root.updateMatrixWorld(true);
      this.bounds = this.restBounds = { min: [0, 0, 0], max: [size, size, 0] };
      this.complete = complete;
    },
    setSurfaceLook(next) { look.apply(next ? { ...next, authored: false } : null); },
    dispose() { root.removeFromParent(); look.dispose(); material.dispose(); geometry.dispose(); }
  };
}

function HarnessSurface({ view, data }) {
  const { services } = data;
  const preferences = useSyncExternalStore(services.preferences.subscribe, services.preferences.getSnapshot, services.preferences.getSnapshot);
  const [scene] = useState(createTriangleScene);
  useEffect(() => () => scene.dispose(), [scene]);
  const resource = useMemo(() => ({ kind: "workspace-file", workspaceId: view.source.id, path: view.file.path, revision: "harness" }),
    [view.source.id, view.file.path]);
  // The host's capture request, as every renderer takes it (`useWorkspaceDocument`).
  const commands = useSyncExternalStore(services.commands?.subscribe || NO_SUBSCRIPTION,
    services.commands?.getSnapshot || NO_COMMANDS, NO_COMMANDS);
  const shellServices = useMemo(() => ({
    preferences, onPreferenceChange: services.preferences.update, live: services.live,
    captureRequest: commands.captureRequest, acknowledgeCommand: services.commands?.acknowledge
  }), [preferences, services, commands.captureRequest]);

  // The camera-settled report is a signal, not state: counted outside React and
  // shown in the overlay, so a test reads the same number the renderer got.
  const settles = useRef(0);
  const [settleLabel, setSettleLabel] = useState("0");
  const onCameraSettled = useCallback(() => {
    settles.current += 1;
    setSettleLabel(String(settles.current));
  }, []);
  const [picked, setPicked] = useState("");
  // The noted press is the harness's selection: the reference a Quick Edit carries.
  const references = useMemo(() => (picked ? [{ resource, target: { kind: "cad-selector", selectors: [`press-${picked.replace(",", "-")}`] } }] : []),
    [picked, resource]);
  const [menuUp, setMenuUp] = useState(false);
  const [shadowReception, setShadowReception] = useState("");
  scene.onShadowReception = setShadowReception;
  // What became of the WebGL runtime under the scene, in order.
  const [runtimeEvents, setRuntimeEvents] = useState([]);
  const runtimeLifecycle = useMemo(() => ({
    onRelease: (runtime, { handoff }) => setRuntimeEvents(events => [...events, `release:${runtime?.renderer ? "live" : "gone"}:${handoff ? "handoff" : "final"}`]),
    onContextLost: () => setRuntimeEvents(events => [...events, "lost"])
  }), []);
  const [stage, setStage] = useState("idle");
  // The revision on screen, which lags the one being loaded while a stage says so.
  const [shownRevision, setShownRevision] = useState("");
  // What the frame put down when the person reached for the model.
  const [putDown, setPutDown] = useState("");
  const { load: stageLoad, scene: stageScene = true } = LOAD_STAGES[stage] || LOAD_STAGES.idle;
  const live = useMemo(() => (shownRevision
    ? { ...LIVE, resource: () => ({ ...resource, revision: shownRevision }) }
    : LIVE), [resource, shownRevision]);

  // `panel*.harness` stands in for a file whose tool stack is full (below); it opens in Select.
  const withPanel = view.file.path.startsWith("panel");
  // `flat*.harness` stands in for a view that is not 3D, a drawing's: its renderer does not declare Preview.
  const previewable = !view.file.path.startsWith("flat");
  const shell = useRendererShell({
    view, services: shellServices, resource, modelKey: view.file.path, revisionKey: "harness",
    features: EDGELESS_VIEW_FEATURES, toolModes: withPanel ? PANEL_TOOL_MODES : HARNESS_TOOL_MODES, previewable, scene: stageScene ? scene : null,
    load: { busy: false, ...stageLoad },
    live, onCameraSettled, runtimeLifecycle,
    // A renderer whose references are its own vocabulary assembles its own snapshot.
    promptContext: ({ resource: shown, references, capture }) => createPromptContext([
      referencePart({ resource: { ...shown }, target: { kind: "whole-resource" } }, "source"),
      ...references.map((reference, index) => textPart(`harness:${reference.note}`, `note-${index}`)),
      { id: "capture", kind: "attachment", name: "harness-view.png", mimeType: "image/png", content: capture, about: ["source"] }
    ]),
    promptReferences: () => [{ note: `${stage}@${shownRevision || resource.revision}` }],
    // A file named for it stands in for a scene drawn with hairlines.
    preserveInteractionPixelRatio: view.file.path.startsWith("hairline")
  });

  // Shift means "nothing to offer here", which must open no menu at all.
  const contextMenuItems = useCallback(press => (press.shiftKey ? null : [
    { id: "note", label: "Note the press", onSelect: () => setPicked(`${Math.round(press.clientX)},${Math.round(press.clientY)}`) },
    { id: "clear", label: "Clear the note", separatorBefore: true, disabled: !picked, onSelect: () => setPicked("") }
  ]), [picked]);

  // `panel*.harness` stands in for a file whose tool stack is full: a tree far taller than any
  // viewer, which Select's press brings back once its X has closed it; the Reference for a
  // selection, sized on its own; a retained effect — "Keep" keeps a small panel under them,
  // highlighted, whatever tool is up — and "Pose", a tool whose panel is the person's to size
  // like the tree.
  const [kept, setKept] = useState(false);
  const [posing, setPosing] = useState(false);
  // `panel-short.harness` turns the heights round: a tree of two rows and a Reference of many.
  const short = view.file.path.startsWith("panel-short");
  const [treeRows, referenceRows] = short ? [2, 40] : [120, 8];
  // `panel-part.harness` stands in for a single part, whose tree starts closed.
  const part = view.file.path.startsWith("panel-part");
  const selectTool = shell.tools.own({ id: SELECT_TOOL, label: "Select", icon: <span aria-hidden="true">S</span>,
    panel: { id: "tree", label: "Harness tree", startsClosed: part } });
  const keepTool = { id: "keep", label: "Keep", icon: <span aria-hidden="true">K</span>, active: kept, disabled: shell.idle,
    onSelect: () => setKept(value => !value) };
  const poseTool = { id: "pose", label: "Pose", icon: <span aria-hidden="true">P</span>, active: posing, disabled: shell.idle,
    onSelect: () => setPosing(value => !value) };
  const rows = (count, name) => <ul className="px-2 py-1">{Array.from({ length: count }, (_, index) =>
    <li key={index} className="flex h-6 items-center">{name} {index + 1}</li>)}</ul>;
  const toolPanels = <>
    {withPanel ? <>
      <ToolPanel id="tree" label="Harness tree" fit="tree" resizable closable collapsible={false}
        header={<p className="flex h-9 items-center border-b px-2"><span className="flex-1">Filter</span><ToolPanelClose /></p>}>{rows(treeRows, "Row")}</ToolPanel>
      <ToolPanel id="reference" title="Reference" label="Harness reference" fit="details" resizable onClose={() => {}}>{rows(referenceRows, "Fact")}</ToolPanel>
      {posing ? <ToolPanel id="position" title="Position" label="Harness position" fit="details" resizable collapsible={false} onClose={() => setPosing(false)}>{rows(30, "Joint")}</ToolPanel> : null}
    </> : null}
    {kept ? <ToolPanel id="kept" title="Kept" label="Kept controls" onClose={() => setKept(false)}><div className="h-16 px-2">Kept</div></ToolPanel> : null}
  </>;

  return <RendererShell shell={shell} tools={withPanel ? [selectTool, shell.tools.draw, keepTool, poseTool] : [shell.tools.draw]}
    toolPanels={toolPanels} references={references} onClearReferences={() => setPicked("")}
    contextMenuItems={contextMenuItems} onContextMenuOpenChange={setMenuUp}
    frameProvider={frame => <HarnessFrameContext.Provider value={`frame:${stage}`}>{frame}</HarnessFrameContext.Provider>}
    onCanvasPointerDown={() => setPutDown(`put down @${stage}`)}
    viewportOverlay={viewport => <div className="pointer-events-none absolute left-2 top-2 z-30 text-xs" data-harness-overlay>
      <span data-harness-camera-settles>{settleLabel}</span>
      <span data-harness-menu-note>{picked}</span>
      <span data-harness-menu-open>{menuUp ? "up" : ""}</span>
      <span data-harness-runtime>{runtimeEvents.join(" ")}</span>
      <span data-harness-shadows>{shadowReception}</span>
      <span data-harness-put-down>{putDown}</span>
      <FrameContextNote />
      <button type="button" className="pointer-events-auto" data-harness-arrive="partial"
        onClick={() => { scene.arrive(false); viewport.commitScene(); }}>partial</button>
      <button type="button" className="pointer-events-auto" data-harness-arrive="whole"
        onClick={() => { scene.arrive(true); viewport.commitScene(); }}>whole</button>
      {Object.keys(LOAD_STAGES).map(name => (
        <button key={name} type="button" className="pointer-events-auto" data-harness-stage={name}
          onClick={() => setStage(name)}>{name}</button>
      ))}
      <button type="button" className="pointer-events-auto" data-harness-shown-revision
        onClick={() => setShownRevision(current => (current ? "" : "shown-revision"))}>shown</button>
      {/* Preview asked for from outside the navbar, as a link or a host request would. */}
      <button type="button" className="pointer-events-auto" data-harness-ask-preview
        onClick={() => shell.setPreviewing(true)}>preview</button>
    </div>}/>;
}

export default function HarnessRenderer(props) {
  const { data, ...view } = props;
  return <HarnessSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
