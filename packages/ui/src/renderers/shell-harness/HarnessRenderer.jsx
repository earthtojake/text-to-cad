import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import * as THREE from "three";
import { EDGELESS_VIEW_FEATURES } from "@hardcore/core/common/viewSettings.js";
import { createSurfaceLook } from "@hardcore/core/lib/viewer/surfaceLook.js";
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

  const shell = useRendererShell({
    view, services: shellServices, resource, modelKey: view.file.path, revisionKey: "harness",
    features: EDGELESS_VIEW_FEATURES, toolModes: HARNESS_TOOL_MODES, scene,
    load: { busy: false }, live: LIVE
  });
  return <RendererShell shell={shell} tools={[shell.tools.draw]} inspector={{ title: "Harness", tabs: [shell.displayTab] }} />;
}

export default function HarnessRenderer(props) {
  const { data, ...view } = props;
  return <HarnessSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
