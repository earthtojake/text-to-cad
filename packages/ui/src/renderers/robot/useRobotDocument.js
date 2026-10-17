import { useEffect, useRef, useState } from "react";
import { entryUrdfAssetHash } from "@text-to-cad/core/lib/entryAssets.js";
import { isAbortError, loadRenderRobot, peekRenderRobot } from "@text-to-cad/core/lib/renderAssetClient.js";
import { loadRobotMeshes, peekRobotMeshes, robotMeshUrls, robotModel } from "@text-to-cad/core/lib/urdf/loadRobot.js";

// Link meshes are fetched and parsed off the main thread where a worker exists, so the
// cap only bounds sockets and the worker's queue; it is tied to cores because the
// worker still parses serially.
const MESH_LOAD_CONCURRENCY = 8;
const KINDS = new Set(["urdf", "srdf", "sdf"]);
const kindOf = entry => String(entry?.kind || "").trim().toLowerCase();

function meshConcurrency() {
  const cores = typeof navigator !== "undefined" ? Number(navigator.hardwareConcurrency) : 0;
  return Number.isFinite(cores) && cores > 0 ? Math.max(2, Math.min(MESH_LOAD_CONCURRENCY, cores)) : MESH_LOAD_CONCURRENCY;
}

// An SRDF holds planning semantics only; what is drawn is the URDF it is about, which
// cadgen pairs with it: the ONE `.urdf` in the same folder whose `<robot name>` matches.
// cadgen's refusal says what it looked for; this is the alert a person reads around it.
function unpairedSrdfAlert(entry, error) {
  const file = String(entry?.file || "");
  const folder = file.includes("/") ? `“${file.slice(0, file.lastIndexOf("/"))}”` : "the folder this SRDF is in";
  const alert = {
    summary: "URDF not found",
    title: "No URDF beside this SRDF",
    message: `An SRDF says how a robot is planned, not what it looks like, so the viewer draws the URDF it belongs to. It looked in ${folder} for exactly one .urdf file with the same <robot name>, and found none, or more than one. ${String(error?.message || "")}`.trim(),
    recovery: "Put the robot's URDF next to this SRDF, or make the two <robot name> attributes match, then reload."
  };
  return Object.assign(new Error(`No URDF is paired with ${file || "this SRDF"}: ${String(error?.message || "")}`.trim(), { cause: error }), { alert });
}

const UNPAIRED_SRDF = /has no paired URDF|is ambiguous: \d+ \.urdf files|has no readable <robot name>/;

function robotOf(entry, robot, urls, meshes) {
  return { file: String(entry?.file || ""), kind: kindOf(entry), revision: entryUrdfAssetHash(entry), ...robotModel(robot, urls, meshes) };
}

// A warm file (its payload and every mesh still decoded) is whole at once.
function peekRobot(entry, resources) {
  if (!KINDS.has(kindOf(entry))) return null;
  const robot = peekRenderRobot(String(entry?.file || ""), { revision: entryUrdfAssetHash(entry) });
  if (!robot) return null;
  const urls = robotMeshUrls(robot);
  const meshes = peekRobotMeshes(urls, { resources });
  return meshes ? robotOf(entry, robot, urls, meshes) : null;
}

/**
 * A robot as cadgen resolved it (`GET /__cad/robot`: the articulation to play, the visuals
 * to draw and the facts a person reads back) and every mesh its visuals name, as the
 * once-built part list a scene is made from. URDF, SRDF (its paired URDF, with the SRDF's
 * semantics on it) and SDF are one payload: nothing here asks which it was. The robot is
 * published ONCE, complete: a half-drawn robot with the loading card gone reads as a broken
 * model, so the counted stage is the progress signal instead. A missing mesh fails the
 * load. A warm file is there on the first render; a new revision loads behind the robot
 * on screen.
 *
 * @returns {{ robot: { file: string, kind: string, revision: string, robot: object, parts: object[],
 *   components: object[] } | null, busy: boolean, progress: object | null, error: unknown }}
 */
export function useRobotDocument({ entry, client, resources }) {
  const kind = kindOf(entry);
  const file = String(entry?.file || "");
  const revision = entryUrdfAssetHash(entry);
  const label = `Loading ${kind.toUpperCase()}`;
  const [state, setState] = useState(() => {
    const robot = peekRobot(entry, resources);
    return { robot, busy: !robot, progress: robot ? null : { phase: "read", label, determinate: false }, error: null };
  });
  const resourcesRef = useRef(resources);
  resourcesRef.current = resources;
  const clientRef = useRef(client);
  clientRef.current = client;
  const entryRef = useRef(entry);
  entryRef.current = entry;
  const loadedRef = useRef(state.robot?.revision ?? null);

  useEffect(() => {
    if (loadedRef.current === revision) return undefined;
    const current = entryRef.current;
    const controller = new AbortController();
    const { signal } = controller;
    const publish = (next) => { if (!signal.aborted) setState(previous => ({ ...previous, ...next })); };
    const fail = (error) => {
      if (signal.aborted || isAbortError(error)) return;
      loadedRef.current = null;
      publish({ busy: false, progress: null, error });
    };
    publish({ busy: true, progress: { phase: "read", label, determinate: false }, error: null });
    (async () => {
      const warm = peekRobot(current, resourcesRef.current);
      if (warm) return warm;
      if (!KINDS.has(kind) || !file) throw new Error(`${kind.toUpperCase() || "robot"} entry has no file to resolve: ${current?.file || "(unknown)"}`);
      let robot;
      try {
        robot = await loadRenderRobot(file, { client: clientRef.current, revision, signal });
      } catch (error) {
        if (kind === "srdf" && UNPAIRED_SRDF.test(String(error?.message || ""))) throw unpairedSrdfAlert(current, error);
        // cadgen refuses a description at the door with a sentence about the FILE (a 400: a
        // validator's finding, a mesh the page cannot draw): that sentence is the diagnosis a
        // person reads, as a mesh that would not load is, not a request that failed.
        if (error?.failure?.kind === "http" && error.failure.status === 400) throw Object.assign(new Error(String(error.message || "")), { cause: error });
        throw error;
      }
      const urls = robotMeshUrls(robot);
      const counted = done => ({ progress: { phase: "meshes", label: "Loading meshes", done, total: urls.size, determinate: true } });
      if (urls.size) publish(counted(0));
      const meshes = await loadRobotMeshes(urls, { resources: resourcesRef.current, signal, concurrency: meshConcurrency(),
        onMeshLoaded: done => publish(counted(done)) });
      signal.throwIfAborted();
      publish({ progress: { phase: "view", label: "Building robot", determinate: false } });
      return robotOf(current, robot, urls, meshes);
    })().then((robot) => {
      if (signal.aborted) return;
      loadedRef.current = revision;
      setState({ robot, busy: false, progress: null, error: null });
    }, fail);
    return () => controller.abort();
  }, [kind, file, revision, label]);
  return state;
}
