import { useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { MousePointer2 } from "lucide-react";
import { readFileView } from "../../kit/shell/fileView.js";
import { ViewerHostContext } from "../../../host/context.js";
import { GLB_TOOL } from "../tools.js";
import { carriesCamJob } from "./detect.js";

/**
 * What GlbRenderer needs to show a CAM result (`cadgen cam plan`): the result's own viewer, loaded as its own chunk
 * (`camView.jsx`), the job read from the file, Display's gates over its paths, stock, fixtures and tool, the playbar
 * clips that run the cut, and Select with its Job panel. A GLB that is not a result gets nulls throughout.
 *
 * `useCamResult` runs before the shell is made (what the shell is given), `useCamChrome` after it (the tool, its panel
 * and the viewport overlay, which read the shell).
 */

const EMPTY = Object.freeze([]);
const SELECT_ICON = <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />;
// What a CAM result's Display gates keep in the file's view, written against the result's schema.
const CAM_SIGNATURE = "cam:1";
const NO_CAM_CHOICE = Object.freeze({ result: null, id: "" });

// The CAM result viewer (`camView.jsx`), once a result has loaded it, for every result after it.
let camView = null;
/** Loads the CAM result viewer: its own chunk, which a plain GLB never fetches. */
export const loadCamView = () => import("../camView.jsx").then((module) => { camView = module; return module; });

/**
 * The CAM result viewer for a scene that carries a job (`kit`), loaded the first time one does; `pending` while it
 * loads. A plain GLB's `kit` is null, and so is a result's should the chunk fail to load: it is then drawn as a plain GLB.
 */
export function useCamView(root) {
  const wanted = useMemo(() => carriesCamJob(root), [root]);
  const [kit, setKit] = useState(camView);
  useEffect(() => {
    if (!wanted || kit) return undefined;
    let live = true;
    loadCamView().then((module) => { if (live) setKit(module); }, () => { if (live) setKit(false); });
    return () => { live = false; };
  }, [wanted, kit]);
  return { kit: wanted && kit ? kit : null, pending: wanted && kit === null };
}

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";
const systemReducesMotion = () => typeof window !== "undefined" && window.matchMedia?.(REDUCED_MOTION_QUERY)?.matches === true;

/** Whether motion is reduced: the app's own setting (the host's `reducedMotion`) or the system's `prefers-reduced-motion`. */
export function useReducedMotion() {
  const app = useContext(ViewerHostContext)?.environment?.reducedMotion === true;
  const [system, setSystem] = useState(systemReducesMotion);
  useEffect(() => {
    const query = typeof window !== "undefined" ? window.matchMedia?.(REDUCED_MOTION_QUERY) : null;
    if (!query?.addEventListener) return undefined;
    const change = () => setSystem(query.matches === true);
    query.addEventListener("change", change);
    return () => query.removeEventListener("change", change);
  }, []);
  return app || system;
}

/**
 * A CAM result's state, before the shell: `cam` (the job; null for any other GLB), its playbar clips (`ownClips`) and
 * what the shell takes from it (`shellOptions`, spread over the renderer's own; null for any other GLB).
 * `requestRenderRef` is the renderer's, filled once the shell exists.
 */
export function useCamResult({ cv, scene, view, requestRenderRef }) {
  // A CAM result carries its job in the file: its verdict, setups and operations (Job), its toolpaths and its
  // simulated stock. What Display shows of it is this renderer's one slice of the file's view.
  const root = scene?.document?.scene || null;
  const cam = useMemo(() => (cv && root ? cv.readCamJob(root) : null), [cv, root]);
  const scheme = view.appearance?.colorScheme === "dark" ? "dark" : "light";
  const meshes = useMemo(() => (cam ? cv.camSceneMeshes(root) : null), [cam, root]);
  const pathKinds = useMemo(() => (cam ? cv.camPathKinds(root) : null), [cam, root]);
  const colours = useMemo(() => (cam ? cv.camOpColours(cam, scheme) : null), [cam, scheme]);
  const [stored] = useState(() => view.state);
  const [edited, setEdited] = useState(null);
  const shown = useMemo(() => (cam ? { ...cv.CAM_SHOWN, ...(readFileView(stored, { cam: CAM_SIGNATURE }).renderer.cam || {}), ...(edited || {}) } : null),
    [cam, stored, edited]);
  const shownRef = useRef(shown);
  shownRef.current = shown;
  const rendererState = useMemo(() => (cam ? { signatures: { cam: CAM_SIGNATURE }, read: () => ({ cam: shownRef.current }) } : null), [cam]);
  const shellRef = useRef(null);
  const show = useCallback((patch) => {
    setEdited((current) => ({ ...(current || {}), ...patch }));
    shellRef.current?.scheduleStateSave();
  }, []);
  // The operations put away by their eyes in Job, kept with Display's gates in the file's view.
  const hidden = useMemo(() => (cam ? cv.camHidden(cam, shown) : null), [cv, cam, shown]);
  const toggleHidden = useCallback((index) => show({ hidden: cv.toggleCamHidden(shownRef.current, index) }), [cv, show]);

  // A row of Job chosen (an operation, a setup, a tool, an error): its paths isolated, and its faces and sentence for Quick Edit.
  const [chosenRow, setChosenRow] = useState(NO_CAM_CHOICE);
  const choices = useMemo(() => (cam ? cv.camChoices(cam) : null), [cam]);
  const choice = cam && chosenRow.result === cam ? choices.get(chosenRow.id) || null : null;
  const clearChoice = useCallback(() => setChosenRow(NO_CAM_CHOICE), []);
  const chooseRow = useCallback((id) => setChosenRow((current) => (current.result === cam && current.id === id ? NO_CAM_CHOICE : { result: cam, id })), [cam]);
  const isolate = useMemo(() => (choice ? new Set(choice.ops) : null), [choice]);
  // The part the job was planned from, the file a choice's references name.
  const source = useMemo(() => (cam ? cv.camSourcePath(view.file.path, cam.document) : ""), [cam, view.file.path]);
  const references = useMemo(() => (cam ? cv.camReferences(source, choice) : null), [cam, source, choice]);

  // The toolpaths and the tool, once the viewport has drawn them (`CamPaths`); the moment a Simulate clip plays.
  const camRef = useRef(null);
  const momentRef = useRef(null);
  const paintRef = useRef(null);
  // The readout over the playbar (`CamReadout`), written as the clip plays; the playbar's speed and whether motion is reduced.
  const readoutRef = useRef(null);
  const speedRef = useRef(1);
  const reducedMotion = useReducedMotion();
  paintRef.current = () => {
    if (!cam) return;
    const moment = momentRef.current;
    const painted = cv.paintCam({ controller: camRef.current, meshes, job: cam, shown, isolate, moment });
    readoutRef.current?.(moment ? cv.camReadoutWords(cam, moment, { op: painted.place?.op ?? null, speed: speedRef.current, reducedMotion }) : null);
    if (painted.changed) requestRenderRef.current?.();
  };
  const paint = useCallback(() => paintRef.current?.(), []);
  useEffect(() => { paint(); }, [cam, shown, isolate, paint]);
  // Simulate, and one per setup, on Preview's playbar: the paths drawn up to the moment and the tool on them; with
  // motion reduced, one operation a second.
  const ownClips = useMemo(() => (cam ? cv.camClips(cam, (moment) => { momentRef.current = moment; paint(); }, { reducedMotion }) : EMPTY),
    [cam, paint, reducedMotion]);
  return {
    cv, cam, root, scheme, colours, choice, chooseRow, clearChoice, hidden, toggleHidden, references, ownClips,
    shellOptions: cam ? {
      rendererState,
      displaySections: cv.camDisplaySections({ job: cam, meshes, paths: pathKinds, shown, onChange: show }),
      // Escape lets go of the row chosen.
      escape: { active: Boolean(choice), handle: () => { if (!choice) return false; clearChoice(); return true; } },
    } : null,
    refs: { shellRef, camRef, readoutRef, speedRef }, paint,
  };
}

/**
 * A CAM result's chrome, after the shell: the RendererShell props that draw it (Select with its Job panel, the toolpaths
 * and readout over the viewport, the chosen row's references), or null for any other GLB.
 */
export function useCamChrome({ result, shell, scene, animation }) {
  const { cv, cam, root, scheme, colours, choice, chooseRow, hidden, toggleHidden, refs, paint } = result;
  refs.shellRef.current = shell;
  refs.speedRef.current = animation?.speed || 1;
  // A new playbar speed says so in the readout at once, paused or not.
  useEffect(() => { paint(); }, [animation?.speed, paint]);
  if (!cam) return null;
  // Select is a CAM result's one tool, with Job its panel.
  const selectActive = !shell.previewing && shell.toolMode === GLB_TOOL.SELECT;
  return {
    tools: [shell.tools.own({ id: GLB_TOOL.SELECT, label: "Select", icon: SELECT_ICON, panel: cv.JOB_PANEL })],
    toolPanels: <cv.CamJobPanel active={selectActive} job={cam} colours={colours} chosen={choice?.id || ""} onChoose={chooseRow}
      hidden={hidden} onToggleHidden={toggleHidden} />,
    references: result.references, onClearReferences: result.clearChoice,
    viewportOverlay: (viewport) => <>
      <cv.CamPaths runtimeRef={viewport.runtimeRef} viewerReadyTick={viewport.viewerReadyTick} root={root}
        cadRoot={scene.object3D} job={cam} scheme={scheme} controllerRef={refs.camRef} onChange={paint} />
      <cv.CamReadout readoutRef={refs.readoutRef} />
    </>,
  };
}
