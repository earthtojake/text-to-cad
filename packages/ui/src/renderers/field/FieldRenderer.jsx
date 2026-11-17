import { useCallback, useMemo, useRef } from "react";
import { MousePointer2 } from "lucide-react";
import { viewFeaturesForKind } from "@cad/core/common/viewSettings.js";
import { useI18n } from "@cad/ui/i18n";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { usePreviewState, useRendererShell } from "../kit/shell/useRendererShell.js";
import { failureAlert } from "../kit/status/loadAlerts.js";
import { useSceneToolState } from "../kit/tools/sceneTools.jsx";
import { TOOL_SHORTCUTS } from "../kit/tools/toolShortcuts.js";
import { useDeclinedSelectReference, useWorkspaceDocument, workspaceLoadAlert } from "../workspace/useWorkspaceDocument.js";
import ParametersSection from "../kit/inspector/ParametersSection.jsx";
import { FIELD_DECLINED_LIVE_COMMANDS, FIELD_TOOL, FIELD_TOOL_MODES } from "./tools.js";
import { useFieldScene } from "./useFieldScene.js";

const SELECT_ICON = <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />;
const NO_REFERENCES = Object.freeze([]);
const FEATURES = viewFeaturesForKind("gsl");

function FieldSurface({ view, data }) {
  const { t } = useI18n();
  const document = useWorkspaceDocument({ view, data });
  const loaded = useFieldScene({ client: document.client, file: view.file.path, revision: document.resource?.revision || "" });
  const scene = loaded.scene;
  // A model that does not compile says why in gsl's own words, which the server answers as they are.
  const loadAlert = useMemo(() => workspaceLoadAlert({
    catalogError: document.catalogError, error: null, modelKey: document.modelKey, hasScene: Boolean(scene), t
  }) || (loaded.error ? failureAlert(document.modelKey, loaded.error?.message || loaded.error, loaded.error?.failure) : null),
  [document.catalogError, loaded.error, document.modelKey, scene, t]);

  const shellRef = useRef(null);
  const preview = usePreviewState();
  const tools = useSceneToolState({ toolModes: FIELD_TOOL_MODES, previewing: preview.previewing, fileKey: document.modelKey,
    revision: loaded.revision, measurable: false, resource: document.resource });
  const live = useMemo(() => ({ declined: FIELD_DECLINED_LIVE_COMMANDS, commands: { clearSelection: () => {} }, state: () => ({ selectedObjects: [] }) }), []);
  const shell = useRendererShell({
    view, services: document.services, resource: document.resource, modelKey: document.modelKey, revisionKey: loaded.revision,
    features: FEATURES, toolModes: FIELD_TOOL_MODES, tool: tools.tool, previewable: false, preview, scene, sceneEffects: true,
    load: { busy: loaded.busy && !scene, updating: loaded.busy && Boolean(scene), progress: loaded.progress, alert: loadAlert },
    live
  });
  shellRef.current = shell;
  useDeclinedSelectReference(document);
  // A parameter moved: the field as it is now, on the next frame. No shadow or bound of the stage's changes.
  const redraw = useCallback(() => shellRef.current?.requestFrame?.(), []);

  const strip = [shell.tools.own({ id: FIELD_TOOL.SELECT, label: t("tool.select"), shortcut: TOOL_SHORTCUTS.select, icon: SELECT_ICON })];
  const sidebar = scene?.parameters.length
    ? <ParametersSection key={document.modelKey} scene={scene} revision={loaded.revision} onChange={redraw} /> : null;
  return <RendererShell shell={shell} tools={strip} sidebar={sidebar} references={NO_REFERENCES} referenceChips={NO_REFERENCES} />;
}

export default function FieldRenderer(props) {
  const { data, ...view } = props;
  return <FieldSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
