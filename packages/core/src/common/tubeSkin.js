import { buildCadEdgeLines } from "../lib/surf/surfMeshData.js";
import { MESH_TABLE_COLUMNS } from "../lib/surf/tessellationCache.js";
import { applyTubeBraidMaterial } from "./tubeBraidMaterial.js";
import {
  TUBE_MATERIAL_ATTRIBUTE,
  TUBE_SKIN_STAGE,
  ensureTubeMaterialStage,
  tubeMaterialStage
} from "./tubeMaterialShader.js";

// A bending tube, played. cadgen works out where a tube is
// (cadgen/_internal/tube_skin_payload.py): every tube a clip bends arrives refined
// and bound in its component's frame -- each vertex and each edge point carrying
// its JOINT COORDINATE, the joint below it plus its weight toward the next -- and
// every key of the tube's track arrives as its joints, an origin and a unit
// quaternion each, in the document's space. This module only blends: the joints of
// two keys the way glTF's LINEAR sampler does (lerp, slerp the short way), then
// each vertex between its two joints, which is skinning. It works out no path.
//
// A record whose clip bends it swaps its component geometry for the binding's and
// keeps the component's for rest (`tubeSkinState.original`). Joint j moves a
// component-local point by base^-1 . key_j . rest_j^-1 . base, `base` being the
// record's own placement, so the record's effect and exploded matrices compose
// over the bend exactly as they compose over a rigid part. The GPU draws the
// skin from rest attributes and a joint texture; the CPU poses the same points
// for a pick, for a host without the GPU stage, and for the record's edges.

/** What a frame's tube pose carries, per record (`applyRecordTubeSkin`). */
const JOINT_VALUES = 7;
const MATRIX_VALUES = 12;
export const TUBE_JOINT_ATTRIBUTE = "cadTubeJoint";
export const TUBE_REST_POSITION_ATTRIBUTE = "cadTubeRestPosition";
export const TUBE_REST_NORMAL_ATTRIBUTE = "cadTubeRestNormal";

// --- the payload -----------------------------------------------------------------

const ARRAY_TYPES = {
  indices: Uint32Array,
  sourceTriangles: Uint32Array,
  edgeOrdinals: Uint32Array,
  edgeClasses: Uint8Array
};

/** cadgen's tube skins (`tube_skin_payload.py` says what each field is), with every
 * array field a typed view over the payload's bytes. */
export function decodeTubeSkins(arrayBuffer) {
  const data = new DataView(arrayBuffer);
  if (data.byteLength < 28 || data.getUint32(0, true) !== 0x46546c67 || data.getUint32(4, true) !== 2) {
    throw new Error("tube skins: not a skins payload");
  }
  const jsonLength = data.getUint32(12, true);
  const gltf = JSON.parse(new TextDecoder("utf-8").decode(new Uint8Array(arrayBuffer, 20, jsonLength)));
  const binStart = 28 + jsonLength;
  const content = gltf?.extras?.cadgenTubeSkins;
  if (content?.schemaVersion !== 1) {
    throw new Error(`tube skins: unsupported payload schema ${content?.schemaVersion ?? "none"} (expected 1)`);
  }
  const view = (field, index) => {
    const entry = gltf.bufferViews[index];
    const Type = ARRAY_TYPES[field] || Float32Array;
    return new Type(arrayBuffer, binStart + entry.byteOffset, entry.byteLength / Type.BYTES_PER_ELEMENT);
  };
  const bindings = content.bindings.map((binding) => Object.fromEntries(Object.entries(binding).map(
    ([field, value]) => [field, field === "occurrence" || field === "joints" ? value : view(field, value)]
  )));
  const tracks = content.tracks.map((track) => ({ ...track, keys: view("keys", track.keys) }));
  return { bindings, tracks };
}

/** Each tube track of `clips` given its skin from `skins`: `track.skin =
 * {joints, keys, byOccurrence}`. A tube track the payload does not pose cannot play. */
export function attachTubeSkins(clips, skins) {
  const bindings = skins.bindings.map(prepareBinding);
  const byTrack = new Map(skins.tracks.map((entry) => [`${entry.clip}\0${entry.track}`, entry]));
  for (const clip of Object.values(clips)) {
    clip.tracks.forEach((track, index) => {
      if (!track.tube) return;
      const entry = byTrack.get(`${clip.id}\0${index}`);
      const members = entry ? entry.bindings.map((binding) => bindings[binding]) : [];
      const joints = members[0]?.joints || 0;
      if (!entry || !joints || entry.keys.length !== track.times.length * joints * JOINT_VALUES
        || members.some((binding) => binding.joints !== joints)) {
        throw new Error(`animation clip ${JSON.stringify(clip.id)} track ${index} bends a tube its skins do not pose`);
      }
      track.skin = { joints, keys: entry.keys, byOccurrence: new Map(members.map((binding) => [binding.occurrence, binding])) };
    });
  }
  return clips;
}

// Once per binding: each joint's rest frame, inverted.
function prepareBinding(binding) {
  const count = binding.joints;
  const restInverse = new Float64Array(count * MATRIX_VALUES);
  const rest = binding.rest;
  for (let joint = 0; joint < count; joint += 1) {
    const at = joint * JOINT_VALUES;
    const m = rotation(rest[at + 3], rest[at + 4], rest[at + 5], rest[at + 6]);
    const out = joint * MATRIX_VALUES;
    for (let row = 0; row < 3; row += 1) {
      // R^T, and -R^T o.
      restInverse[out + row * 4] = m[row];
      restInverse[out + row * 4 + 1] = m[3 + row];
      restInverse[out + row * 4 + 2] = m[6 + row];
      restInverse[out + row * 4 + 3] = -(m[row] * rest[at] + m[3 + row] * rest[at + 1] + m[6 + row] * rest[at + 2]);
    }
  }
  return { ...binding, restInverse };
}

// The 3x3 of a unit quaternion, row-major.
function rotation(x, y, z, w) {
  return [
    1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w),
    2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w),
    2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)
  ];
}

// --- a pose ----------------------------------------------------------------------

/** One record's tube at a frame: the key bracket of its track and its binding. */
export function tubeSkinPose(track, occurrenceId, index, u) {
  const binding = track.skin?.byOccurrence.get(occurrenceId);
  if (!binding) return null;
  return { binding, keys: track.skin.keys, index, u: u > 0 ? u : 0, braid: track.braid || null };
}

function samePose(a, b) {
  return Boolean(a && b) && a.binding === b.binding && a.keys === b.keys && a.index === b.index && a.u === b.u;
}

// The joints of a pose, blended: origins lerped, rotations slerped the short way --
// three's own slerpFlat, which is the step glTF's LINEAR sampler takes.
function blendJoints(THREE, pose, out) {
  const { binding, keys, index, u } = pose;
  const count = binding.joints;
  const from = index * count * JOINT_VALUES;
  const to = u > 0 ? from + count * JOINT_VALUES : from;
  for (let joint = 0; joint < count; joint += 1) {
    const a = from + joint * JOINT_VALUES;
    const b = to + joint * JOINT_VALUES;
    const at = joint * JOINT_VALUES;
    out[at] = keys[a] + (keys[b] - keys[a]) * u;
    out[at + 1] = keys[a + 1] + (keys[b + 1] - keys[a + 1]) * u;
    out[at + 2] = keys[a + 2] + (keys[b + 2] - keys[a + 2]) * u;
    THREE.Quaternion.slerpFlat(out, at + 3, keys, a + 3, keys, b + 3, u);
  }
  return out;
}

const scratch = new Float64Array(MATRIX_VALUES);

// Each joint's motion of a component-local point, base^-1 . joint . rest^-1 . base,
// as the rows of a 3x4.
function jointMatrices(THREE, state, pose) {
  const { binding } = pose;
  const joints = blendJoints(THREE, pose, state.joints);
  const out = state.matrices;
  const k = state.restTimesBase;
  const inverse = state.baseInverse;
  for (let joint = 0; joint < binding.joints; joint += 1) {
    const at = joint * JOINT_VALUES;
    const r = rotation(joints[at + 3], joints[at + 4], joints[at + 5], joints[at + 6]);
    const o = joint * MATRIX_VALUES;
    // p = joint . (rest^-1 . base): the rest-relative motion in the document's space.
    const p = scratch;
    for (let row = 0; row < 3; row += 1) {
      for (let column = 0; column < 4; column += 1) {
        p[row * 4 + column] = r[row * 3] * k[o + column] + r[row * 3 + 1] * k[o + 4 + column]
          + r[row * 3 + 2] * k[o + 8 + column] + (column === 3 ? joints[at + row] : 0);
      }
    }
    for (let row = 0; row < 3; row += 1) {
      for (let column = 0; column < 4; column += 1) {
        out[o + row * 4 + column] = inverse[row * 4] * p[column] + inverse[row * 4 + 1] * p[4 + column]
          + inverse[row * 4 + 2] * p[8 + column] + (column === 3 ? inverse[row * 4 + 3] : 0);
      }
    }
  }
  return out;
}

// Points skinned on the CPU: `rest` (xyz) blended between their two joints.
function skinPoints(matrices, count, rest, along, out, normals = null, restNormals = null) {
  for (let point = 0; point < along.length; point += 1) {
    const lower = Math.min(Math.floor(along[point]), count - 2);
    const weight = along[point] - lower;
    const a = lower * MATRIX_VALUES;
    const b = a + MATRIX_VALUES;
    const x = rest[point * 3];
    const y = rest[point * 3 + 1];
    const z = rest[point * 3 + 2];
    for (let row = 0; row < 3; row += 1) {
      const pa = matrices[a + row * 4] * x + matrices[a + row * 4 + 1] * y + matrices[a + row * 4 + 2] * z + matrices[a + row * 4 + 3];
      const pb = matrices[b + row * 4] * x + matrices[b + row * 4 + 1] * y + matrices[b + row * 4 + 2] * z + matrices[b + row * 4 + 3];
      out[point * 3 + row] = pa + (pb - pa) * weight;
    }
    if (normals) {
      const nx = restNormals[point * 3];
      const ny = restNormals[point * 3 + 1];
      const nz = restNormals[point * 3 + 2];
      let length = 0;
      for (let row = 0; row < 3; row += 1) {
        const na = matrices[a + row * 4] * nx + matrices[a + row * 4 + 1] * ny + matrices[a + row * 4 + 2] * nz;
        const nb = matrices[b + row * 4] * nx + matrices[b + row * 4 + 1] * ny + matrices[b + row * 4 + 2] * nz;
        normals[point * 3 + row] = na + (nb - na) * weight;
        length += normals[point * 3 + row] ** 2;
      }
      length = Math.sqrt(length) || 1;
      for (let row = 0; row < 3; row += 1) normals[point * 3 + row] /= length;
    }
  }
}

// --- the GPU stage -----------------------------------------------------------------

// The joint texture holds three texels per joint, the rows of its 3x4.
const PARS = `
attribute float ${TUBE_JOINT_ATTRIBUTE};
attribute vec3 ${TUBE_REST_POSITION_ATTRIBUTE};
attribute vec3 ${TUBE_REST_NORMAL_ATTRIBUTE};
uniform sampler2D cadTubeJointTexture;
uniform float cadTubeJointCount;
uniform float cadTubeSkinEnabled;
vec3 cadSkinPoint;
vec3 cadSkinNormal;
bool cadSkinEvaluated = false;
mat4 cadTubeJointMatrix(float joint) {
  float v = (joint + 0.5) / cadTubeJointCount;
  vec4 a = texture2D(cadTubeJointTexture, vec2(0.5 / 3.0, v));
  vec4 b = texture2D(cadTubeJointTexture, vec2(1.5 / 3.0, v));
  vec4 c = texture2D(cadTubeJointTexture, vec2(2.5 / 3.0, v));
  return mat4(a.x, b.x, c.x, 0.0, a.y, b.y, c.y, 0.0, a.z, b.z, c.z, 0.0, a.w, b.w, c.w, 1.0);
}
void cadEvaluateSkin() {
  if (cadSkinEvaluated || cadTubeSkinEnabled < 0.5) return;
  cadSkinEvaluated = true;
  float lower = min(floor(${TUBE_JOINT_ATTRIBUTE}), cadTubeJointCount - 2.0);
  float weight = ${TUBE_JOINT_ATTRIBUTE} - lower;
  mat4 a = cadTubeJointMatrix(lower);
  mat4 b = cadTubeJointMatrix(lower + 1.0);
  vec4 rest = vec4(${TUBE_REST_POSITION_ATTRIBUTE}, 1.0);
  cadSkinPoint = mix((a * rest).xyz, (b * rest).xyz, weight);
  cadSkinNormal = normalize(mix(mat3(a) * ${TUBE_REST_NORMAL_ATTRIBUTE}, mat3(b) * ${TUBE_REST_NORMAL_ATTRIBUTE}, weight));
}
`;

function applySkinStage(shader) {
  shader.vertexShader = shader.vertexShader
    .replace("#include <common>", `#include <common>\n${PARS}`)
    .replace(
      "#include <beginnormal_vertex>",
      "#include <beginnormal_vertex>\ncadEvaluateSkin();\nif (cadTubeSkinEnabled > 0.5) objectNormal = cadSkinNormal;"
    )
    .replace(
      "#include <begin_vertex>",
      "#include <begin_vertex>\ncadEvaluateSkin();\nif (cadTubeSkinEnabled > 0.5) transformed = cadSkinPoint;"
    );
}

// A material patched for an earlier state keeps its uniform objects (a compiled
// program references them); a later state copies its values into them.
function patchMaterial(material, uniforms) {
  if (!material) return;
  const stage = ensureTubeMaterialStage(material, TUBE_SKIN_STAGE, () => ({ uniforms, apply: applySkinStage }));
  if (stage.uniforms === uniforms) return;
  for (const [name, uniform] of Object.entries(uniforms)) {
    if (stage.uniforms[name]) {
      stage.uniforms[name].value = uniform.value;
    } else {
      stage.uniforms[name] = uniform;
      material.needsUpdate = true;
    }
  }
}

/** Re-patch a skinned record's materials: a theme or selection pass may have swapped them. */
export function syncTubeSkinMaterials(record) {
  const gpu = record?.tubeSkinState?.gpu;
  if (!gpu?.active) return;
  for (const object of [record.mesh, record.silhouette, record.ghostMesh]) {
    if (object) patchMaterial(object.material, gpu.uniforms);
  }
  patchMaterial(record.mesh.customDepthMaterial, gpu.uniforms);
  patchMaterial(record.mesh.customDistanceMaterial, gpu.uniforms);
}

function gpuState(THREE, record, state) {
  if (state.gpu) return state.gpu;
  const count = state.binding.joints;
  const texture = new THREE.DataTexture(new Float32Array(count * MATRIX_VALUES), 3, count, THREE.RGBAFormat, THREE.FloatType);
  texture.needsUpdate = true;
  state.geometry.addEventListener("dispose", () => texture.dispose());
  if (!record.mesh.customDepthMaterial) {
    record.mesh.customDepthMaterial = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking });
    record.mesh.customDistanceMaterial = new THREE.MeshDistanceMaterial();
    record.mesh.material.addEventListener("dispose", () => {
      record.mesh.customDepthMaterial?.dispose();
      record.mesh.customDistanceMaterial?.dispose();
    });
  }
  state.gpu = {
    texture,
    active: false,
    uniforms: {
      cadTubeJointTexture: { value: texture },
      cadTubeJointCount: { value: count },
      cadTubeSkinEnabled: { value: 1 }
    }
  };
  return state.gpu;
}

// --- a record ----------------------------------------------------------------------

function placementOf(THREE, record) {
  const base = new THREE.Matrix4();
  if (record.baseTransform) base.fromArray(record.baseTransform).transpose();
  return base;
}

// The binding drawn for one record: the component geometry swapped for the
// binding's (rest positions and normals kept for the GPU; writable copies a pose
// fills for the CPU), the component's face ids and colours carried to the refined
// triangles, and the record's placement folded into each joint's rest.
function createSkinState(THREE, record, previous, binding) {
  const original = previous?.original || record.mesh.geometry;
  const originalFaceIds = previous?.originalFaceIds || record.mesh.userData?.faceIds;
  const geometry = new THREE.BufferGeometry();
  geometry.setIndex(new THREE.BufferAttribute(binding.indices, 1));
  geometry.setAttribute("position", new THREE.BufferAttribute(binding.positions.slice(), 3));
  geometry.setAttribute("normal", new THREE.BufferAttribute(binding.normals.slice(), 3));
  geometry.setAttribute(TUBE_JOINT_ATTRIBUTE, new THREE.BufferAttribute(binding.along, 1));
  geometry.setAttribute(TUBE_REST_POSITION_ATTRIBUTE, new THREE.BufferAttribute(binding.positions, 3));
  geometry.setAttribute(TUBE_REST_NORMAL_ATTRIBUTE, new THREE.BufferAttribute(binding.normals, 3));
  geometry.setAttribute(TUBE_MATERIAL_ATTRIBUTE, new THREE.BufferAttribute(binding.material, 3));
  const colors = original.attributes.color;
  if (colors && original.index) {
    // A component's vertices belong to one face each, so a refined vertex takes the
    // colour of the triangle it refines.
    const out = new Float32Array(binding.positions.length);
    const corners = original.index.array;
    for (let triangle = 0; triangle < binding.sourceTriangles.length; triangle += 1) {
      const source = corners[binding.sourceTriangles[triangle] * 3];
      for (let corner = 0; corner < 3; corner += 1) {
        const vertex = binding.indices[triangle * 3 + corner];
        out[vertex * 3] = colors.getX(source);
        out[vertex * 3 + 1] = colors.getY(source);
        out[vertex * 3 + 2] = colors.getZ(source);
      }
    }
    geometry.setAttribute("color", new THREE.BufferAttribute(out, 3));
  }
  geometry.userData = { ...geometry.userData, cadSceneCachedGeometry: false, __bvhSkipped: true };
  geometry.boundsTree = null;
  previous?.geometry.dispose();

  const base = placementOf(THREE, record);
  const baseInverse = base.clone().invert();
  const rows = (matrix) => {
    const e = matrix.elements;
    return [e[0], e[4], e[8], e[12], e[1], e[5], e[9], e[13], e[2], e[6], e[10], e[14]];
  };
  const b = rows(base);
  const count = binding.joints;
  const restTimesBase = new Float64Array(count * MATRIX_VALUES);
  for (let joint = 0; joint < count; joint += 1) {
    const o = joint * MATRIX_VALUES;
    const r = binding.restInverse;
    for (let row = 0; row < 3; row += 1) {
      for (let column = 0; column < 4; column += 1) {
        restTimesBase[o + row * 4 + column] = r[o + row * 4] * b[column] + r[o + row * 4 + 1] * b[4 + column]
          + r[o + row * 4 + 2] * b[8 + column] + (column === 3 ? r[o + row * 4 + 3] : 0);
      }
    }
  }
  // How far the tube reaches from its joints, in the document's space: no point
  // sits further than `radius` from either joint it rides, and a joint moves
  // rigidly, so a posed point is within `radius` of the blend of its joints' posed
  // origins -- the joints' box grown by it holds every pose.
  let radius = 0;
  const placed = new THREE.Vector3();
  const reach = (points, along) => {
    for (let point = 0; point < along.length; point += 1) {
      placed.fromArray(points, point * 3).applyMatrix4(base);
      const lower = Math.min(Math.floor(along[point]), count - 2);
      for (const joint of [lower, lower + 1]) {
        const at = joint * JOINT_VALUES;
        radius = Math.max(radius, Math.hypot(placed.x - binding.rest[at], placed.y - binding.rest[at + 1], placed.z - binding.rest[at + 2]));
      }
    }
  };
  reach(binding.positions, binding.along);
  reach(binding.edgePositions, binding.edgeAlong);

  const state = {
    binding,
    original,
    originalFaceIds,
    geometry,
    edges: skinEdgeLines(binding),
    sourceTriangles: binding.sourceTriangles,
    base,
    baseInverse: rows(baseInverse),
    restTimesBase,
    radius,
    joints: new Float32Array(count * JOINT_VALUES),
    matrices: new Float64Array(count * MATRIX_VALUES),
    active: false,
    lastPose: null,
    cpuPose: null,
    gpu: previous?.gpu && previous.binding === binding ? previous.gpu : null,
    partBounds: previous?.partBounds || record.partBounds
  };
  record.mesh.geometry = geometry;
  if (originalFaceIds) {
    record.mesh.userData.faceIds = Uint32Array.from(binding.sourceTriangles, (triangle) => originalFaceIds[triangle]);
  }
  record.geometry = geometry;
  if (record.silhouette) record.silhouette.geometry = geometry;
  if (record.ghostMesh) record.ghostMesh.geometry = geometry;
  return state;
}

// The binding's edge segments as the component's edges are drawn
// (`buildCadEdgeLines`: grouped by drawn class), with each point's joint
// coordinate in the lines' own point order.
function skinEdgeLines(binding) {
  const count = binding.edgeOrdinals.length;
  const rows = new Uint32Array(count * MESH_TABLE_COLUMNS);
  const along = new Float32Array(count * 6);
  for (let segment = 0; segment < count; segment += 1) {
    rows.set([binding.edgeOrdinals[segment], segment * 2, 2, binding.edgeClasses[segment]], segment * MESH_TABLE_COLUMNS);
    along[segment * 6] = binding.edgeAlong[segment * 2];
    along[segment * 6 + 3] = binding.edgeAlong[segment * 2 + 1];
  }
  const lines = buildCadEdgeLines(rows, binding.edgePositions);
  const order = buildCadEdgeLines(rows, along).positions;
  const pointAlong = new Float32Array(order.length / 3);
  for (let point = 0; point < pointAlong.length; point += 1) pointAlong[point] = order[point * 3];
  return { ...lines, owner: binding, along: pointAlong };
}

// Straight again. The record keeps the skin's geometry, at rest, as it keeps the
// skin's edges: every publish resets the pose before the clip bends it again, and
// swapping geometries there would rebuild the record's draw on every publish.
function restore(record, state) {
  const { geometry, binding } = state;
  geometry.attributes.position.array.set(binding.positions);
  geometry.attributes.normal.array.set(binding.normals);
  geometry.attributes.position.needsUpdate = true;
  geometry.attributes.normal.needsUpdate = true;
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  if (state.gpu) {
    state.gpu.uniforms.cadTubeSkinEnabled.value = 0;
    state.gpu.active = false;
  }
  record.mesh.userData.cadBeforeRaycast = null;
  record.partBounds = state.partBounds;
  state.active = false;
  state.lastPose = null;
  state.cpuPose = null;
  poseEdges(record, state, null);
}

// The record's private edge lines posed (null: at rest).
function poseEdges(record, state, matrices) {
  const lines = state.edges;
  const points = matrices ? new Float32Array(lines.positions.length) : lines.positions;
  if (matrices) skinPoints(matrices, state.binding.joints, lines.positions, lines.along, points);
  for (const line of record.edges?.children || []) {
    const range = line.userData?.cadEdgeRange;
    const geometry = line.geometry;
    if (!range || !geometry) continue;
    const attribute = geometry.attributes.instanceStart?.data || geometry.attributes.position;
    const pairs = attribute?.array;
    if (!pairs || pairs.length !== range.segmentCount * 6) continue;
    for (let segment = 0; segment < range.segmentCount; segment += 1) {
      for (let end = 0; end < 2; end += 1) {
        const point = lines.indices[(range.segmentStart + segment) * 2 + end] * 3;
        pairs[segment * 6 + end * 3] = points[point];
        pairs[segment * 6 + end * 3 + 1] = points[point + 1];
        pairs[segment * 6 + end * 3 + 2] = points[point + 2];
      }
    }
    attribute.needsUpdate = true;
    geometry.computeBoundingBox?.();
    geometry.computeBoundingSphere?.();
  }
}

// The pose's box: its joints' origins, grown by the tube's reach, in the document
// and in the component's frame.
function poseBounds(THREE, record, state) {
  const box = new THREE.Box3();
  const point = new THREE.Vector3();
  for (let joint = 0; joint < state.binding.joints; joint += 1) {
    box.expandByPoint(point.fromArray(state.joints, joint * JOINT_VALUES));
  }
  box.expandByScalar(state.radius + 1e-4);
  record.partBounds = { min: box.min.toArray(), max: box.max.toArray() };
  const local = box.clone().applyMatrix4(state.base.clone().invert());
  state.geometry.boundingBox = local;
  state.geometry.boundingSphere = local.getBoundingSphere(new THREE.Sphere());
}

// The exact CPU surface of the current pose, made when a pick needs it.
function materialize(state) {
  if (state.cpuPose === state.lastPose) return;
  const { geometry, binding } = state;
  skinPoints(state.matrices, binding.joints, binding.positions, binding.along,
    geometry.attributes.position.array, geometry.attributes.normal.array, binding.normals);
  geometry.attributes.position.needsUpdate = true;
  geometry.attributes.normal.needsUpdate = true;
  state.cpuPose = state.lastPose;
}

/** Bend (or, with a null pose, straighten) one record's tube. */
export function applyRecordTubeSkin(THREE, record, pose) {
  if (!record?.mesh?.geometry) return;
  record.effectDeformation = pose || null;
  applyTubeBraidMaterial(THREE, record.material || record.mesh.material, pose?.braid || null);
  let state = record.tubeSkinState;
  if (!pose) {
    if (state?.active) restore(record, state);
    return;
  }
  if (state?.active && samePose(state.lastPose, pose)) {
    syncTubeSkinMaterials(record);
    return;
  }
  if (!state || state.binding !== pose.binding) {
    state = record.tubeSkinState = createSkinState(THREE, record, state, pose.binding);
  }
  // The record's edges leave the component's instanced draw for a private line
  // drawn from the binding's segments, which bend with the surface.
  if (!state.edgesBound) {
    record.bindTubeEdges?.(state.edges);
    state.edgesBound = true;
  }
  const matrices = jointMatrices(THREE, state, pose);
  state.lastPose = pose;
  state.active = true;
  poseBounds(THREE, record, state);
  if (record.edges && record.edges.visible !== false) poseEdges(record, state, matrices);
  if (record.gpuTubeSkinAllowed === true) {
    const gpu = gpuState(THREE, record, state);
    const texels = gpu.texture.image.data;
    for (let index = 0; index < matrices.length; index += 1) texels[index] = matrices[index];
    gpu.texture.needsUpdate = true;
    gpu.uniforms.cadTubeSkinEnabled.value = 1;
    gpu.active = true;
    syncTubeSkinMaterials(record);
    record.mesh.userData.cadBeforeRaycast = (raycaster) => {
      if (!state.active) return true;
      const ray = raycaster.ray.clone().applyMatrix4(record.mesh.matrixWorld.clone().invert());
      if (!ray.intersectsBox(state.geometry.boundingBox)) return false;
      materialize(state);
      return true;
    };
    return;
  }
  materialize(state);
}

/** Bring a record's edges to its current pose (they skip poses while hidden). */
export function poseRecordTubeEdges(record) {
  const state = record?.tubeSkinState;
  if (state?.active) poseEdges(record, state, state.matrices);
}
