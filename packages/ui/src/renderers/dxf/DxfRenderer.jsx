import { useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Box, Square } from "lucide-react";
import { EDGELESS_VIEW_FEATURES } from "@hardcore/core/common/viewSettings.js";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { readShellState } from "../kit/shell/shellState.js";
import { useRendererShell } from "../kit/shell/useRendererShell.js";
import { useDeclinedSelectReference, useWorkspaceDocument, workspaceLoadAlert } from "../workspace/useWorkspaceDocument.js";
import { createDxfScene } from "./dxfScene.js";
import { DXF_DECLINED_LIVE_COMMANDS } from "./tools.js";
import { useDxfDocument } from "./useDxfDocument.js";
import { useDxfSettings } from "./useDxfSettings.js";
import { BendsTab } from "./tabs/BendsTab.jsx";
import { LayersTab } from "./tabs/LayersTab.jsx";
import { MaterialTab } from "./tabs/MaterialTab.jsx";

/** The Inspector's tabs. Ids the Display tab's own id joins; a stored tab a file does not
 *  have falls back to the first, so a remembered "bends" before the parse is harmless. */
export const DXF_TAB = Object.freeze({ MATERIAL: "material", BENDS: "bends", LAYERS: "dxfLayers" });
const LIVE = Object.freeze({ declined: DXF_DECLINED_LIVE_COMMANDS });

/** A layout the bend mesher could not extrude still HAS its line-work; saying so beats an
 *  empty viewport, and beats the endless spinner it used to sit under. */
function meshFallbackAlert(modelKey, failure) {
  return {
    severity: "warning", blocking: false, summary: "No flat pattern",
    title: "No closed cut contour",
    message: `“${modelKey}” has no closed contour to extrude, so it is shown as its line-work. Thickness and bends have nothing to apply to.`,
    recovery: "Close the cut profile in the source drawing, then reload.",
    details: String(failure?.message || failure)
  };
}

function DxfSurface({ view, data }) {
  const workspace = useWorkspaceDocument({ view, data });
  const loaded = useDxfDocument({ entry: workspace.entry, resources: workspace.client.resources });

  const scene = useMemo(() => (loaded.dxf ? createDxfScene(THREE, loaded.dxf) : null), [loaded.dxf]);
  // Its owner releases it: the viewport only ever detaches a scene.
  useLayoutEffect(() => () => scene?.dispose(), [scene]);

  const [restored] = useState(() => readShellState(view.state).renderer);
  const settings = useDxfSettings(restored, scene?.bendLines.length ?? 0);
  const sceneSettings = settings.scene;

  const loadAlert = useMemo(() => workspaceLoadAlert({
    catalogError: workspace.catalogError, error: loaded.error, modelKey: workspace.modelKey, hasScene: Boolean(scene)
  }) || (scene?.meshFailure ? meshFallbackAlert(workspace.modelKey, scene.meshFailure) : null),
  [workspace.catalogError, loaded.error, workspace.modelKey, scene]);

  // A document IS a plan: it has no third dimension to look at, so it opens locked and the
  // 2D/3D action has nothing to offer.
  const layout = scene?.presentation === "layout";
  const planView = scene ? !layout || settings.state.view === "2d" : settings.state.view === "2d";
  const navigationActions = useMemo(() => (layout ? [{
    id: "drawing-projection",
    label: settings.state.view === "2d" ? "Switch to 3D view" : "Switch to 2D view",
    icon: settings.state.view === "2d" ? Box : Square,
    disabled: loaded.busy && !scene,
    onInvoke: () => settings.setView(settings.state.view === "2d" ? "3d" : "2d")
  }] : []), [layout, scene, settings.state.view, settings.setView, loaded.busy]);

  const shell = useRendererShell({
    view, services: workspace.services, resource: workspace.resource, modelKey: workspace.modelKey,
    revisionKey: loaded.revision, features: EDGELESS_VIEW_FEATURES, scene,
    load: { busy: loaded.busy && !scene, updating: loaded.busy && Boolean(scene), progress: loaded.progress, alert: loadAlert },
    live: LIVE, planView, navigationActions, rendererState: settings.record
  });
  useDeclinedSelectReference(workspace, shell.setCopyStatus, DXF_DECLINED_LIVE_COMMANDS.select);

  // Posing the scene is synchronous and BEFORE paint, so a slider tick never shows one
  // un-posed frame — and it must ask for that frame. The viewport's render loop is on
  // demand: `update` rewrites the geometry, and without this the folded sheet sits in
  // memory until something else (a camera move, a Display change, a capture) happens to
  // draw a frame. That is exactly the shape of bug a screenshot catches and a capture
  // cannot, because capturing renders.
  // (`shell.requestRender` is a fresh closure per render, so it is read through a ref: a
  // settings change is what re-poses the scene, never a re-render of this component.)
  const requestRender = useRef(shell.requestRender);
  requestRender.current = shell.requestRender;
  useLayoutEffect(() => {
    if (!scene) return;
    scene.update(sceneSettings);
    requestRender.current();
  }, [scene, sceneSettings]);

  // 2D and 3D are camera moves, not scene changes: switching eases the camera between the
  // top face ("z" — looking straight down at a flat pattern IS the 2D view) and the default
  // three-quarter view. Opening is NOT a switch: the viewport frames the file itself, from
  // the lock when it is locked and from the camera the file recorded when it has one.
  const viewerRef = shell.viewerRef;
  const view3d = settings.state.view === "3d";
  const appliedView = useRef(null);
  useLayoutEffect(() => {
    if (!layout) return;
    const previous = appliedView.current;
    appliedView.current = view3d;
    if (previous === null || previous === view3d) return;
    if (view3d) viewerRef.current?.activateDefaultViewPlane?.();
    else viewerRef.current?.activateViewPlaneFace?.("z");
  }, [layout, view3d, viewerRef]);

  // Tabs and tools are per PRESENTATION: what a flat pattern offers is not what a drawing
  // does. A new presentation adds its own arm here and leaves these two alone.
  const layersTab = (scene?.layers.length ?? 0) > 1 ? { id: DXF_TAB.LAYERS, title: "Layers",
    content: <LayersTab layers={scene.layers} hiddenLayers={settings.state.hiddenLayers}
      onLayerVisibilityChange={settings.setLayerVisible} /> } : null;
  const tabs = (layout
    ? [{ id: DXF_TAB.MATERIAL, title: "Material", content: <MaterialTab settings={settings} /> },
      scene.bendLines.length ? { id: DXF_TAB.BENDS, title: "Bends", content: <BendsTab settings={settings} /> } : null,
      layersTab]
    // A drawing has no stock to give it and nothing to fold; its layers are all it has.
    : [{ id: DXF_TAB.MATERIAL, title: "Material", content: <MaterialTab settings={settings} /> }, layersTab]
  ).concat(shell.displayTab).filter(Boolean);

  return <RendererShell shell={shell} tools={[]} inspector={{ title: "DXF", tabs }} />;
}

export default function DxfRenderer(props) {
  const { data, ...view } = props;
  return <DxfSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
