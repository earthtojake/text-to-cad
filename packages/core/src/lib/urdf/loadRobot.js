// A robot as cadgen resolved it (`cadgen.robot_payload`: the articulation to play and the
// visuals to draw) and every mesh those visuals name, loaded into the once-built part list
// its scene is made from (`robotParts.js`, then `robotScene.js`). No React and no DOM
// beyond fetch: the viewer's robot renderer (`useRobotDocument`, which adds its progress,
// its warm reopen and its abort) and the snapshot CLI's headless stage both load a robot
// through these, so they draw the same payload, fetch the same meshes and fail on the
// same missing one. The page reads no description: URDF, SRDF and SDF are one payload.

import { loadRenderMeshByUrl, peekRenderMeshByUrl } from "../render/meshLoaders.js";
import { buildRobotParts } from "./robotParts.js";

const DEFAULT_MESH_CONCURRENCY = 6;

/** Every distinct mesh URL the payload's visuals name, with the decoder the payload says each takes. */
export function robotMeshUrls(robot) {
  const formats = new Map();
  for (const visual of Array.isArray(robot?.visuals) ? robot.visuals : []) {
    const url = String(visual?.mesh?.url || "").trim();
    if (url && !formats.has(url)) formats.set(url, String(visual?.mesh?.format || "glb").trim().toLowerCase());
  }
  return formats;
}

/** Every mesh already decoded, in `urls` order, or null when any one is not. */
export function peekRobotMeshes(urls, { resources } = {}) {
  const meshes = [...urls].map(([url, format]) => peekRenderMeshByUrl(url, { resources, fallback: format }));
  return meshes.every(Boolean) ? meshes : null;
}

/**
 * Every mesh, in `urls` order. A mesh that fails to load fails the robot: a robot drawn
 * without one of its links is a plausible wrong picture, in the viewer and in a snapshot alike.
 *
 * @param {Map<string, string>} urls  `robotMeshUrls(robot)`.
 * @param {{ resources?: object, signal?: AbortSignal, concurrency?: number, onMeshLoaded?: (done: number) => void }} [options]
 */
export async function loadRobotMeshes(urls, { resources, signal, concurrency = DEFAULT_MESH_CONCURRENCY, onMeshLoaded } = {}) {
  const entries = [...urls];
  const meshes = new Array(entries.length);
  let next = 0;
  let done = 0;
  await Promise.all(Array.from({ length: Math.min(Math.max(1, concurrency), entries.length) }, async () => {
    while (next < entries.length) {
      const index = next;
      next += 1;
      signal?.throwIfAborted();
      const [url, format] = entries[index];
      meshes[index] = await loadRenderMeshByUrl(url, { signal, resources, fallback: format });
      done += 1;
      onMeshLoaded?.(done);
    }
  }));
  return meshes;
}

/**
 * The robot a scene is built from: the payload and its part list (`buildRobotParts`).
 *
 * @param {object} robot  The payload.
 * @param {Map<string, string>} urls  `robotMeshUrls(robot)`.
 * @param {object[]} meshes  `loadRobotMeshes(urls)` or `peekRobotMeshes(urls)`.
 * @returns {{ robot: object, parts: object[], components: object[] }}
 */
export function robotModel(robot, urls, meshes) {
  return { robot, ...buildRobotParts(robot, new Map([...urls.keys()].map((url, index) => [url, meshes[index]]))) };
}

/**
 * Load a robot whole from the payload a host handed over: every mesh its visuals name.
 *
 * @param {{ robot: object, resources?: object, signal?: AbortSignal, concurrency?: number }} source
 */
export async function loadRobot({ robot, resources, signal, concurrency } = {}) {
  if (!robot || typeof robot !== "object" || !robot.articulation) {
    throw new Error("a robot is drawn from the payload cadgen resolved (resolved.robot): none was given");
  }
  const urls = robotMeshUrls(robot);
  return robotModel(robot, urls, await loadRobotMeshes(urls, { resources, signal, concurrency }));
}
