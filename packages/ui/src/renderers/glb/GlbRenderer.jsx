import { useCallback, useEffect, useMemo, useRef } from "react";
import { MousePointer2 } from "lucide-react";
import { EDGELESS_VIEW_FEATURES } from "@text-to-cad/core/common/viewSettings.js";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { useRendererShell } from "../kit/shell/useRendererShell.js";
import { PointerPick } from "../kit/tools/select/usePointerPick.js";
import { useDeclinedSelectReference, useWorkspaceDocument, workspaceLoadAlert } from "../workspace/useWorkspaceDocument.js";
import LeafSection from "./LeafSection.jsx";
import { GLB_DECLINED_LIVE_COMMANDS, GLB_LEAF_DECLINED_LIVE_COMMANDS, GLB_TOOL, GLB_TOOL_MODES, GLB_TOOL_RESTORE } from "./tools.js";
import { useGlbAnimation } from "./useGlbAnimation.js";
import { useGlbScene } from "./useGlbScene.js";
import { useLeafSelection } from "./useLeafSelection.js";

const PLAIN_LIVE = Object.freeze({ declined: GLB_DECLINED_LIVE_COMMANDS });
const SELECT_ICON = <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />;
const NO_LEAVES = Object.freeze([]);

function GlbSurface({ view, data }) {
  const document = useWorkspaceDocument({ view, data });
  const loaded = useGlbScene({ entry: document.entry, resources: document.client.resources });
  const scene = loaded.scene;
  const loadAlert = useMemo(() => workspaceLoadAlert({
    catalogError: document.catalogError, error: loaded.error, modelKey: document.modelKey, hasScene: Boolean(scene)
  }), [document.catalogError, loaded.error, document.modelKey, scene]);

  // ---- leaves: an implicit part's GLB selects; every other GLB has nothing to pick --------
  const leaves = scene?.leaves?.length ? scene.leaves : NO_LEAVES;
  const selectable = leaves.length > 0;
  const shellRef = useRef(null);
  const requestRender = useCallback(() => shellRef.current?.requestRender(), []);
  const selection = useLeafSelection({ scene, requestRender });
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  const live = useMemo(() => (selectable ? {
    declined: GLB_LEAF_DECLINED_LIVE_COMMANDS,
    commands: { clearSelection: () => selectionRef.current.clear() },
    state: () => ({ selectedLeaves: [...selectionRef.current.selected] })
  } : PLAIN_LIVE), [selectable]);
  const escape = useMemo(() => ({
    active: selection.active,
    handle: () => { if (!selectionRef.current.active) return false; selectionRef.current.clear(); return true; }
  }), [selection.active]);
  // A snapshot taken with leaves picked depicts them: the file, labelled by what was chosen.
  const resource = document.resource;
  const promptReferences = useCallback(() => {
    const picked = leaves.filter(leaf => selectionRef.current.selected.includes(leaf.id));
    if (!picked.length) return [];
    return [{ resource: { ...resource }, target: { kind: "whole-resource" }, label: picked.map(leaf => leaf.label).join(", ") }];
  }, [leaves, resource]);

  const requestRenderRef = useMemo(() => ({ current: null }), []);
  const animation = useGlbAnimation(scene?.document || null, () => requestRenderRef.current?.());
  const shell = useRendererShell({
    view, services: document.services, resource, modelKey: document.modelKey, revisionKey: loaded.revision,
    features: EDGELESS_VIEW_FEATURES, toolModes: GLB_TOOL_MODES, toolRestore: GLB_TOOL_RESTORE, scene,
    load: { busy: loaded.busy && !scene, updating: loaded.busy && Boolean(scene), progress: loaded.progress, alert: loadAlert },
    animation, live, escape, promptReferences
  });
  shellRef.current = shell;
  requestRenderRef.current = shell.requestRender;
  useDeclinedSelectReference(document);

  const { toolMode } = shell;
  const clearSelection = selection.clear;
  // A selection exists only while Select is the tool: leaving it drops the selection.
  useEffect(() => { if (toolMode !== GLB_TOOL.SELECT) clearSelection(); }, [toolMode, clearSelection]);
  const selectActive = selectable && !shell.presenting && toolMode === GLB_TOOL.SELECT;
  const fileName = String(document.entry?.file || document.modelKey || "").split("/").pop() || "part.glb";

  const tools = selectable ? [shell.tools.own({ id: GLB_TOOL.SELECT, label: "Select", icon: SELECT_ICON })] : [];
  const toolPanels = selectable
    ? <LeafSection key={document.modelKey} leaves={leaves} selection={selection} resource={resource} fileName={fileName} active={selectActive} />
    : null;

  return <RendererShell shell={shell} tools={tools} toolPanels={toolPanels}
    viewportOverlay={selectable ? viewport => <PointerPick viewport={viewport} scene={scene} enabled={selectActive} onPick={selection.pick} onHover={selection.hoverHit} /> : undefined} />;
}

export default function GlbRenderer(props) {
  const { data, ...view } = props;
  return <GlbSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
