import { useEffect, useRef, useState } from "react";
import { entryAssetUrl, entryUrdfAssetHash } from "@hardcore/core/lib/entryAssets.js";
import {
  isAbortError, loadRenderSdf, loadRenderSrdf, loadRenderText, loadRenderUrdf, peekRenderSdf, peekRenderSrdf, peekRenderUrdf
} from "@hardcore/core/lib/renderAssetClient.js";
import { loadRenderMeshByUrl, peekRenderMeshByUrl } from "@hardcore/core/lib/render/meshLoaders.js";
import { buildRobotParts } from "./robotParts.js";

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

/** Every distinct mesh a description's visuals name. */
export function robotMeshUrls(description) {
  return [...new Set((Array.isArray(description?.links) ? description.links : [])
    .flatMap(link => (Array.isArray(link?.visuals) ? link.visuals : []))
    .map(visual => String(visual?.meshUrl || "").trim()).filter(Boolean))];
}

function descriptionUrls(entry) {
  const kind = kindOf(entry);
  return { kind, primary: entryAssetUrl(entry, kind === "sdf" ? "sdf" : kind === "srdf" ? "srdf" : "urdf"), urdf: entryAssetUrl(entry, "urdf") };
}

function peekDescription(entry, resources) {
  const { kind, primary, urdf } = descriptionUrls(entry);
  if (!primary) return null;
  if (kind === "srdf") return urdf ? peekRenderSrdf(primary, { resources, urdfUrl: urdf })?.urdfData || null : null;
  return kind === "sdf" ? peekRenderSdf(primary, { resources }) : peekRenderUrdf(primary, { resources });
}

async function loadDescription(entry, { resources, signal }) {
  const { kind, primary, urdf } = descriptionUrls(entry);
  if (kind === "srdf") return (await loadRenderSrdf(primary, { resources, signal, urdfUrl: urdf })).urdfData;
  return kind === "sdf" ? loadRenderSdf(primary, { resources, signal }) : loadRenderUrdf(primary, { resources, signal });
}

// An SRDF holds planning semantics only; what is drawn is the URDF it is about, which the
// catalog pairs with it: the ONE `.urdf` in the same folder whose `<robot name>` matches.
// No match (or two) is not something to wait for, so it is said, with what was looked for.
async function unpairedSrdfError(entry, { resources, signal }) {
  let robotName = "";
  try {
    const text = await loadRenderText(entryAssetUrl(entry, "srdf"), { resources, signal });
    robotName = /<robot\b[^>]*?\bname\s*=\s*(?:"([^"]*)"|'([^']*)')/.exec(text)?.slice(1).find(Boolean)?.trim() || "";
  } catch (error) {
    if (isAbortError(error) || signal.aborted) throw error;
  }
  const file = String(entry?.file || "");
  const folder = file.includes("/") ? `“${file.slice(0, file.lastIndexOf("/"))}”` : "the folder this SRDF is in";
  const wanted = robotName ? `whose <robot name> is “${robotName}”` : "with the same <robot name> (this SRDF's <robot> element has no name to match)";
  const error = new Error(`No URDF is paired with ${file || "this SRDF"}: looked in ${folder} for exactly one .urdf file ${wanted}.`);
  // The alert a person reads; the message above is its Details.
  error.alert = {
    summary: "URDF not found",
    title: "No URDF beside this SRDF",
    message: `An SRDF says how a robot is planned, not what it looks like, so the viewer draws the URDF it belongs to. It looked in ${folder} for exactly one .urdf file ${wanted}, and found none, or more than one.`,
    recovery: "Put the robot's URDF next to this SRDF, or make the two <robot name> attributes match, then reload."
  };
  return error;
}

async function mapWithConcurrency(items, limit, run) {
  const results = new Array(items.length);
  let next = 0;
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) {
      const index = next;
      next += 1;
      results[index] = await run(items[index], index);
    }
  }));
  return results;
}

function robotOf(entry, description, meshes, urls) {
  const { parts, components } = buildRobotParts(description, new Map(urls.map((url, index) => [url, meshes[index]])));
  return { file: String(entry?.file || ""), kind: kindOf(entry), revision: entryUrdfAssetHash(entry), description, parts, components };
}

// A warm file (its description and every link mesh still decoded) is whole at once.
function peekRobot(entry, resources) {
  if (!KINDS.has(kindOf(entry))) return null;
  const description = peekDescription(entry, resources);
  if (!description) return null;
  const urls = robotMeshUrls(description);
  const meshes = urls.map(url => peekRenderMeshByUrl(url, { resources, fallback: "stl" }));
  return meshes.every(Boolean) ? robotOf(entry, description, meshes, urls) : null;
}

/**
 * A robot description and every mesh it names, as the once-built part list a scene is
 * made from. URDF, SRDF (its paired URDF, with the SRDF's semantics on it) and SDF differ
 * only in which core loader reads them. The robot is published ONCE, complete: a
 * half-drawn robot with the loading card gone reads as a broken model, so the counted
 * stage is the progress signal instead. A missing link mesh fails the load. A warm file
 * is there on the first render; a new revision loads behind the robot on screen.
 *
 * @returns {{ robot: { file: string, kind: string, revision: string, description: object, parts: object[],
 *   components: object[] } | null, busy: boolean, progress: object | null, error: unknown }}
 */
export function useRobotDocument({ entry, resources }) {
  const kind = kindOf(entry);
  const revision = entryUrdfAssetHash(entry);
  const { primary, urdf } = descriptionUrls(entry);
  const pending = entry?.catalogPending === true;
  const label = `Loading ${kind.toUpperCase()}`;
  const [state, setState] = useState(() => {
    const robot = pending ? null : peekRobot(entry, resources);
    return { robot, busy: !robot, progress: robot ? null : { phase: "read", label, determinate: false }, error: null };
  });
  const resourcesRef = useRef(resources);
  resourcesRef.current = resources;
  const entryRef = useRef(entry);
  entryRef.current = entry;
  const loadedRef = useRef(state.robot?.revision ?? null);

  useEffect(() => {
    if (pending || loadedRef.current === revision) return undefined;
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
      if (kind === "srdf" && !urdf) throw await unpairedSrdfError(current, { resources: resourcesRef.current, signal });
      if (!primary) throw new Error(`${kind.toUpperCase()} entry is missing its ${kind.toUpperCase()} asset: ${current?.file || "(unknown)"}`);
      const description = await loadDescription(current, { resources: resourcesRef.current, signal });
      const urls = robotMeshUrls(description);
      let done = 0;
      if (urls.length) publish({ progress: { phase: "meshes", label: "Loading meshes", done, total: urls.length, determinate: true } });
      const meshes = await mapWithConcurrency(urls, meshConcurrency(), async (url) => {
        signal.throwIfAborted();
        const mesh = await loadRenderMeshByUrl(url, { signal, resources: resourcesRef.current, fallback: "stl" });
        done += 1;
        publish({ progress: { phase: "meshes", label: "Loading meshes", done, total: urls.length, determinate: true } });
        return mesh;
      });
      signal.throwIfAborted();
      publish({ progress: { phase: "view", label: "Building robot", determinate: false } });
      return robotOf(current, description, meshes, urls);
    })().then((robot) => {
      if (signal.aborted) return;
      loadedRef.current = revision;
      setState({ robot, busy: false, progress: null, error: null });
    }, fail);
    return () => controller.abort();
  }, [kind, primary, urdf, revision, pending, label]);
  return state;
}
