import { useMemo } from "react";
import { EDGELESS_VIEW_FEATURES } from "@hardcore/core/common/viewSettings.js";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { useRendererShell } from "../kit/shell/useRendererShell.js";
import { noGeometryAlert } from "../kit/status/loadAlerts.js";
import { useDeclinedSelectReference, useWorkspaceDocument, workspaceLoadAlert } from "../workspace/useWorkspaceDocument.js";
import { MESH_DECLINED_LIVE_COMMANDS } from "./tools.js";
import { useMeshScene } from "./useMeshScene.js";

const LIVE = Object.freeze({ declined: MESH_DECLINED_LIVE_COMMANDS });

function MeshSurface({ view, data }) {
  const document = useWorkspaceDocument({ view, data });
  const loaded = useMeshScene({ entry: document.entry, resources: document.client.resources });
  const scene = loaded.scene;
  const loadAlert = useMemo(() => workspaceLoadAlert({
    catalogError: document.catalogError, error: loaded.error, modelKey: document.modelKey, hasScene: Boolean(scene)
  }) || (loaded.empty ? noGeometryAlert(document.modelKey) : null),
  [document.catalogError, loaded.error, loaded.empty, document.modelKey, scene]);

  const shell = useRendererShell({
    view, services: document.services, resource: document.resource, modelKey: document.modelKey, revisionKey: loaded.revision,
    features: EDGELESS_VIEW_FEATURES, scene,
    load: { busy: loaded.busy && !scene, updating: loaded.busy && Boolean(scene), progress: loaded.progress, alert: loadAlert },
    live: LIVE
  });
  useDeclinedSelectReference(document);

  return <RendererShell shell={shell} tools={[]} />;
}

export default function MeshRenderer(props) {
  const { data, ...view } = props;
  return <MeshSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
