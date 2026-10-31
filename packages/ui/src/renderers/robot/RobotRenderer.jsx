import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import * as THREE from "three";
import { Box, MousePointer2 } from "lucide-react";
import { PositionIcon } from "../kit/tools/ChangedDot.jsx";
import { scenePartCount, viewFeaturesForKind } from "@text-to-cad/core/common/viewSettings.js";
const URDF_JOINT_VALUE_EPSILON = 1e-9;
import { createRobotScene } from "@text-to-cad/core/lib/urdf/robotScene.js";
import { VIEWER_SCENE_SCALE } from "@text-to-cad/core/lib/viewer/sceneScale.js";
import RendererShell from "../kit/shell/RendererShell.jsx";
import { readFileView } from "../kit/shell/fileView.js";
import { usePreviewState, useRendererShell } from "../kit/shell/useRendererShell.js";
import { usePreviewScene } from "../kit/shell/usePreviewScene.js";
import { failureAlert } from "../kit/status/loadAlerts.js";
import JointHandleOverlay from "../kit/tools/pose/JointHandleOverlay.jsx";
import { useSceneToolState, useSceneTools } from "../kit/tools/sceneTools.jsx";
import ToolPanel from "../kit/tools/ToolPanel.jsx";
import { PointerPick } from "../kit/tools/select/usePointerPick.js";
import SelectFilterMenu from "../kit/tools/select/SelectFilterMenu.jsx";
import { selects } from "../kit/tools/select/selectFilter.js";
import { useDeclinedSelectReference, useWorkspaceDocument, workspaceLoadAlert } from "../workspace/useWorkspaceDocument.js";
import PositionControls from "./PositionControls.jsx";
import { positionValuesAreDefault } from "../kit/inspector/kinematicsControls.jsx";
import { useRobotReferences } from "./robotReferences.jsx";
import LinksSection from "./LinksSection.jsx";
import SdfSection from "./SdfSection.jsx";
import { prepareRobotJointHandles, robotJointHandles } from "./jointHandles.js";
import { createPoseStore, poseLogic } from "./poseStore.js";
import { ROBOT_DECLINED_LIVE_COMMANDS, ROBOT_TOOL, ROBOT_TOOL_MODES } from "./tools.js";
import { useLinkSelection } from "./useLinkSelection.js";
import { useRobotVisibility } from "./useRobotVisibility.js";
import { useRobotDocument } from "./useRobotDocument.js";
import { TOOL_SHORTCUTS } from "../kit/tools/toolShortcuts.js";
import { useI18n } from "@text-to-cad/ui/i18n";

const NO_HANDLES = Object.freeze([]);
const NO_REFERENCES = Object.freeze([]);
const SELECT_ICON = <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />;
const menuIcon = Icon => <Icon className="size-3.5" strokeWidth={2} aria-hidden="true" />;
// What a robot's Select picks (`kit/tools/select/selectFilter.js`): All, its links and its
// joints' knobs, as it opens; its links alone; or its knobs alone (a press on the model picks nothing).
const ROBOT_SELECT_DEFAULT = Object.freeze(["links", "position"]);
const ROBOT_SELECT_MODES = Object.freeze([
  { id: "all", label: "All", key: "pick.all", kinds: ROBOT_SELECT_DEFAULT, icon: menuIcon(MousePointer2) },
  { id: "links", label: "Links", key: "pick.links", kinds: ["links"], icon: menuIcon(Box) },
  { id: "position", label: "Position", key: "pick.position", kinds: ["position"], icon: menuIcon(PositionIcon) },
]);
// Solid, cut by Clip: a robot is posed, never exploded.
const CLIP_OFF = Object.freeze({ clip: { enabled: false, axis: "x", invert: false } });
// Whether a pose has a joint off its opening pose: Position is set.
const poseIsSet = pose => Boolean(pose) && Object.entries(pose.getSnapshot().values)
  .some(([name, value]) => Math.abs(value - (pose.defaults[name] ?? value)) > URDF_JOINT_VALUE_EPSILON);

// The file sidebar's Position section, its tile's dot the tools view's joints off their defaults. It
// reads the pose itself, and only whether it is off its defaults: a pose step renders it only when
// that flips, and never the surface (a pose step renders no component of the renderer).
function PositionSection({ pose, previewPose, revision }) {
  const { t } = useI18n();
  const changed = useSyncExternalStore(pose.subscribe, () => !positionValuesAreDefault(pose.getSnapshot().values, pose.defaults));
  return <ToolPanel id="position" title={t("position.title")} label={t("position.controls")} fit="details" changed={changed}>
    {/* Preview poses its own robot (`previewPose`). */}
    <PositionControls key={`${revision}:${previewPose ? "preview" : "tools"}`} pose={previewPose || pose} />
  </ToolPanel>;
}

function RobotSurface({ view, data }) {
  const { t } = useI18n();
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

  // Preview: a robot of its own (`previewScene`, below), posed by its own Position.
  const preview = usePreviewState();
  const previewing = preview.previewing;
  // The tool in hand, and Measure's session (`kit/tools/sceneTools.jsx`): Quick Edit reads it.
  const tools = useSceneToolState({ toolModes: ROBOT_TOOL_MODES, previewing, fileKey: document.modelKey, revision: robot?.revision || "",
    measurable: true, resource: document.resource });
  const { measure } = tools;
  const measureRef = useRef(measure);
  measureRef.current = measure;

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
      return { ...failureAlert(document.modelKey, loaded.error.message, undefined, false, t), ...(loaded.error.alertIn?.(t) ?? loaded.error.alert), reason: undefined };
    }
    return workspaceLoadAlert({ catalogError: document.catalogError, error: loaded.error, modelKey: document.modelKey, hasScene: Boolean(scene), t });
  }, [document.catalogError, loaded.error, document.modelKey, scene, t]);

  // ---- selection -------------------------------------------------------------------------
  const shellRef = useRef(null);
  // A highlight recolours links and casts no new shadow: its frame keeps the shadow maps.
  const requestHighlightFrame = useCallback(() => shellRef.current?.requestFrame?.(), []);
  const selection = useLinkSelection({ scene, requestRender: requestHighlightFrame, shown: true });
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
    active: selection.active || measure.drafting || measure.selected.length > 0,
    // Escape cancels a measurement in progress, then clears what is picked.
    handle: () => {
      const now = measureRef.current;
      if (now.drafting) { now.cancelDraft(); return true; }
      if (now.selected.length) { now.select([]); return true; }
      if (!selectionRef.current.active) return false;
      selectionRef.current.clear();
      return true;
    }
  }), [selection.active, measure.drafting, measure.selected.length]);

  // ---- visibility: React state, the scene told ---------------------------------------------
  // A hidden visual leaves the render and the pick; the bounds (lighting, floor) follow, and the
  // view's record is saved with the ids.
  const requestVisibilityRender = useCallback(() => {
    shellRef.current?.requestRender();
    shellRef.current?.syncSceneBounds();
    shellRef.current?.scheduleStateSave();
  }, []);
  const { hiddenPartIds, changeVisibility } = useRobotVisibility({ robot, scene, requestRender: requestVisibilityRender, stored, shown: true });
  // The slices are read when the view is WRITTEN: the pose lives outside React; the hidden ids
  // are React state, both against the payload's revision. Until the robot has loaded there is
  // nothing to say, and what was stored is kept.
  const rendererState = useMemo(() => (robot && pose ? {
    signatures: { pose: robot.revision, visibility: robot.revision },
    read: () => ({ pose: { jointValues: pose.getSnapshot().values }, visibility: { hiddenPartIds } })
  } : null), [robot, pose, hiddenPartIds]);

  // Parts where the robot draws several link meshes to colour.
  const features = useMemo(() => viewFeaturesForKind("urdf", { parts: scenePartCount(scene) }), [scene]);
  const shell = useRendererShell({
    view, services: document.services, resource: document.resource, modelKey: document.modelKey, revisionKey: robot?.revision || "",
    features, toolModes: ROBOT_TOOL_MODES, tool: tools.tool, previewable: true, preview, scene, sceneEffects: true,
    sceneScaleMode: VIEWER_SCENE_SCALE.URDF, deleteSelection: measure.removeSelected,
    load: { busy: (loaded.busy && !scene) || (Boolean(robot) && !scene), updating: loaded.busy && Boolean(scene), progress: loaded.progress, alert: loadAlert },
    live, escape, rendererState,
    // A prompt's view: the robot's pose and the parts hidden. A robot is drawn in metres.
    viewState: () => ({ jointValues: pose?.getSnapshot().values, hide: hiddenPartIds }), annotationUnits: "m"
  });
  shellRef.current = shell;
  useDeclinedSelectReference(document);

  // ---- one motion at a time: Position and Clip ----------------------------------------------
  // Clip turned on puts the pose back at the opening pose; a joint moved off it takes Clip off,
  // heard on the pose store itself, outside React: a pose step renders nothing.
  const clipSet = Boolean(shell.viewSettings.view.clip?.enabled);
  const clipSetRef = useRef(clipSet);
  clipSetRef.current = clipSet;
  useEffect(() => {
    if (!pose) return undefined;
    let wasSet = poseIsSet(pose);
    return pose.subscribe(() => {
      const set = poseIsSet(pose);
      if (set && !wasSet && clipSetRef.current) shellRef.current?.viewSettings.store.patch(CLIP_OFF);
      wasSet = set;
    });
  }, [pose]);
  // Clip turned on on this file (not a file opening cut): the pose goes back.
  const clipSeen = useRef({ file: document.modelKey, on: clipSet });
  useEffect(() => {
    const seen = clipSeen.current;
    clipSeen.current = { file: document.modelKey, on: clipSet };
    if (!clipSet || seen.on || seen.file !== document.modelKey || !pose || !poseIsSet(pose)) return;
    pose.reset();
  }, [clipSet, document.modelKey, pose]);

  // ---- a pose step: k matrices, one frame, no component ----------------------------------
  const handlesRef = useRef(NO_HANDLES);
  const handleLayoutRef = useRef(null);
  // Preview's own robot and pose: the robot as it opens, each time Preview opens, moved by the
  // Preview's Position section and gone as it closes — the tools view's robot and pose are never touched.
  const previewScene = usePreviewScene(scene, previewing);
  const previewPose = useMemo(() => (previewing && robot ? createPoseStore(robot.robot) : null), [previewing, robot]);
  useLayoutEffect(() => {
    if (!previewScene || !previewPose) return undefined;
    let boundsFrame = 0;
    const present = () => {
      if (!previewScene.setControlValues(previewPose.getSnapshot().values)) return;
      const view = shellRef.current?.frame.previewViewRef.current;
      view?.requestRender?.();
      boundsFrame ||= window.requestAnimationFrame(() => { boundsFrame = 0; shellRef.current?.frame.previewViewRef.current?.syncSceneBounds?.(); });
    };
    present();
    const unsubscribe = previewPose.subscribe(present);
    return () => { unsubscribe(); window.cancelAnimationFrame(boundsFrame); };
  }, [previewScene, previewPose]);
  const previewView = useMemo(() => ({ scene: previewScene }), [previewScene]);
  const previewSceneRef = useRef(previewScene);
  previewSceneRef.current = previewScene;
  useLayoutEffect(() => {
    if (!scene || !pose || !robot) { handlesRef.current = NO_HANDLES; return undefined; }
    const prepared = prepareRobotJointHandles(THREE, robot.robot, scene);
    let boundsFrame = 0;
    const readHandles = () => { handlesRef.current = robotJointHandles(THREE, prepared, scene, pose.getSnapshot().values, pose.write); };
    const present = () => {
      if (!scene.setControlValues(pose.getSnapshot().values)) return;
      readHandles();
      shellRef.current?.requestRender();
      // Lighting, shadows and the floor follow the posed robot: once per frame, however many writes landed in it.
      boundsFrame ||= window.requestAnimationFrame(() => { boundsFrame = 0; shellRef.current?.syncSceneBounds(); });
    };
    const step = () => { shellRef.current?.scheduleStateSave(); present(); };
    readHandles();
    present();
    const unsubscribe = pose.subscribe(step);
    return () => {
      unsubscribe(); window.cancelAnimationFrame(boundsFrame); handlesRef.current = NO_HANDLES;
    };
  }, [scene, pose, robot]);

  // Read-only debug/test seams: where the Pose knobs are (CSS pixels, with each joint's
  // value), where every link IS (so a test asserts what is drawn, not what was asked
  // for), and what posing costs.
  const surfaceRenders = useRef(0);
  surfaceRenders.current += 1;
  useEffect(() => {
    const handles = () => handleLayoutRef.current?.() || [];
    // The robot on screen: Preview's own while it is open.
    const links = () => [...((previewSceneRef.current || scene)?.linkFrames() || [])].map(([link, matrixWorld]) => ({ link, matrixWorld }));
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
  // What Select picks: Links and Position, each on its own; another file starts with both.
  const [selectFilter, setSelectFilter] = useState(ROBOT_SELECT_DEFAULT);
  useEffect(() => { setSelectFilter(ROBOT_SELECT_DEFAULT); }, [document.modelKey]);
  // A selection outlives Select: Quick Edit names it and the view lights it under any tool, until it
  // is cleared. Picking is Select's alone, and so are the joints' knobs, while it picks them.
  const clearSelection = selection.clear;
  const selectActive = !shell.previewing && Boolean(scene) && toolMode === ROBOT_TOOL.SELECT;
  const poseActive = selectActive && posable && selects(selectFilter, "position");
  const picksLinks = selectActive && selects(selectFilter, "links");

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

  // Select, its filter the chevron's menu: Position offered where a control can be driven (until
  // the robot has loaded that is not known, and it is offered meanwhile); then Annotate, Measure and Clip.
  const sceneTools = useSceneTools({ shell, scene, features, state: tools, measurable: true, clearParts: clearSelection });
  const strip = [
    shell.tools.own({ id: ROBOT_TOOL.SELECT, label: t("tool.select"), shortcut: TOOL_SHORTCUTS.select, icon: SELECT_ICON,
      // A robot with nothing to pose has one thing to pick, and no menu.
      menu: robot && !posable ? null : <SelectFilterMenu value={selectFilter} modes={ROBOT_SELECT_MODES}
        onChange={value => { setSelectFilter(value); selectTool(ROBOT_TOOL.SELECT); }} /> }),
    ...sceneTools.tools
  ];
  // The file sidebar, whatever the tool: the Links (and an SDF's own metadata), then Position's controls.
  const sidebarShown = !shell.previewing;
  const sidebar = <>
    <LinksSection key={modelKey} active={sidebarShown} robot={robot?.robot || null} components={robot?.components}
      parts={robot?.parts} hiddenPartIds={hiddenPartIds} onVisibilityChange={changeVisibility} selection={treeSelection} onOpenFile={view.onOpenFile} />
    {kind === "sdf" ? <ToolPanel id="sdf" title="SDF" label="SDF" fit="details" defaultCollapsed>
      <SdfSection info={robot?.robot?.sdf || null} />
    </ToolPanel> : null}
    {/* Headed "Position"; its Pose row's Default puts the joints back. */}
    {posable && pose ? <PositionSection pose={pose} previewPose={previewPose} revision={robot.revision} /> : null}
  </>;

  // What is selected, for Quick Edit: each link (an object by its link) as a reference into the
  // description, and as a chip whose card says what the description says of it.
  const { references, chips: referenceChips } = useRobotReferences({ robot: robot?.robot || null, components: robot?.components,
    selection, resource: shell.frame.resource, onOpenFile: view.onOpenFile });

  // A link pasted into Quick Edit's note, by its name and the solid's glyph (as its chip shows it),
  // where it is one of this file's.
  const resourcePath = shell.frame.resource?.path;
  const nameLink = useCallback(reference => (reference?.resource?.path === resourcePath && reference.target?.kind === "cad-selector"
    ? { name: reference.target.selectors.join(", "), kind: "solid" } : ""), [resourcePath]);

  return <RendererShell shell={shell} tools={strip} subToolbar={sceneTools.subToolbar} sidebar={sidebar} previewView={previewView}
    references={shell.previewing ? NO_REFERENCES : references} referenceChips={shell.previewing ? NO_REFERENCES : referenceChips}
    nameReference={nameLink}
    onClearReferences={() => { clearSelection(); measure.select([]); }}
    onSelectPress={sceneTools.onSelectPress} onSelectHover={sceneTools.onSelectHover}
    viewportOverlay={viewport => <>
      {sceneTools.overlay(viewport)}
      {poseActive ? <JointHandleOverlay handlesRef={handlesRef} layoutSeamRef={handleLayoutRef} {...viewport} /> : null}
      <PointerPick viewport={viewport} scene={scene} enabled={picksLinks} onPick={handlePick} onHover={selection.hoverHit} />
    </>} />;
}

export default function RobotRenderer(props) {
  const { data, ...view } = props;
  return <RobotSurface key={JSON.stringify([view.source.id, view.file.path])} view={view} data={data} />;
}
