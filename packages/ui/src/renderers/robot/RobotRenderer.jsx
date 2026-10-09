import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import * as THREE from "three";
import { MousePointer2 } from "lucide-react";
import { EDGELESS_VIEW_FEATURES } from "@text-to-cad/core/common/viewSettings.js";
import { createRobotScene } from "@text-to-cad/core/lib/urdf/robotScene.js";
import { VIEWER_SCENE_SCALE } from "@text-to-cad/core/lib/viewer/sceneScale.js";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { readFileView } from "../kit/shell/fileView.js";
import { usePreviewState, useRendererShell } from "../kit/shell/useRendererShell.js";
import { failureAlert } from "../kit/status/loadAlerts.js";
import JointHandleOverlay from "../kit/tools/pose/JointHandleOverlay.jsx";
import ToolPanel from "../kit/tools/ToolPanel.jsx";
import { MotionResetButton, PositionToolIcon, positionValuesAreDefault } from "../kit/inspector/kinematicsControls.jsx";
import { PointerPick } from "../kit/tools/select/usePointerPick.js";
import { useDeclinedSelectReference, useWorkspaceDocument, workspaceLoadAlert } from "../workspace/useWorkspaceDocument.js";
import PositionControls from "./PositionControls.jsx";
import LinksSection from "./LinksSection.jsx";
import SdfSection from "./SdfSection.jsx";
import { prepareRobotJointHandles, robotJointHandles } from "./jointHandles.js";
import { createPoseStore, poseLogic } from "./poseStore.js";
import { ROBOT_DECLINED_LIVE_COMMANDS, ROBOT_TOOL, ROBOT_TOOL_MODES } from "./tools.js";
import { useLinkSelection } from "./useLinkSelection.js";
import { useRobotVisibility } from "./useRobotVisibility.js";
import { useRobotDocument } from "./useRobotDocument.js";

const NO_HANDLES = Object.freeze([]);
const SELECT_ICON = <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />;
// Select's own panel, which a person can close (`LinksSection.jsx`'s tree). A robot is never a
// single part: like an assembly's, its tree starts open, except on a phone.
const LINKS_PANEL = Object.freeze({ id: "tree", label: "Links", startsClosed: false });

function RobotSurface({ view, data }) {
  const document = useWorkspaceDocument({ view, data });
  const loaded = useRobotDocument({ entry: document.entry, client: document.client, resources: document.client.resources });
  const robot = loaded.robot;
  const kind = String(document.entry?.kind || "").toLowerCase();

  // ---- pose: outside React ------------------------------------------------------------
  // The pose slice of the file's view (`kit/shell/fileView.js`): the control values, written
  // against the payload's revision, so a reopened file takes its pose back only if it is the
  // same robot. The selection and the tree's disclosure are not in it.
  const [stored] = useState(() => view.state);
  const poseRef = useRef(null);
  const pose = useMemo(() => {
    if (!robot) return null;
    // A new revision of the file keeps the pose it was left in, and the named pose it was chosen
    // as, while what poses it — its controls and named poses — is unchanged; when that changed it
    // opens at its own opening pose: the old pose is never fitted onto other controls. The first
    // load takes the stored pose, written against this very revision.
    const previous = poseRef.current;
    if (previous) {
      const { values, groupStateId } = previous.getSnapshot();
      return previous.logic === poseLogic(robot.robot)
        ? createPoseStore(robot.robot, values, groupStateId) : createPoseStore(robot.robot);
    }
    return createPoseStore(robot.robot, readFileView(stored, { pose: robot.revision }).renderer.pose?.jointValues || null);
  }, [robot, stored]);
  poseRef.current = pose;
  const robotRef = useRef(robot);
  robotRef.current = robot;

  // ---- preview: a state of its own ---------------------------------------------------------
  // Held here because the scene's writers below run before the shell hook. The person's work —
  // the pose, the hidden visuals, what is picked and lit — reaches the scene through those writers,
  // and each draws the robot as it opens while previewing: the opening pose, every visual, nothing
  // lit. None of the work changes, so leaving preview finds the tools view exactly as it was.
  const preview = usePreviewState();
  const previewing = preview.previewing;
  const previewingRef = useRef(previewing);
  previewingRef.current = previewing;

  // ---- scene ----------------------------------------------------------------------------
  const [scene, setScene] = useState(null);
  useLayoutEffect(() => {
    if (!robot || !pose) { setScene(null); return undefined; }
    const next = createRobotScene(THREE, robot);
    next.setControlValues(pose.getSnapshot().values);
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
  // A highlight recolours links and casts no new shadow: its frame keeps the shadow maps.
  const requestHighlightFrame = useCallback(() => shellRef.current?.requestFrame?.(), []);
  const selection = useLinkSelection({ scene, requestRender: requestHighlightFrame, shown: !previewing });
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  const live = useMemo(() => ({
    declined: ROBOT_DECLINED_LIVE_COMMANDS,
    commands: { clearSelection: () => selectionRef.current.clear() },
    state: () => ({
      selectedLinks: [...selectionRef.current.selectedLinkNames],
      selectedPartIds: (robotRef.current?.parts || []).filter(part => (selectionRef.current.selectedLinkNames.length
        ? selectionRef.current.selectedLinkNames.includes(part.link) : selectionRef.current.selectedComponentIds.includes(part.id))).map(part => part.id)
    })
  }), []);
  const escape = useMemo(() => ({
    active: selection.active,
    // Escape clears the selection.
    handle: () => { if (!selectionRef.current.active) return false; selectionRef.current.clear(); return true; }
  }), [selection.active]);

  // ---- visibility: React state, the scene told ---------------------------------------------
  // A hidden visual leaves the render and the pick; the bounds (lighting, floor) follow, and the
  // view's record is saved with the ids.
  const requestVisibilityRender = useCallback(() => {
    shellRef.current?.requestRender();
    shellRef.current?.syncSceneBounds();
    shellRef.current?.scheduleStateSave();
  }, []);
  const { hiddenPartIds, changeVisibility } = useRobotVisibility({ robot, scene, requestRender: requestVisibilityRender, stored, shown: !previewing });
  // The slices are read when the view is WRITTEN: the pose lives outside React; the hidden ids
  // are React state, both against the payload's revision. Until the robot has loaded there is
  // nothing to say, and what was stored is kept.
  const rendererState = useMemo(() => (robot && pose ? {
    signatures: { pose: robot.revision, visibility: robot.revision },
    read: () => ({ pose: { jointValues: pose.getSnapshot().values }, visibility: { hiddenPartIds } })
  } : null), [robot, pose, hiddenPartIds]);

  const shell = useRendererShell({
    view, services: document.services, resource: document.resource, modelKey: document.modelKey, revisionKey: robot?.revision || "",
    features: EDGELESS_VIEW_FEATURES, toolModes: ROBOT_TOOL_MODES, previewable: true, preview, scene,
    sceneScaleMode: VIEWER_SCENE_SCALE.URDF,
    load: { busy: (loaded.busy && !scene) || (Boolean(robot) && !scene), updating: loaded.busy && Boolean(scene), progress: loaded.progress, alert: loadAlert },
    live, escape, rendererState
  });
  shellRef.current = shell;
  useDeclinedSelectReference(document);

  // ---- a pose step: k matrices, one frame, no component ----------------------------------
  const handlesRef = useRef(NO_HANDLES);
  const handleLayoutRef = useRef(null);
  // Poses the scene: the pose in hand, or in preview the opening pose.
  const presentPoseRef = useRef(null);
  useLayoutEffect(() => {
    if (!scene || !pose || !robot) { handlesRef.current = NO_HANDLES; return undefined; }
    const prepared = prepareRobotJointHandles(THREE, robot.robot, scene);
    let boundsFrame = 0;
    const readHandles = () => { handlesRef.current = robotJointHandles(THREE, prepared, scene, pose.getSnapshot().values, pose.write); };
    const present = () => {
      if (!scene.setControlValues(previewingRef.current ? pose.defaults : pose.getSnapshot().values)) return;
      readHandles();
      shellRef.current?.requestRender();
      // Lighting, shadows and the floor follow the posed robot: once per frame, however many writes landed in it.
      boundsFrame ||= window.requestAnimationFrame(() => { boundsFrame = 0; shellRef.current?.syncSceneBounds(); });
    };
    const step = () => {
      shellRef.current?.scheduleStateSave();
      present();
    };
    readHandles();
    present();
    presentPoseRef.current = present;
    const unsubscribe = pose.subscribe(step);
    return () => {
      unsubscribe(); window.cancelAnimationFrame(boundsFrame); handlesRef.current = NO_HANDLES;
      if (presentPoseRef.current === present) presentPoseRef.current = null;
    };
  }, [scene, pose, robot]);
  useLayoutEffect(() => { presentPoseRef.current?.(); }, [previewing]);

  // Read-only debug/test seams: where the Pose knobs are (CSS pixels, with each joint's
  // value), where every link IS (so a test asserts what is drawn, not what was asked
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
  // Pose exists where something can be driven: a control of the articulation.
  const posable = Boolean(pose?.controls.length);
  const { toolMode, selectTool } = shell;
  // A robot restores into Pose before it has loaded; only a LOADED one can say it has nothing to pose.
  useEffect(() => { if (robot && !posable && toolMode === ROBOT_TOOL.POSE) selectTool(ROBOT_TOOL.SELECT); }, [robot, posable, toolMode, selectTool]);
  // A selection exists only while Select is the tool: leaving it drops the selection.
  const clearSelection = selection.clear;
  useEffect(() => { if (toolMode !== ROBOT_TOOL.SELECT) clearSelection(); }, [toolMode, clearSelection]);
  const poseActive = !shell.previewing && posable && Boolean(scene) && toolMode === ROBOT_TOOL.POSE;
  const selectActive = !shell.previewing && Boolean(scene) && toolMode === ROBOT_TOOL.SELECT;

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

  const modelKey = document.modelKey;

  // Whether the pose is not the opening one, for the dot on the Position icon: a boolean read off
  // the pose store, so moving a control re-renders this only when it flips.
  const noPose = useCallback(() => () => {}, []);
  const poseCustom = useSyncExternalStore(pose ? pose.subscribe : noPose,
    () => Boolean(pose) && !positionValuesAreDefault(pose.getSnapshot().values, pose.defaults));
  // Position is offered where a control can be driven; until the robot has loaded that is not
  // known, and it is shown, idle, meanwhile.
  const tools = [
    // Links closes by its X; a press on Select while it is the tool opens it again.
    shell.tools.own({ id: ROBOT_TOOL.SELECT, label: "Select", icon: SELECT_ICON, panel: LINKS_PANEL }),
    !robot || posable ? shell.tools.own({ id: ROBOT_TOOL.POSE, label: "Position", icon: <PositionToolIcon custom={poseCustom} />,
      // Its panel is in the tool stack for as long as it is the tool.
      onSelect: () => { if (!poseActive) selectTool(ROBOT_TOOL.POSE); } }) : null
  ].filter(Boolean);
  // The tool stack: Select's Links and Reference (and an SDF's own metadata), then Position's controls.
  const linksShown = !shell.previewing && toolMode === ROBOT_TOOL.SELECT;
  const toolPanels = <>
    <LinksSection key={modelKey} active={linksShown} robot={robot?.robot || null} components={robot?.components}
      parts={robot?.parts} hiddenPartIds={hiddenPartIds} onVisibilityChange={changeVisibility} selection={treeSelection} onOpenFile={view.onOpenFile} />
    {kind === "sdf" ? <ToolPanel id="sdf" title="SDF" label="SDF" fit="details" defaultCollapsed hidden={!linksShown}>
      <SdfSection info={robot?.robot?.sdf || null} />
    </ToolPanel> : null}
    {/* Headed "Position" with its Reset; sized like the tree: its content's height, up to half the stack. */}
    {/* Its X puts Position down, back to Select (a robot's default tool); the pose stays. */}
    {posable && pose ? <ToolPanel id="position" title="Position" actions={<MotionResetButton onReset={pose.reset} />} label="Position controls"
      fit="details" resizable collapsible={false} onClose={shell.selectDefaultTool} closeLabel="Close position" hidden={!poseActive}>
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
