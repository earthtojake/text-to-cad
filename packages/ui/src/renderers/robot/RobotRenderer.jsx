import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Spline, MousePointer2 } from "lucide-react";
import { EDGELESS_VIEW_FEATURES } from "@hardcore/core/common/viewSettings.js";
import { resolveLocalAssetFileRef } from "@hardcore/core/lib/urdf/meshAssetUrl.js";
import { createRobotScene } from "@hardcore/core/lib/urdf/robotScene.js";
import { srdfGroupNamesByLink } from "@hardcore/core/lib/urdf/parseSrdf.js";
import { VIEWER_SCENE_SCALE } from "@hardcore/core/lib/viewer/sceneScale.js";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { readShellState } from "../kit/shell/shellState.js";
import { useRendererShell } from "../kit/shell/useRendererShell.js";
import { failureAlert } from "../kit/status/loadAlerts.js";
import JointHandleOverlay from "../kit/tools/pose/JointHandleOverlay.jsx";
import ToolPanel from "../kit/tools/ToolPanel.jsx";
import { PointerPick } from "../kit/tools/select/usePointerPick.js";
import { useDeclinedSelectReference, useWorkspaceDocument, workspaceLoadAlert } from "../workspace/useWorkspaceDocument.js";
import PositionControls from "./PositionControls.jsx";
import LinksSection from "./LinksSection.jsx";
import SdfSection from "./SdfSection.jsx";
import { prepareRobotJointHandles, robotJointHandles, robotPosableJoints } from "./jointHandles.js";
import { createPoseStore } from "./poseStore.js";
import { ROBOT_DECLINED_LIVE_COMMANDS, ROBOT_TOOL, ROBOT_TOOL_MODES, ROBOT_TOOL_RESTORE } from "./tools.js";
import { useLinkSelection } from "./useLinkSelection.js";
import { useRobotDocument } from "./useRobotDocument.js";

const NO_HANDLES = Object.freeze([]);
const POSITION_ICON = <Spline className="size-3" strokeWidth={2} aria-hidden="true" />;
const SELECT_ICON = <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />;

function RobotSurface({ view, data }) {
  const document = useWorkspaceDocument({ view, data });
  const loaded = useRobotDocument({ entry: document.entry, resources: document.client.resources });
  const robot = loaded.robot;
  const kind = String(document.entry?.kind || "").toLowerCase();

  // ---- pose: outside React ------------------------------------------------------------
  const [restored] = useState(() => readShellState(view.state).renderer);
  const poseRef = useRef(null);
  const pose = useMemo(() => {
    if (!robot) return null;
    // A new revision of the file keeps the pose it was left in (clamped onto the new
    // description); a reopened file takes its record back only if it is the same robot.
    const carried = poseRef.current?.getSnapshot().values || (restored.signature === robot.revision ? restored.jointValues : null);
    return createPoseStore(robot.description, carried);
  }, [robot, restored]);
  poseRef.current = pose;
  const robotRef = useRef(robot);
  robotRef.current = robot;
  // The record's own slot, read when the record is WRITTEN: the pose lives outside React.
  // Until the robot has loaded there is nothing to say, and what was stored is kept.
  const rendererState = useCallback(() => (poseRef.current && robotRef.current
    ? { jointValues: poseRef.current.getSnapshot().values, signature: robotRef.current.revision } : restored), [restored]);

  // ---- scene ----------------------------------------------------------------------------
  const [scene, setScene] = useState(null);
  useLayoutEffect(() => {
    if (!robot || !pose) { setScene(null); return undefined; }
    const next = createRobotScene(THREE, robot);
    next.setJointValues(pose.getSnapshot().values);
    setScene(next);
    // Its owner releases it: the viewport only ever detaches a scene.
    return () => next.dispose();
  }, [robot, pose]);

  const loadAlert = useMemo(() => {
    if (loaded.error?.alert && !scene) {
      return { ...failureAlert(document.modelKey, loaded.error.message), ...loaded.error.alert, reason: undefined };
    }
    return workspaceLoadAlert({ catalogError: document.catalogError, error: loaded.error, modelKey: document.modelKey, hasScene: Boolean(scene) });
  }, [document.catalogError, loaded.error, document.modelKey, scene]);

  // ---- selection -------------------------------------------------------------------------
  const shellRef = useRef(null);
  const requestRender = useCallback(() => shellRef.current?.requestRender(), []);
  const selection = useLinkSelection({ scene, requestRender });
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  const live = useMemo(() => ({
    declined: ROBOT_DECLINED_LIVE_COMMANDS,
    commands: { clearSelection: () => selectionRef.current.clear() },
    state: () => ({
      selectedLinks: [...selectionRef.current.selectedLinkNames],
      selectedPartIds: (robotRef.current?.parts || []).filter(part => (selectionRef.current.selectedLinkNames.length
        ? selectionRef.current.selectedLinkNames.includes(part.linkName) : selectionRef.current.selectedComponentIds.includes(part.id))).map(part => part.id)
    })
  }), []);
  const escape = useMemo(() => ({
    active: selection.active,
    // Escape clears the selection.
    handle: () => { if (!selectionRef.current.active) return false; selectionRef.current.clear(); return true; }
  }), [selection.active]);

  const shell = useRendererShell({
    view, services: document.services, resource: document.resource, modelKey: document.modelKey, revisionKey: robot?.revision || "",
    features: EDGELESS_VIEW_FEATURES, toolModes: ROBOT_TOOL_MODES, toolRestore: ROBOT_TOOL_RESTORE, scene,
    sceneScaleMode: VIEWER_SCENE_SCALE.URDF,
    load: { busy: (loaded.busy && !scene) || (Boolean(robot) && !scene), updating: loaded.busy && Boolean(scene), progress: loaded.progress, alert: loadAlert },
    live, escape, rendererState
  });
  shellRef.current = shell;
  useDeclinedSelectReference(document);

  // ---- a pose step: k matrices, one frame, no component ----------------------------------
  const handlesRef = useRef(NO_HANDLES);
  const handleLayoutRef = useRef(null);
  useLayoutEffect(() => {
    if (!scene || !pose || !robot) { handlesRef.current = NO_HANDLES; return undefined; }
    const prepared = prepareRobotJointHandles(THREE, robot.description, scene);
    let boundsFrame = 0;
    const readHandles = () => { handlesRef.current = robotJointHandles(THREE, prepared, scene, pose.getSnapshot().values, pose.write); };
    const step = () => {
      shellRef.current?.scheduleStateSave();
      if (!scene.setJointValues(pose.getSnapshot().values)) return;
      readHandles();
      shellRef.current?.requestRender();
      // Lighting, shadows and the floor follow the posed robot: once per frame, however many writes landed in it.
      boundsFrame ||= window.requestAnimationFrame(() => { boundsFrame = 0; shellRef.current?.syncSceneBounds(); });
    };
    readHandles();
    const unsubscribe = pose.subscribe(step);
    return () => { unsubscribe(); window.cancelAnimationFrame(boundsFrame); handlesRef.current = NO_HANDLES; };
  }, [scene, pose, robot]);

  // Read-only debug/test seams: where the Pose knobs are (CSS pixels, with each joint's
  // value), where every link group IS (so a test asserts what is drawn, not what was asked
  // for), and what posing costs.
  const surfaceRenders = useRef(0);
  surfaceRenders.current += 1;
  useEffect(() => {
    const handles = () => handleLayoutRef.current?.() || [];
    const links = () => [...(scene?.linkFrames() || [])].map(([link, matrixWorld]) => ({ link, matrixWorld }));
    // What a pose step cost: the matrices it wrote, and whether this component rendered for it (it must not).
    const stats = () => ({ ...(scene?.stats || {}), surfaceRenders: surfaceRenders.current });
    Object.assign(window, { __cadJointHandles: handles, __robotLinks: links, __robotPoseStats: stats });
    return () => {
      if (window.__cadJointHandles === handles) delete window.__cadJointHandles;
      if (window.__robotLinks === links) delete window.__robotLinks;
      if (window.__robotPoseStats === stats) delete window.__robotPoseStats;
    };
  }, [scene]);

  // ---- tools -------------------------------------------------------------------------------
  // Pose exists where something can be driven: a turning or sliding joint that is not a mimic follower.
  const posable = useMemo(() => robotPosableJoints(robot?.description).length > 0, [robot]);
  const { toolMode, selectTool } = shell;
  // A robot restores into Pose before it has loaded; only a LOADED one can say it has nothing to pose.
  useEffect(() => { if (robot && !posable && toolMode === ROBOT_TOOL.POSE) selectTool(ROBOT_TOOL.SELECT); }, [robot, posable, toolMode, selectTool]);
  // A selection exists only while Select is the tool: leaving it drops the selection.
  const clearSelection = selection.clear;
  useEffect(() => { if (toolMode !== ROBOT_TOOL.SELECT) clearSelection(); }, [toolMode, clearSelection]);
  const poseActive = !shell.presenting && posable && Boolean(scene) && toolMode === ROBOT_TOOL.POSE;
  const selectActive = !shell.presenting && Boolean(scene) && toolMode === ROBOT_TOOL.SELECT;

  // Choosing a link or an object under another tool returns to Select first; its Links and the
  // Reference for what was chosen are Select's panels, so they are then on screen.
  const toSelect = useCallback(() => selectTool(ROBOT_TOOL.SELECT), [selectTool]);
  const treeSelection = useMemo(() => ({
    ...selection,
    select: (id, options) => { selection.select(id, options); if (id) toSelect(); },
    selectLink: (name, options) => { selection.selectLink(name, options); if (name) toSelect(); }
  }), [selection, toSelect]);
  const pickSelection = selection.pick;
  const handlePick = useCallback((hit, modifiers) => { pickSelection(hit, modifiers); if (hit) toSelect(); }, [pickSelection, toSelect]);

  // A mesh the description names, as the path the host opens. It resolves against the
  // opened file exactly as the mesh loader does (an SRDF's URDF is always beside it); a
  // `package://` reference, or one that leaves the served root, has no path here.
  const modelKey = document.modelKey;
  const hostPath = String(document.entry?.rootRelativeFile || "").trim() || modelKey;
  const meshPath = useCallback((filename) => {
    const path = resolveLocalAssetFileRef(hostPath, filename);
    return path && !path.startsWith("/") && !path.startsWith("../") ? path : "";
  }, [hostPath]);
  const groupNamesByLink = useMemo(() => (robot?.description?.srdf ? srdfGroupNamesByLink(robot.description) : null), [robot]);

  // Position is offered where a joint can be driven; until the robot has loaded that is not
  // known, and it is shown, idle, meanwhile.
  const tools = [
    shell.tools.own({ id: ROBOT_TOOL.SELECT, label: "Select", icon: SELECT_ICON }),
    !robot || posable ? shell.tools.own({ id: ROBOT_TOOL.POSE, label: "Position", icon: POSITION_ICON,
      // Its panel is in the tool stack for as long as it is the tool.
      onSelect: () => { if (!poseActive) selectTool(ROBOT_TOOL.POSE); } }) : null
  ].filter(Boolean);
  // The tool stack: Select's Links and Reference (and an SDF's own metadata), then Position's joints.
  const linksShown = !shell.presenting && toolMode === ROBOT_TOOL.SELECT;
  const toolPanels = <>
    <LinksSection key={modelKey} active={linksShown} description={robot?.description || null} components={robot?.components}
      parts={robot?.parts} selection={treeSelection} groupNamesByLink={groupNamesByLink} meshPath={meshPath} onOpenFile={view.onOpenFile} />
    {kind === "sdf" ? <ToolPanel title="SDF" label="SDF" fit="details" collapsible defaultCollapsed hidden={!linksShown}>
      <SdfSection info={robot?.description?.sdf || null} movableJointCount={pose?.joints.length || 0} />
    </ToolPanel> : null}
    {/* No heading: its Pose row leads it. */}
    {posable && pose ? <ToolPanel label="Position controls" fit="details" hidden={!poseActive}>
      <PositionControls key={robot.revision} pose={pose} />
    </ToolPanel> : null}
  </>;

  return <RendererShell shell={shell} tools={tools} toolPanels={toolPanels}
    viewportOverlay={viewport => <>
      {poseActive ? <JointHandleOverlay handlesRef={handlesRef} layoutSeamRef={handleLayoutRef} {...viewport} /> : null}
      <PointerPick viewport={viewport} scene={scene} enabled={selectActive} onPick={handlePick} onHover={selection.hoverHit} />
    </>} />;
}

export default function RobotRenderer(props) {
  const { data, ...view } = props;
  return <RobotSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
