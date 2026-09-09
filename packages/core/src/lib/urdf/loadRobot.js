// Assemble a robot into ordinary mesh data, with no UI attached.
//
// This is the step that lets a robot render ANYWHERE the mesh path runs. The viewer had
// it, spread across a React hook (fetch the description, fetch every link mesh, build the
// geometry, pose it) — which is why headless renders had no robot support at all: the
// assembly only existed inside a component. Nothing here touches React or the DOM beyond
// fetch, so the snapshot runtime uses the same code the viewer does.
//
// The viewer keeps its own loader: it publishes links progressively and handles aborts on
// selection changes, neither of which a one-shot headless render wants.

import {
  loadRenderSdf,
  loadRenderSrdf,
  loadRenderUrdf
} from "../renderAssetClient.js";
import { loadRenderMeshByUrl } from "../render/meshLoaders.js";
import {
  applyUrdfPoseToMeshData,
  buildDefaultUrdfJointValues,
  buildUrdfMeshGeometry
} from "./kinematics.js";

export const ROBOT_SOURCE_KINDS = Object.freeze(["urdf", "srdf", "sdf"]);

export function isRobotSourceKind(kind) {
  return ROBOT_SOURCE_KINDS.includes(String(kind || "").trim().toLowerCase());
}

export function robotSourceKindFromUrl(url = "") {
  const pathname = String(url || "").split(/[?#]/, 1)[0].toLowerCase();
  return ROBOT_SOURCE_KINDS.find((kind) => pathname.endsWith(`.${kind}`)) || "";
}

// Every distinct mesh a robot's visuals reference. Already absolute: the parser resolves
// each `filename` against the description's own URL, so a headless caller needs to know
// nothing about where the link meshes live.
export function urdfMeshUrls(urdfData) {
  return [...new Set(
    (Array.isArray(urdfData?.links) ? urdfData.links : [])
      .flatMap((link) => (Array.isArray(link?.visuals) ? link.visuals : []))
      .map((visual) => String(visual?.meshUrl || "").trim())
      .filter(Boolean)
  )];
}

async function loadRobotDescription(url, kind, { signal, urdfUrl = "" } = {}) {
  const normalizedKind = String(kind || "").trim().toLowerCase() || robotSourceKindFromUrl(url);
  if (normalizedKind === "srdf") {
    // An SRDF describes semantics for a URDF; the geometry still comes from the pair.
    const payload = await loadRenderSrdf(url, { signal, urdfUrl });
    return payload?.urdfData || null;
  }
  if (normalizedKind === "sdf") {
    return loadRenderSdf(url, { signal });
  }
  return loadRenderUrdf(url, { signal });
}

async function loadMeshesByUrl(meshUrls, { signal, concurrency = 6 } = {}) {
  const meshesByUrl = new Map();
  const queue = [...meshUrls];
  const workers = Array.from({ length: Math.max(1, Math.min(concurrency, queue.length)) }, async () => {
    for (;;) {
      const meshUrl = queue.shift();
      if (!meshUrl) {
        return;
      }
      // A link whose mesh will not load is skipped rather than fatal: a robot missing one
      // visual should still render, the same way the viewer draws what it has.
      try {
        const mesh = await loadRenderMeshByUrl(meshUrl, { signal, fallback: "stl" });
        if (mesh) {
          meshesByUrl.set(meshUrl, mesh);
        }
      } catch {
        // fall through
      }
    }
  });
  await Promise.all(workers);
  return meshesByUrl;
}

// Assemble a robot at a pose. `jointValues` is the robot's analogue of a STEP parameter
// sidecar's values — omit it for the rest pose.
export async function loadRobotMeshData(url, {
  kind = "",
  jointValues = null,
  urdfUrl = "",
  signal = null,
  concurrency = 6
} = {}) {
  const sourceUrl = String(url || "").trim();
  if (!sourceUrl) {
    throw new Error("loadRobotMeshData requires a robot description URL");
  }
  const urdfData = await loadRobotDescription(sourceUrl, kind, { signal, urdfUrl });
  if (!urdfData) {
    throw new Error(`Robot description did not parse: ${sourceUrl}`);
  }
  const meshUrls = urdfMeshUrls(urdfData);
  const meshesByUrl = await loadMeshesByUrl(meshUrls, { signal, concurrency });
  if (!meshesByUrl.size && meshUrls.length) {
    throw new Error(`No link mesh loaded for robot: ${sourceUrl}`);
  }
  const meshData = buildUrdfMeshGeometry(urdfData, meshesByUrl, { lightweight: true });
  const posed = applyUrdfPoseToMeshData(
    urdfData,
    meshData,
    resolveJointValues(urdfData, jointValues)
  );
  return {
    urdfData,
    meshData: posed?.meshData || meshData,
    linkWorldTransforms: posed?.linkWorldTransforms || new Map()
  };
}

// Named joints override the rest pose; anything unnamed keeps its default, so a caller can
// pose one joint without restating the robot.
export function resolveJointValues(urdfData, jointValues) {
  const defaults = buildDefaultUrdfJointValues(urdfData);
  if (!jointValues || typeof jointValues !== "object" || Array.isArray(jointValues)) {
    return defaults;
  }
  const resolved = { ...defaults };
  for (const [name, value] of Object.entries(jointValues)) {
    const jointName = String(name || "").trim();
    const numericValue = Number(value);
    if (jointName && Number.isFinite(numericValue)) {
      resolved[jointName] = numericValue;
    }
  }
  return resolved;
}
