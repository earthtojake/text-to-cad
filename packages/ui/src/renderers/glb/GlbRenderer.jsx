import { useMemo } from "react";
import { EDGELESS_VIEW_FEATURES } from "@hardcore/core/common/viewSettings.js";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { useRendererShell } from "../kit/shell/useRendererShell.js";
import { useDeclinedSelectReference, useWorkspaceDocument, workspaceLoadAlert } from "../workspace/useWorkspaceDocument.js";
import { GLB_DECLINED_LIVE_COMMANDS, GLB_TOOL_MODES } from "./tools.js";
import { useGlbAnimation } from "./useGlbAnimation.js";
import { useGlbScene } from "./useGlbScene.js";

const LIVE = Object.freeze({ declined: GLB_DECLINED_LIVE_COMMANDS });

function GlbSurface({ view, data }) {
  const document = useWorkspaceDocument({ view, data });
  const loaded = useGlbScene({ entry: document.entry, resources: document.client.resources });
  const scene = loaded.scene;
  const loadAlert = useMemo(() => workspaceLoadAlert({
    catalogError: document.catalogError, error: loaded.error, modelKey: document.modelKey, hasScene: Boolean(scene)
  }), [document.catalogError, loaded.error, document.modelKey, scene]);

  const requestRenderRef = useMemo(() => ({ current: null }), []);
  const animation = useGlbAnimation(scene?.document || null, () => requestRenderRef.current?.());
  const shell = useRendererShell({
    view, services: document.services, resource: document.resource, modelKey: document.modelKey, revisionKey: loaded.revision,
    features: EDGELESS_VIEW_FEATURES, toolModes: GLB_TOOL_MODES, scene,
    load: { busy: loaded.busy && !scene, updating: loaded.busy && Boolean(scene), progress: loaded.progress, alert: loadAlert },
    animation, live: LIVE
  });
  requestRenderRef.current = shell.requestRender;
  useDeclinedSelectReference(document, shell.setCopyStatus, GLB_DECLINED_LIVE_COMMANDS.select);

  const tools = [shell.tools.orbit, shell.tools.draw, shell.tools.animate].filter(Boolean);
  return <RendererShell shell={shell} tools={tools} inspector={{ title: "GLB", tabs: [shell.displayTab] }} />;
}

export default function GlbRenderer(props) {
  const { data, ...view } = props;
  return <GlbSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
