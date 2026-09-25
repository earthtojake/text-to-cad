import { useEffect, useMemo, useState } from "react";
import { EDGELESS_VIEW_FEATURES } from "@hardcore/core/common/viewSettings.js";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { readShellState } from "../kit/shell/shellState.js";
import { useRendererShell } from "../kit/shell/useRendererShell.js";
import { useDeclinedSelectReference, useWorkspaceDocument, workspaceLoadAlert } from "../workspace/useWorkspaceDocument.js";
import FeaLegend from "./FeaLegend.jsx";
import { applyDeformation, readFeaResult, recolorByField } from "./feaResult.js";
import { GLB_DECLINED_LIVE_COMMANDS } from "./tools.js";
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

  // An FEA result (cadgen fea solve) carries its fields and true displacement in the
  // file; the legend lets the field and the exaggeration be chosen per tab.
  const fea = useMemo(() => (scene ? readFeaResult(scene) : null), [scene]);
  const [restored] = useState(() => readShellState(view.state).renderer || {});
  const [feaField, setFeaField] = useState(() => (typeof restored.feaField === "string" ? restored.feaField : null));
  const [feaScale, setFeaScale] = useState(() => (Number.isFinite(restored.feaScale) ? restored.feaScale : null));
  const rendererState = useMemo(() => (fea ? { feaField, feaScale } : restored), [fea, feaField, feaScale, restored]);

  const requestRenderRef = useMemo(() => ({ current: null }), []);
  const animation = useGlbAnimation(scene?.document || null, () => requestRenderRef.current?.());
  const shell = useRendererShell({
    view, services: document.services, resource: document.resource, modelKey: document.modelKey, revisionKey: loaded.revision,
    features: EDGELESS_VIEW_FEATURES, scene,
    load: { busy: loaded.busy && !scene, updating: loaded.busy && Boolean(scene), progress: loaded.progress, alert: loadAlert },
    animation, live: LIVE, rendererState
  });
  requestRenderRef.current = shell.requestRender;
  useDeclinedSelectReference(document);

  const requestRender = shell.requestRender;
  useEffect(() => {
    if (!fea) {
      return;
    }
    const field = fea.fields.find((entry) => entry.attribute === feaField) || fea.fields[0];
    const changed = recolorByField(fea.mesh, field)
      | applyDeformation(fea.mesh, Number.isFinite(feaScale) ? feaScale : fea.deformationScale, fea.deformationScale);
    if (changed) {
      requestRender?.();
    }
  }, [fea, feaField, feaScale, requestRender]);

  const overlay = fea ? (
    <FeaLegend
      result={fea}
      field={feaField}
      onFieldChange={setFeaField}
      deformation={feaScale}
      onDeformationChange={setFeaScale}
    />
  ) : null;

  return <RendererShell shell={shell} tools={[]} viewportOverlay={overlay} />;
}

export default function GlbRenderer(props) {
  const { data, ...view } = props;
  return <GlbSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
