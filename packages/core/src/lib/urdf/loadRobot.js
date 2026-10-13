// A robot description and every mesh it names, loaded into the once-built part list its
// scene is made from (`robotParts.js`, then `robotScene.js`). No React and no DOM beyond
// fetch: the viewer's robot renderer (`useRobotDocument`, which adds its progress, its warm
// reopen and its abort) and the snapshot CLI's headless stage both load a robot through
// these, so they read the same description, resolve the same link meshes and fail on the
// same missing one.
//
// URDF, SRDF and SDF differ only in which parser reads them. An SRDF holds planning
// semantics; what is drawn is the URDF it is paired with, with the SRDF's semantics on it.

import {
  isAbortError,
  loadRenderSdf,
  loadRenderSrdf,
  loadRenderUrdf,
  peekRenderSdf,
  peekRenderSrdf,
  peekRenderUrdf
} from "../renderAssetClient.js";
import { loadRenderMeshByUrl, peekRenderMeshByUrl } from "../render/meshLoaders.js";
import { buildRobotParts } from "./robotParts.js";

const DEFAULT_MESH_CONCURRENCY = 6;

/** Every distinct mesh a description's visuals name, already absolute (the parser resolves them). */
export function robotMeshUrls(description) {
  return [...new Set((Array.isArray(description?.links) ? description.links : [])
    .flatMap(link => (Array.isArray(link?.visuals) ? link.visuals : []))
    .map(visual => String(visual?.meshUrl || "").trim()).filter(Boolean))];
}

/**
 * @param {"urdf" | "srdf" | "sdf"} kind
 * @param {{ url: string, urdfUrl?: string, resources?: object }} source  `url` is the description
 *   itself; an SRDF also names the URDF it is paired with.
 * @returns {object | null}  The parsed description when it is already decoded, else null.
 */
export function peekRobotDescription(kind, { url, urdfUrl = "", resources } = {}) {
  if (!url) return null;
  if (kind === "srdf") return urdfUrl ? peekRenderSrdf(url, { resources, urdfUrl })?.urdfData || null : null;
  return kind === "sdf" ? peekRenderSdf(url, { resources }) : peekRenderUrdf(url, { resources });
}

/** The parsed description (an SRDF's is its URDF's, with the SRDF on it). */
export async function loadRobotDescription(kind, { url, urdfUrl = "", resources, signal } = {}) {
  if (kind === "srdf") return (await loadRenderSrdf(url, { resources, signal, urdfUrl })).urdfData;
  return kind === "sdf" ? loadRenderSdf(url, { resources, signal }) : loadRenderUrdf(url, { resources, signal });
}

/** Every link mesh already decoded, in `urls` order, or null when any one is not. */
export function peekRobotMeshes(urls, { resources } = {}) {
  const meshes = urls.map(url => peekRenderMeshByUrl(url, { resources, fallback: "stl" }));
  return meshes.every(Boolean) ? meshes : null;
}

/** The first visual that names `url`, as its description wrote it: `link “base” mesh “meshes/base.stl”`. */
function meshNamedBy(description, url) {
  for (const link of Array.isArray(description?.links) ? description.links : []) {
    for (const visual of Array.isArray(link?.visuals) ? link.visuals : []) {
      if (String(visual?.meshUrl || "").trim() === url) {
        return `Link “${link.name}” mesh “${visual.filename || url}”`;
      }
    }
  }
  return `Mesh ${url}`;
}

/** A mesh's failure, saying which link's mesh it is: the server's reason alone ("No file at …")
 * did not say which `<mesh>` to fix. Cancellation passes through as it came. */
function meshFailure(error, description, url, signal) {
  if (signal?.aborted || isAbortError(error)) return error;
  return Object.assign(new Error(`${meshNamedBy(description, url)}: ${error?.message || error}`, { cause: error }),
    { status: error?.status, url: error?.url || url, alert: error?.alert });
}

/**
 * Every link mesh, in `urls` order. A mesh that fails to load fails the robot: a robot
 * drawn without one of its links is a plausible wrong picture, in the viewer and in a
 * snapshot alike. Its error names the link and the mesh as the description wrote it.
 *
 * @param {string[]} urls  `robotMeshUrls(description)`.
 * @param {{ description?: object, resources?: object, signal?: AbortSignal, concurrency?: number, onMeshLoaded?: (done: number) => void }} [options]
 */
export async function loadRobotMeshes(urls, { description, resources, signal, concurrency = DEFAULT_MESH_CONCURRENCY, onMeshLoaded } = {}) {
  const meshes = new Array(urls.length);
  let next = 0;
  let done = 0;
  await Promise.all(Array.from({ length: Math.min(Math.max(1, concurrency), urls.length) }, async () => {
    while (next < urls.length) {
      const index = next;
      next += 1;
      signal?.throwIfAborted();
      try {
        meshes[index] = await loadRenderMeshByUrl(urls[index], { signal, resources, fallback: "stl" });
      } catch (error) {
        throw meshFailure(error, description, urls[index], signal);
      }
      done += 1;
      onMeshLoaded?.(done);
    }
  }));
  return meshes;
}

/**
 * The robot a scene is built from: the description and its part list (`buildRobotParts`).
 *
 * @param {object} description  `loadRobotDescription`.
 * @param {string[]} urls  `robotMeshUrls(description)`.
 * @param {object[]} meshes  `loadRobotMeshes(urls)` or `peekRobotMeshes(urls)`.
 * @returns {{ description: object, parts: object[], components: object[] }}
 */
export function robotModel(description, urls, meshes) {
  return { description, ...buildRobotParts(description, new Map(urls.map((url, index) => [url, meshes[index]]))) };
}

/**
 * Load a robot whole: its description, then every link mesh it names.
 *
 * @param {"urdf" | "srdf" | "sdf"} kind
 * @param {{ url: string, urdfUrl?: string, resources?: object, signal?: AbortSignal, concurrency?: number }} source
 */
export async function loadRobot(kind, { url, urdfUrl = "", resources, signal, concurrency } = {}) {
  const description = await loadRobotDescription(kind, { url, urdfUrl, resources, signal });
  if (!description) throw new Error(`Robot description did not parse: ${url}`);
  const urls = robotMeshUrls(description);
  return robotModel(description, urls, await loadRobotMeshes(urls, { description, resources, signal, concurrency }));
}
