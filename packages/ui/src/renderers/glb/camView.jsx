/**
 * The CAM result viewer GlbRenderer loads only for a GLB that carries a job (`cadgen cam plan`): one module,
 * so the bundler makes it a chunk of its own and a plain GLB never fetches it. Everything GlbRenderer uses of
 * the CAM viewer is here, by name.
 */
import { useLayoutEffect, useRef } from "react";
import * as THREE from "three";
import { formatPromptReference } from "@text-to-cad/core/prompt";
import { cn } from "@text-to-cad/ui/utils";
import { FLOATING_CHROME_SURFACE_CLASS } from "../../lib/floatingSurface.js";
import { english } from "../../i18n/core.js";
import { useI18n } from "@text-to-cad/ui/i18n";
import { InfoRow } from "../kit/inspector/referenceRows.jsx";
import { camToolpathObjects, createCamPaths } from "./cam/lines.js";
import { camSceneMeshes, showCamMeshes } from "./cam/playback.js";
import { createCamTool } from "./cam/tool.js";

export { default as CamJobPanel } from "./CamJobPanel.jsx";
export { camChoices } from "./CamJobPanel.jsx";
export { CamResultError, camSourcePath, readCamJob } from "./cam/extras.js";
export { camOpColours } from "./cam/colours.js";
export { camClips, camReadoutWords } from "./cam/playback.js";
export { camSceneMeshes, showCamMeshes };

/**
 * What the view shows of a result, before the person chooses (Job's Show rows): the paths, the tool riding them and
 * the part; the stock box is a choice. `hidden` is the operations put away by their eyes in Job (their indices).
 */
export const CAM_SHOWN = Object.freeze({ toolpaths: true, rapids: true, tool: true, stock: false, part: true, hidden: Object.freeze([]) });

/** The operations put away (`shown.hidden`), as a set of the job's indices; null for none. */
export function camHidden(job, shown) {
  const indices = new Set(job.operations.map((op) => op.index));
  const hidden = (Array.isArray(shown?.hidden) ? shown.hidden : []).filter((index) => indices.has(index));
  return hidden.length ? new Set(hidden) : null;
}

/** `shown.hidden` with one operation's eye turned: put away, or back. */
export function toggleCamHidden(shown, index) {
  const hidden = new Set(Array.isArray(shown?.hidden) ? shown.hidden : []);
  if (!hidden.delete(index)) hidden.add(index);
  return [...hidden].sort((a, b) => a - b);
}

/**
 * Job's Show rows: a gate each for what the file draws beyond a plain GLB's surfaces — its toolpaths, its rapids,
 * the tool, the stock box, the finished part — offered where the file has it, with the
 * words its hint says. `shown` is what is on (`on`); Job's eye turns one, as `{ [id]: on }` patched into `shown`.
 */
export function camGates({ meshes, paths, shown, t = english }) {
  const gates = [];
  const gate = (id) => gates.push({ id, title: t(`cam.gate.${id}`), hint: t(`cam.gate.${id}Hint`), on: shown[id] !== false });
  if (paths.feed) gate("toolpaths");
  if (paths.rapid) gate("rapids");
  if (paths.feed || paths.rapid) gate("tool");
  if (meshes.stock.length) gate("stock");
  if (meshes.part.length) gate("part");
  return gates;
}

/** Which kinds of path the file has: its lines, by kind. */
export function camPathKinds(root) {
  const kinds = { feed: false, rapid: false };
  for (const { kind } of camToolpathObjects(root)) kinds[kind] = true;
  return kinds;
}

/**
 * What Quick Edit gets for a choice: the part the job was planned from (`source`), the choice's faces as a
 * cad selector or, with none, the whole file, and the choice's sentence as its `summary`.
 */
export function camReferences(source, choice) {
  if (!source || !choice) return [];
  const faces = choice.faces;
  const target = faces.length ? { kind: "cad-selector", selectors: faces } : { kind: "whole-resource" };
  return [{ resource: { kind: "workspace-file", path: source }, target, ...(choice.summary ? { summary: choice.summary } : {}) }];
}

const fileName = (path) => String(path || "").split(/[\\/]/).filter(Boolean).at(-1) || String(path || "");

/** A choice's card in Quick Edit: its sentence, then the part it names and how many of its faces. */
function CamChoiceCard({ choice, reference }) {
  const { t } = useI18n();
  const faces = reference.target.kind === "cad-selector" ? reference.target.selectors.length : 0;
  return <>
    {choice.summary ? <p className="py-0.5 text-tiny text-muted-foreground [overflow-wrap:break-word]" data-cam-chip-summary="">{choice.summary}</p> : null}
    <InfoRow label={t("cam.gate.part")} copy={reference.resource.path}>{fileName(reference.resource.path)}</InfoRow>
    <InfoRow label={t("cam.faces")}>{faces ? faces.toLocaleString("en-US") : t("cam.wholePart")}</InfoRow>
  </>;
}

/**
 * What Quick Edit shows of a choice (`camReferences`' one reference): one chip named for its row ("Pocket",
 * "Top setup", "T1 6 mm flat", an error's words), a face's glyph where it names faces (in the operation's colour, for
 * an operation's), else the whole part's, its card the row's sentence. A click copies the reference; its X lets go of
 * the choice (`onRemove`). None without a reference.
 */
export function camChips(choice, references, { colours = {}, onRemove, t = english } = {}) {
  const reference = references?.[0];
  if (!choice || !reference) return [];
  const op = choice.ops.length === 1 && choice.id.startsWith("op:") ? choice.ops[0] : null;
  return [{
    key: `cam:${choice.id}`, label: choice.label || choice.summary || t("cam.job"), glyph: reference.target.kind === "cad-selector" ? "face" : "solid",
    ...(op !== null && colours[op] ? { glyphColor: colours[op] } : {}),
    copy: formatPromptReference(reference), card: <CamChoiceCard choice={choice} reference={reference} />, onRemove,
  }];
}

/**
 * The group the CAM drawing hangs from: in the viewport's model group, beside the GLB's own object rather than in it,
 * placed where the file's scene root is. What is drawn in the root's frame is then drawn where it was, yet is no part
 * of the scene: Preview's copy of the scene, Select's picks, Explode and Clip's caps never meet it.
 */
function camHolder(runtime, root, cadRoot) {
  const holder = new THREE.Group();
  holder.name = "cam-drawing";
  holder.userData.camDrawn = true;
  holder.matrixAutoUpdate = false;
  // The root's place under the object the model group adopts (`cadRoot`), then that object's own.
  const place = new THREE.Matrix4();
  for (let node = root; node && node !== cadRoot; node = node.parent) {
    if (node.matrixAutoUpdate) node.updateMatrix();
    place.premultiply(node.matrix);
  }
  if (cadRoot && cadRoot !== root) {
    if (cadRoot.matrixAutoUpdate) cadRoot.updateMatrix();
    place.premultiply(cadRoot.matrix);
  }
  holder.matrix.copy(place);
  (runtime.modelGroup || cadRoot?.parent || root).add(holder);
  return holder;
}

/**
 * The toolpaths and the riding tool, drawn into the viewport once its runtime is up (`createCamPaths`,
 * which needs its screen-space lines) and put away with the result. `controllerRef` holds `{ paths, tool }`
 * while they are up; `onChange` is told when they come and go, to draw what is shown.
 */
export function CamPaths({ runtimeRef, viewerReadyTick, root, cadRoot, job, scheme, controllerRef, onChange }) {
  useLayoutEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime || !root || !job) return undefined;
    const pixelRatio = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
    const holder = camHolder(runtime, root, cadRoot);
    const paths = createCamPaths(runtime.THREE || THREE, root, job, { context: runtime, cadRoot, scheme, pixelRatio, parent: holder });
    if (!paths) { holder.removeFromParent(); return undefined; }
    const tool = createCamTool(runtime.THREE || THREE, holder, job, paths.frame);
    controllerRef.current = { paths, tool };
    onChange?.();
    return () => {
      controllerRef.current = null;
      tool.dispose();
      paths.dispose();
      holder.removeFromParent();
      onChange?.();
    };
    // The scheme is restyled in place (below), never rebuilt.
  }, [runtimeRef, viewerReadyTick, root, cadRoot, job]); // eslint-disable-line react-hooks/exhaustive-deps
  useLayoutEffect(() => {
    const controller = controllerRef.current;
    if (!controller) return;
    controller.paths.style(scheme);
    onChange?.();
  }, [scheme]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

const TOOL_LEAD_S = 1e-6;

/**
 * Draws what is shown, in one pass: the paths (on or off, isolated, the hidden ones put away, revealed up to the
 * moment playing), the tool at that moment, and the part and stock as Job's Show rows say. Returns whether anything changed, and `place`, where the tool is at the moment.
 */
export function paintCam({ controller, meshes, job, shown, isolate, moment }) {
  let changed = showCamMeshes(meshes, { part: shown.part !== false, stock: shown.stock !== false });
  if (!controller) return { changed, place: null };
  const { paths, tool } = controller;
  if (paths.update({ toolpaths: shown.toolpaths !== false, rapids: shown.rapids !== false, isolate, hidden: camHidden(job, shown),
    time: moment ? moment.t : null, setup: moment?.setup || null })) changed = true;
  // The tool as it reaches the moment: at an operation's last moment it is at that operation's end, not at the start
  // of the next (which begins at the same time), so a step-by-step playback leaves it on what it just cut.
  const place = moment ? paths.toolAt(Math.max(moment.t - TOOL_LEAD_S, 0), moment.setup || null) : null;
  if (moment && shown.tool !== false) {
    tool.show(place);
    return { changed: true, place };
  }
  tool.hide();
  return { changed: changed || Boolean(moment), place };
}

// A clip plays from the file sidebar's Animation section: the readout sits at the view's bottom centre, clear of
// Quick Edit's sheet on a phone (`--cad-quick-edit-peek`).
const READOUT_BOTTOM = "calc(var(--cad-quick-edit-peek, 0px) + 1rem)";

/**
 * Where a playing clip is, at the view's bottom centre: the operation under way, the program's time over its whole
 * ("1:32 / 3:38") and how fast it plays ("12× speed"). There only while a clip plays (`write(words)`; null puts it
 * away). The playback writes it every frame through `readoutRef.current(words)`, never through React; it takes no
 * pointer, and is not read out as it changes (the Animation section has the time).
 */
export function CamReadout({ readoutRef }) {
  const boxRef = useRef(null);
  const operationRef = useRef(null);
  const timeRef = useRef(null);
  const speedRef = useRef(null);
  useLayoutEffect(() => {
    const set = (element, value) => { if (element && element.textContent !== value) element.textContent = value; };
    const write = (words) => {
      if (!boxRef.current) return;
      boxRef.current.style.display = words ? "" : "none";
      if (!words) return;
      set(operationRef.current, words.operation);
      set(timeRef.current, words.time);
      set(speedRef.current, words.speed || "");
    };
    readoutRef.current = write;
    return () => { if (readoutRef.current === write) readoutRef.current = null; };
  }, [readoutRef]);
  // Put away until a clip writes to it: React never draws it shown, so a render never undoes what the playback wrote.
  return <div ref={boxRef} className="pointer-events-none absolute inset-x-0 z-20 flex justify-center px-3" aria-hidden="true" data-cam-readout=""
    style={{ bottom: READOUT_BOTTOM, display: "none" }}>
    <div className={cn("flex max-w-full items-center gap-2 rounded-md px-2.5 py-1 text-micro tabular-nums text-muted-foreground", FLOATING_CHROME_SURFACE_CLASS)}>
      <span ref={operationRef} className="min-w-0 truncate text-tiny text-foreground" data-cam-readout-operation="" />
      <span ref={timeRef} className="shrink-0" data-cam-readout-time="" />
      <span ref={speedRef} className="shrink-0" data-cam-readout-speed="" />
    </div>
  </div>;
}
