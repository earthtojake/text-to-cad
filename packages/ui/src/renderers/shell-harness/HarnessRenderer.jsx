import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import * as THREE from "three";
import { EDGELESS_VIEW_FEATURES } from "@hardcore/core/common/viewSettings.js";
import { createSurfaceLook } from "@hardcore/core/lib/viewer/surfaceLook.js";
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

  const shell = useRendererShell({
    view, services: shellServices, resource, modelKey: view.file.path, revisionKey: "harness",
    features: EDGELESS_VIEW_FEATURES, toolModes: HARNESS_TOOL_MODES, scene,
    load: { busy: false }, live: LIVE, onCameraSettled, runtimeLifecycle,
    // A file named for it stands in for a scene drawn with hairlines.
    preserveInteractionPixelRatio: view.file.path.startsWith("hairline")
  });

  // Shift means "nothing to offer here", which must open no menu at all.
  const contextMenuItems = useCallback(press => (press.shiftKey ? null : [
    { id: "note", label: "Note the press", onSelect: () => setPicked(`${Math.round(press.clientX)},${Math.round(press.clientY)}`) },
    { id: "clear", label: "Clear the note", separatorBefore: true, disabled: !picked, onSelect: () => setPicked("") }
  ]), [picked]);

  return <RendererShell shell={shell} tools={[shell.tools.draw]} inspector={{ title: "Harness", tabs: [shell.displayTab] }}
    contextMenuItems={contextMenuItems} onContextMenuOpenChange={setMenuUp}
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
      <button type="button" className="pointer-events-auto" data-harness-arrive="partial"
        onClick={() => { scene.arrive(false); viewport.commitScene(); }}>partial</button>
      <button type="button" className="pointer-events-auto" data-harness-arrive="whole"
        onClick={() => { scene.arrive(true); viewport.commitScene(); }}>whole</button>
    </div>}/>;
}

export default function HarnessRenderer(props) {
  const { data, ...view } = props;
  return <HarnessSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
