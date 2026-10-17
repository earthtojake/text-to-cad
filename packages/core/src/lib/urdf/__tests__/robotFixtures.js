// Robot payloads for the robot scene's tests, built by hand in the shape cadgen resolves
// (`cadgen.robot_payload`): the articulation (the STEP format, over links), the visual list and
// the link facts. Hand-built so a test reads every number it asserts against; what cadgen writes
// for real descriptions is held current by the Python suite (`tests/python/.../test_robot_payload.py`)
// and served to the browser suite from `packages/ui/src/renderers/robot/__fixtures__`.
import { buildRobotParts } from "../robotParts.js";

const DEG = 180 / Math.PI;
export const identity = () => [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
export const translation = (x, y, z) => [1, 0, 0, x, 0, 1, 0, y, 0, 0, 1, z, 0, 0, 0, 1];
// A primitive is meshed in metres and drawn in millimetres: its placement scales by 0.001.
export const scaled = (x, y, z, s = 0.001) => [s, 0, 0, x, 0, s, 0, y, 0, 0, s, z, 0, 0, 0, 1];

/** A box mesh as the page's loaders hand one back (`buildMeshDataFromGlbBuffer` shape), in millimetres. */
export function boxMesh([sx, sy, sz], { colors = null, parts = [] } = {}) {
  const [hx, hy, hz] = [sx / 2, sy / 2, sz / 2];
  const corners = [[-hx, -hy, -hz], [hx, -hy, -hz], [hx, hy, -hz], [-hx, hy, -hz], [-hx, -hy, hz], [hx, -hy, hz], [hx, hy, hz], [-hx, hy, hz]];
  const faces = [[0, 2, 1, 0, 3, 2], [4, 5, 6, 4, 6, 7], [0, 1, 5, 0, 5, 4], [2, 3, 7, 2, 7, 6], [1, 2, 6, 1, 6, 5], [3, 0, 4, 3, 4, 7]];
  return {
    vertices: new Float32Array(corners.flat()),
    indices: new Uint32Array(faces.flat()),
    normals: new Float32Array(0),
    colors: colors || new Float32Array(0),
    bounds: { min: [-hx, -hy, -hz], max: [hx, hy, hz] },
    has_source_colors: Boolean(colors),
    parts
  };
}

export const row = (control, weight = 1, bias = 0) => ({ bias, terms: [[control, weight]] });

// base -(yaw, continuous Z, 0.1 up)-> turret -(pitch, revolute Y, 1 m up, turned 0.3 about Z)-> arm
// -(lift, prismatic Z, 1 m along the arm)-> tool, with a fixed camera on the turret, a finger pair
// (finger_mirror = -finger) on the tool, and a wheel whose geometry sits on its own axis.
export const ARM = Object.freeze({
  schemaVersion: 2, kind: "urdf", name: "arm", root: "base",
  articulation: {
    schemaVersion: 2,
    controls: [
      { id: "yaw", label: "yaw", unit: "deg", min: null, max: null, default: 0 },
      { id: "pitch", label: "pitch", unit: "deg", min: -90, max: 90, default: 0 },
      { id: "lift", label: "lift", unit: "m", min: 0, max: 0.5, default: 0 },
      { id: "finger", label: "finger", unit: "m", min: 0, max: 0.04, default: 0 },
      { id: "wheel", label: "wheel", unit: "deg", min: null, max: null, default: 0 }
    ],
    joints: [
      { id: "yaw", parent: null, kind: "revolute", origin: [0, 0, 0.1], axis: [0, 0, 1], turn: row("yaw") },
      { id: "pitch", parent: "yaw", kind: "revolute", origin: [0, 0, 1.1], axis: [-Math.sin(0.3), Math.cos(0.3), 0], turn: row("pitch") },
      { id: "lift", parent: "pitch", kind: "slider", origin: [Math.cos(0.3), Math.sin(0.3), 1.1], axis: [0, 0, 1], travel: row("lift") },
      { id: "camera_mount", parent: "yaw", kind: "fixed" },
      { id: "finger", parent: "lift", kind: "slider", origin: [Math.cos(0.3), Math.sin(0.3), 1.1], axis: [-Math.sin(0.3), Math.cos(0.3), 0], travel: row("finger") },
      { id: "finger_mirror", parent: "lift", kind: "slider", origin: [Math.cos(0.3), Math.sin(0.3), 1.1], axis: [-Math.sin(0.3), Math.cos(0.3), 0], travel: row("finger", -1) },
      { id: "wheel", parent: null, kind: "revolute", origin: [0, 2, 0], axis: [0, -1, 0], turn: row("wheel") }
    ],
    carries: { yaw: ["turret"], pitch: ["arm"], lift: ["tool"], camera_mount: ["camera"], finger: ["finger_link"], finger_mirror: ["finger_mirror_link"], wheel: ["wheel_link"] },
    handles: [
      { id: "yaw", joint: "yaw", dof: "turn", control: "yaw", weight: 1, label: "yaw", unit: "deg", min: null, max: null },
      { id: "pitch", joint: "pitch", dof: "turn", control: "pitch", weight: 1, label: "pitch", unit: "deg", min: -90, max: 90 },
      { id: "lift", joint: "lift", dof: "travel", control: "lift", weight: 1, label: "lift", unit: "m", min: 0, max: 0.5 },
      { id: "finger", joint: "finger", dof: "travel", control: "finger", weight: 1, label: "finger", unit: "m", min: 0, max: 0.04 },
      { id: "finger_mirror", joint: "finger_mirror", dof: "travel", control: "finger", weight: -1, label: "finger_mirror", unit: "m", min: -0.04, max: 0 },
      { id: "wheel", joint: "wheel", dof: "turn", control: "wheel", weight: 1, label: "wheel", unit: "deg", min: null, max: null }
    ],
    poses: {},
    opening: { yaw: 0, pitch: 0, lift: 0, finger: 0, wheel: 0 }
  },
  links: [
    { name: "base", placement: identity(), visuals: [{ name: "", type: "box", filename: "", size: [0.6, 0.6, 0.1], origin: { xyz: [0, 0, 0.05], rpy: [0, 0, 0] }, color: "#4d4d59", materialName: "m" }], collisions: [], inertial: null },
    { name: "turret", placement: translation(0, 0, 0.1), visuals: [{ name: "", type: "box", filename: "", size: [0.2, 0.2, 1], origin: { xyz: [0, 0, 0.5], rpy: [0, 0, 0] }, color: "", materialName: "" }], collisions: [], inertial: null },
    { name: "arm", placement: [Math.cos(0.3), -Math.sin(0.3), 0, 0, Math.sin(0.3), Math.cos(0.3), 0, 0, 0, 0, 1, 1.1, 0, 0, 0, 1], visuals: [{ name: "", type: "box", filename: "", size: [1, 0.2, 0.2], origin: { xyz: [0.5, 0, 0], rpy: [0, 0, 0] }, color: "#e6801a", materialName: "m" }], collisions: [], inertial: null },
    { name: "tool", placement: [Math.cos(0.3), -Math.sin(0.3), 0, Math.cos(0.3), Math.sin(0.3), Math.cos(0.3), 0, Math.sin(0.3), 0, 0, 1, 1.1, 0, 0, 0, 1], visuals: [{ name: "", type: "box", filename: "", size: [0.1, 0.1, 0.1], origin: { xyz: [0, 0, 0], rpy: [0, 0, 0] }, color: "", materialName: "" }], collisions: [], inertial: null },
    { name: "camera", placement: translation(0, 0, 1.3), visuals: [], collisions: [], inertial: null },
    { name: "finger_link", placement: [Math.cos(0.3), -Math.sin(0.3), 0, Math.cos(0.3), Math.sin(0.3), Math.cos(0.3), 0, Math.sin(0.3), 0, 0, 1, 1.1, 0, 0, 0, 1], visuals: [], collisions: [], inertial: null },
    { name: "finger_mirror_link", placement: [Math.cos(0.3), -Math.sin(0.3), 0, Math.cos(0.3), Math.sin(0.3), Math.cos(0.3), 0, Math.sin(0.3), 0, 0, 1, 1.1, 0, 0, 0, 1], visuals: [], collisions: [], inertial: null },
    { name: "wheel_link", placement: [1, 0, 0, 0, 0, 0, -1, 2, 0, 1, 0, 0, 0, 0, 0, 1], visuals: [{ name: "", type: "cylinder", filename: "", radius: 0.3, length: 0.1, origin: { xyz: [0, 0, 0], rpy: [0, 0, 0] }, color: "", materialName: "" }], collisions: [], inertial: null }
  ],
  joints: [
    { name: "yaw", type: "continuous", parent: "base", child: "turret", axis: [0, 0, 1], origin: { xyz: [0, 0, 0.1], rpy: [0, 0, 0] }, limit: null, mimic: null },
    { name: "pitch", type: "revolute", parent: "turret", child: "arm", axis: [0, 1, 0], origin: { xyz: [0, 0, 1], rpy: [0, 0, 0.3] }, limit: { lower: -1.5708, upper: 1.5708, effort: 1, velocity: 1 }, mimic: null },
    { name: "lift", type: "prismatic", parent: "arm", child: "tool", axis: [0, 0, 1], origin: { xyz: [1, 0, 0], rpy: [0, 0, 0] }, limit: { lower: 0, upper: 0.5, effort: 1, velocity: 1 }, mimic: null },
    { name: "camera_mount", type: "fixed", parent: "turret", child: "camera", axis: null, origin: { xyz: [0, 0, 1.2], rpy: [0, 0.5, 0] }, limit: null, mimic: null },
    { name: "finger", type: "prismatic", parent: "tool", child: "finger_link", axis: [0, 1, 0], origin: { xyz: [0, 0, 0], rpy: [0, 0, 0] }, limit: { lower: 0, upper: 0.04, effort: 1, velocity: 1 }, mimic: null },
    { name: "finger_mirror", type: "prismatic", parent: "tool", child: "finger_mirror_link", axis: [0, 1, 0], origin: { xyz: [0, 0, 0], rpy: [0, 0, 0] }, limit: { lower: -0.04, upper: 0, effort: 1, velocity: 1 }, mimic: { joint: "finger", multiplier: -1, offset: 0 } },
    { name: "wheel", type: "continuous", parent: "base", child: "wheel_link", axis: [0, 0, 1], origin: { xyz: [0, 2, 0], rpy: [1.5708, 0, 0] }, limit: null, mimic: null }
  ],
  visuals: [
    { id: "base:v1", link: "base", label: "box", placement: scaled(0, 0, 0.05), color: "#4d4d59", mesh: { format: "glb", url: "/primitives/box-0.6-0.6-0.1.glb" } },
    { id: "turret:v1", link: "turret", label: "box", placement: scaled(0, 0, 0.6), color: "", mesh: { format: "glb", url: "/primitives/box-0.2-0.2-1.glb" } },
    { id: "arm:v1", link: "arm", label: "box", placement: [0.001 * Math.cos(0.3), -0.001 * Math.sin(0.3), 0, 0.5 * Math.cos(0.3), 0.001 * Math.sin(0.3), 0.001 * Math.cos(0.3), 0, 0.5 * Math.sin(0.3), 0, 0, 0.001, 1.1, 0, 0, 0, 1], color: "#e6801a", mesh: { format: "glb", url: "/primitives/box-1-0.2-0.2.glb" } },
    { id: "tool:v1", link: "tool", label: "box", placement: [0.001 * Math.cos(0.3), -0.001 * Math.sin(0.3), 0, Math.cos(0.3), 0.001 * Math.sin(0.3), 0.001 * Math.cos(0.3), 0, Math.sin(0.3), 0, 0, 0.001, 1.1, 0, 0, 0, 1], color: "", mesh: { format: "glb", url: "/primitives/box-0.1-0.1-0.1.glb" } },
    { id: "wheel_link:v1", link: "wheel_link", label: "cylinder", placement: [0.001, 0, 0, 0, 0, 0, -0.001, 2, 0, 0.001, 0, 0, 0, 0, 0, 1], color: "", mesh: { format: "glb", url: "/primitives/cylinder-0.3-0.1.glb" } }
  ],
  srdf: null,
  sdf: null
});

/** The ARM with an SRDF's semantics on it: two group states, `home` the opening. */
export const ARM_SRDF = Object.freeze({
  ...ARM,
  kind: "srdf",
  articulation: {
    ...ARM.articulation,
    poses: { "reach/home": { pitch: -0.5 * DEG }, "reach/raised": { yaw: 1.0 * DEG, pitch: -1.0 * DEG, lift: 0.2 }, "grip/open": { finger: 0.04 } },
    opening: { yaw: 0, pitch: -0.5 * DEG, lift: 0, finger: 0, wheel: 0 }
  },
  srdf: {
    planningGroups: [{ name: "reach", jointNames: ["yaw", "pitch", "lift"], linkNames: [], chains: [], subgroups: [] }, { name: "grip", jointNames: ["finger"], linkNames: [], chains: [], subgroups: [] }],
    endEffectors: [{ name: "gripper", parentLink: "tool", group: "grip", parentGroup: "reach", link: "tool" }],
    groupStates: [{ id: "reach/home", name: "home", group: "reach" }, { id: "reach/raised", name: "raised", group: "reach" }, { id: "grip/open", name: "open", group: "grip" }],
    disabledCollisionPairs: [],
    groupsByLink: { turret: ["reach"], arm: ["reach"], tool: ["reach"], finger_link: ["grip"] }
  }
});

// An SDF-shaped robot: the hinge joint hangs from nothing (the base is the root), its child link
// sits 0.05 along the joint's X at an offset from the joint frame, so the joint frame and the
// child frame differ: the case a rest-space delta over a rest placement exists for.
export const SWING = Object.freeze({
  schemaVersion: 2, kind: "sdf", name: "swing", root: "base",
  articulation: {
    schemaVersion: 2,
    controls: [{ id: "hinge", label: "hinge", unit: "deg", min: -1.2 * DEG, max: 1.2 * DEG, default: 0 },
      { id: "slide", label: "slide", unit: "m", min: 0, max: 0.3, default: 0 }],
    joints: [
      { id: "hinge", parent: null, kind: "revolute", origin: [0, 0, 0.2], axis: [0, 1, 0], turn: row("hinge") },
      { id: "slide", parent: "hinge", kind: "slider", origin: [0.55, 0, 0.2], axis: [1, 0, 0], travel: row("slide") }
    ],
    carries: { hinge: ["arm"], slide: ["tip"] },
    handles: [
      { id: "hinge", joint: "hinge", dof: "turn", control: "hinge", weight: 1, label: "hinge", unit: "deg", min: -1.2 * DEG, max: 1.2 * DEG },
      { id: "slide", joint: "slide", dof: "travel", control: "slide", weight: 1, label: "slide", unit: "m", min: 0, max: 0.3 }
    ],
    poses: {},
    opening: { hinge: 0, slide: 0 }
  },
  links: [
    { name: "base", placement: identity(), visuals: [{ name: "v", type: "box", filename: "", size: [0.4, 0.4, 0.1], origin: { xyz: [0, 0, 0.05], rpy: [0, 0, 0] }, color: "", materialName: "" }], collisions: [], inertial: null },
    { name: "arm", placement: translation(0.05, 0, 0.2), visuals: [{ name: "v", type: "box", filename: "", size: [0.5, 0.08, 0.06], origin: { xyz: [0.25, 0, 0], rpy: [0, 0, 0] }, color: "", materialName: "" }], collisions: [], inertial: null },
    { name: "tip", placement: translation(0.55, 0, 0.22), visuals: [{ name: "v", type: "sphere", filename: "", radius: 0.04, origin: { xyz: [0, 0, 0], rpy: [0, 0, 0] }, color: "", materialName: "" }], collisions: [], inertial: null }
  ],
  joints: [
    { name: "hinge", type: "revolute", parent: "base", child: "arm", axis: [0, 1, 0], origin: { xyz: [0, 0, 0.2], rpy: [0, 0, 0] }, limit: { lower: -1.2, upper: 1.2 }, mimic: null },
    { name: "slide", type: "prismatic", parent: "arm", child: "tip", axis: [1, 0, 0], origin: { xyz: [0.5, 0, 0], rpy: [0, 0, 0] }, limit: { lower: 0, upper: 0.3 }, mimic: null }
  ],
  visuals: [
    { id: "base:v1", link: "base", label: "box", placement: scaled(0, 0, 0.05), color: "", mesh: { format: "glb", url: "/primitives/box-0.4-0.4-0.1.glb" } },
    { id: "arm:v1", link: "arm", label: "box", placement: scaled(0.3, 0, 0.2), color: "", mesh: { format: "glb", url: "/primitives/box-0.5-0.08-0.06.glb" } },
    { id: "tip:v1", link: "tip", label: "sphere", placement: scaled(0.55, 0, 0.22), color: "", mesh: { format: "glb", url: "/primitives/sphere-0.04.glb" } }
  ],
  srdf: null,
  sdf: { version: "1.9", documentKind: "model", worldName: "", modelName: "swing", rootLink: "base", rootLinks: ["base"], frameCount: 0, linkCount: 3, jointCount: 2,
    staticMetadata: { includes: [], plugins: [], sensors: [], lights: [], physics: [], nestedModelCount: 0 } }
});

/** The meshes a payload's visuals name, as the loaders hand them back: a box (in millimetres) per primitive URL. */
export function meshesFor(robot) {
  const meshes = new Map();
  for (const visual of robot.visuals) {
    const url = visual.mesh.url;
    if (meshes.has(url)) continue;
    const number = "(\\d+(?:\\.\\d+)?)";
    const size = new RegExp(`box-${number}-${number}-${number}`).exec(url);
    const round = new RegExp(`(?:cylinder|sphere)-${number}(?:-${number})?`).exec(url);
    const metres = size ? [Number(size[1]), Number(size[2]), Number(size[3])]
      : [2 * Number(round[1]), 2 * Number(round[1]), round[2] === undefined ? 2 * Number(round[1]) : Number(round[2])];
    meshes.set(url, boxMesh(metres.map(value => value * 1000)));
  }
  return meshes;
}

/** A payload with its once-built part list, as the robot renderer and the snapshot CLI load it. */
export function robotOf(robot, meshesByUrl = meshesFor(robot)) {
  return { robot, ...buildRobotParts(robot, meshesByUrl) };
}
