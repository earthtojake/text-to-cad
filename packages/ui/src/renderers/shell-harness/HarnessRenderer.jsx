import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import * as THREE from "three";
import { EDGELESS_VIEW_FEATURES } from "@hardcore/core/common/viewSettings.js";
import { createSurfaceLook } from "@hardcore/core/lib/viewer/surfaceLook.js";
import { createPromptContext, referencePart, textPart } from "@hardcore/core/prompt";
import { Button } from "@hardcore/ui/primitives/button";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { SHELL_TOOL, useRendererShell } from "../kit/shell/useRendererShell.js";
import { createToolModes } from "../kit/tools/toolModes.js";

// TEST SCAFFOLDING. This renderer is never registered in a product: it exists so
// the shell's own tools can be driven in a real browser under a frame that is
// nothing else. The only shipping tool the shell owns is Draw, and the only
// format that has it is STEP, which is still the pre-shell renderer — so without
// this there is nowhere to exercise shell-level Draw behaviour (a fullscreen drag
// while a sketch is open, say) that STEP cannot reach yet. It draws one triangle,
// reads no bytes and talks to no backend.
//
// It also stands in for a renderer that USES the shell surfaces STEP will need
// when it moves: a viewport context menu of its own (and word of when it is up), a
// bottom action whose long label falls back to a count, the camera-settled report,
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
const LIVE = Object.freeze({ declined: {
  select: "The shell harness has nothing to select: it draws one triangle and reads no file.",
  clearSelection: "The shell harness has no selection to clear."
} });
// Deliberately far too long for any button, so what the strip shows is the count;
// pressing it leaves a short one, which fits and is shown whole. The two together
// are the measuring rule: what is shown depends on the label's WIDTH, not its text.
const LONG_LABEL = `#harness_document/${"triangle_face_0001.top_surface_of_the_first_and_only_triangle.".repeat(4)}edge_0001`;
const SHORT_LABEL = "#harness_document/triangle_face_0001";

// A renderer whose OWN context the whole frame is mounted under: both halves of the
// shell read it, so it cannot be a viewport overlay (`frameProvider`).
const HarnessFrameContext = createContext("");
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
  // The same work, now drawn: the wait is over even though the write is not.
  previewing: { load: { editPending: true, currentPreview: true } },
  // A newer revision failed and the model on screen survives it: the viewport's card says
  // so, and can be put away, because the previous version is still there to use.
  failed: {
    load: { alert: { severity: "error", blocking: false, summary: "Update failed", title: "Harness update failed",
      message: "The harness could not load its latest revision. The existing model remains visible.",
      details: "harness detail", reload: true } }
  }
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
  const shellServices = useMemo(() => ({
    preferences, onPreferenceChange: services.preferences.update, live: services.live
  }), [preferences, services]);

  // The camera-settled report is a signal, not state: counted outside React and
  // shown in the overlay, so a test reads the same number the renderer got.
  const settles = useRef(0);
  const [settleLabel, setSettleLabel] = useState("0");
  const onCameraSettled = useCallback(() => {
    settles.current += 1;
    setSettleLabel(String(settles.current));
  }, []);
  const [picked, setPicked] = useState("");
  const [menuUp, setMenuUp] = useState(false);
  const [shadowReception, setShadowReception] = useState("");
  scene.onShadowReception = setShadowReception;
  // What became of the WebGL runtime under the scene, in order.
  const [runtimeEvents, setRuntimeEvents] = useState([]);
  const runtimeLifecycle = useMemo(() => ({
    onRelease: (runtime, { handoff }) => setRuntimeEvents(events => [...events, `release:${runtime?.renderer ? "live" : "gone"}:${handoff ? "handoff" : "final"}`]),
    onContextLost: () => setRuntimeEvents(events => [...events, "lost"])
  }), []);
  const [actionLabel, setActionLabel] = useState(LONG_LABEL);
  const [stage, setStage] = useState("idle");
  // The revision on screen, which lags the one being loaded while a stage says so.
  const [shownRevision, setShownRevision] = useState("");
  // What the frame put down when the person reached for the model.
  const [putDown, setPutDown] = useState("");
  const { load: stageLoad } = LOAD_STAGES[stage] || LOAD_STAGES.idle;
  const live = useMemo(() => (shownRevision
    ? { ...LIVE, resource: () => ({ ...resource, revision: shownRevision }) }
    : LIVE), [resource, shownRevision]);

  const shell = useRendererShell({
    view, services: shellServices, resource, modelKey: view.file.path, revisionKey: "harness",
    features: EDGELESS_VIEW_FEATURES, toolModes: HARNESS_TOOL_MODES, scene,
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

  // `panel*.harness` stands in for a file with Settings (a model tab and a Position tab) and a
  // retained effect: "Keep" keeps a panel under the strip, highlighted, whatever tool is up.
  const [kept, setKept] = useState(false);
  const withPanel = view.file.path.startsWith("panel");
  const keepTool = { id: "keep", label: "Keep", icon: <span aria-hidden="true">K</span>, active: kept, disabled: shell.idle,
    onSelect: () => setKept(value => !value) };
  const panel = withPanel ? { title: "Settings", sections: [
    { id: "features", role: "model", title: "Features", content: <p data-harness-tab="features">Model tree</p> },
    { id: "position", role: "position", title: "Position", content: <p data-harness-tab="position">Joints</p> }
  ] } : null;

  return <RendererShell shell={shell} tools={withPanel ? [shell.tools.draw, keepTool] : [shell.tools.draw]} panel={panel}
    toolPanels={kept ? <div className="w-40" data-harness-kept=""><section aria-label="Kept controls"
      className="pointer-events-auto h-24 rounded-md border border-border bg-popover text-tiny">Kept</section></div> : null}
    contextMenuItems={contextMenuItems} onContextMenuOpenChange={setMenuUp}
    frameProvider={frame => <HarnessFrameContext.Provider value={`frame:${stage}`}>{frame}</HarnessFrameContext.Provider>}
    onCanvasPointerDown={() => setPutDown(`put down @${stage}`)}
    bottomAction={shell.toolMode === SHELL_TOOL.DRAW ? null : {
      label: actionLabel, shortLabel: "Copy 1 reference", title: actionLabel,
      // A renderer whose action is not a plain press renders its own control.
      render: ({ className, disabled, title, children }) => (
        <Button type="button" variant="default" size="sm" className={className} disabled={disabled} title={title}
          data-harness-bottom-action onClick={() => setActionLabel(SHORT_LABEL)}>{children}</Button>
      )
    }}
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
    </div>}/>;
}

export default function HarnessRenderer(props) {
  const { data, ...view } = props;
  return <HarnessSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
