import { useMemo } from "react";
import { EDGELESS_VIEW_FEATURES } from "@text-to-cad/core/common/viewSettings.js";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { useRendererShell } from "../kit/shell/useRendererShell.js";
import { useDeclinedSelectReference, useWorkspaceDocument, workspaceLoadAlert } from "../workspace/useWorkspaceDocument.js";
import { useCamChrome, useCamResult, useCamView } from "./cam/useCamResult.jsx";
import { GLB_DECLINED_LIVE_COMMANDS, GLB_TOOL_MODES } from "./tools.js";
import { useGlbAnimation } from "./useGlbAnimation.js";
import { useGlbScene } from "./useGlbScene.js";

const LIVE = Object.freeze({ declined: GLB_DECLINED_LIVE_COMMANDS });

function GlbSurface({ view, data }) {
  const document = useWorkspaceDocument({ view, data });
  const loaded = useGlbScene({ entry: document.entry, resources: document.client.resources });
  // A CAM result (cadgen cam plan) has a viewer of its own (`cam/useCamResult.jsx`), loaded as its own chunk; it waits
  // for it as the file loading, so it is framed once, as the viewer draws it.
  const { kit: cv, pending } = useCamView(loaded.scene?.document?.scene);
  const scene = pending ? null : loaded.scene;
  const loadAlert = useMemo(() => workspaceLoadAlert({
    catalogError: document.catalogError, error: loaded.error, modelKey: document.modelKey, hasScene: Boolean(scene)
  }), [document.catalogError, loaded.error, document.modelKey, scene]);

  const requestRenderRef = useMemo(() => ({ current: null }), []);
  const camResult = useCamResult({ cv, scene, view, requestRenderRef });
  const animation = useGlbAnimation(scene?.document || null, () => requestRenderRef.current?.(), camResult.ownClips);
  const shell = useRendererShell({
    view, services: document.services, resource: document.resource, modelKey: document.modelKey, revisionKey: loaded.revision,
    features: EDGELESS_VIEW_FEATURES, toolModes: GLB_TOOL_MODES, previewable: true, scene,
    load: { busy: (loaded.busy || pending) && !scene, updating: loaded.busy && Boolean(scene), progress: loaded.progress, alert: loadAlert },
    animation, live: LIVE,
    // A CAM result's own state, Display sections and Escape.
    ...camResult.shellOptions
  });
  requestRenderRef.current = shell.requestRender;
  useDeclinedSelectReference(document);
  const camChrome = useCamChrome({ result: camResult, shell, scene, animation });

  return camChrome ? <RendererShell shell={shell} {...camChrome} /> : <RendererShell shell={shell} tools={[]} />;
}

export default function GlbRenderer(props) {
  const { data, ...view } = props;
  return <GlbSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
