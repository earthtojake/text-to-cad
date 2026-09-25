import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { isKitScene, sceneFramingBounds } from "../viewer/sceneContract.js";
import { parseArmUrdf, parseSwingSdf, robotOf, solvedBounds } from "./__tests__/robotFixtures.js";
import { solveUrdfLinkWorldTransforms } from "./kinematics.js";
import { createRobotScene } from "./robotScene.js";

// The description solver (`solveUrdfLinkWorldTransforms`) is the ORACLE here: for any pose,
// the graph must put every link, and every box, exactly where the solver does. The graph is
// the ONE way a robot is posed, in the viewer and in a snapshot alike.

const INSPECT = Object.freeze({
  defaultColor: "#b6c4ce", fillColors: ["#b6c4ce", "#f4a7a7", "#f8c77e"], cycleColors: false, overrideSourceColors: false,
  tintStrength: 0, roughness: 0.58, metalness: 0.02, clearcoat: 0.12, clearcoatRoughness: 0.42, envMapIntensity: 0.42, emissiveIntensity: 0.02
});
const look = (patch = {}) => ({ materialSettings: { ...INSPECT, ...patch.materialSettings }, authored: patch.authored === true,
  surface: { style: "shaded", opacity: 1, ...patch.surface } });

// A seeded generator: a failure names a pose that can be replayed.
function random(seed) {
  let state = seed;
  return () => { state = (state * 1664525 + 1013904223) % 4294967296; return state / 4294967296; };
}
function randomPose(description, next) {
  // Beyond the limits on purpose: clamping is the solver's and must be the graph's too.
  return Object.fromEntries(description.joints.filter(joint => joint.type !== "fixed")
    .map(joint => [joint.name, joint.type === "prismatic" ? (next() - 0.3) * 1.2 : (next() - 0.5) * 500]));
}
const closeTo = (actual, expected, tolerance, message) => {
  assert.equal(actual.length, expected.length, message);
  actual.forEach((value, index) => assert.ok(Math.abs(value - expected[index]) <= tolerance, `${message}: [${index}] ${value} != ${expected[index]}`));
};

for (const [name, parse] of [["URDF", parseArmUrdf], ["SDF", parseSwingSdf]]) {
  test(`${name}: every link group is where the description solver puts that link, for any pose`, () => {
    const robot = robotOf(parse());
    const scene = createRobotScene(THREE, robot);
    const next = random(name.length * 7919);
    for (let round = 0; round < 40; round += 1) {
      const pose = round === 0 ? {} : randomPose(robot.description, next);
      scene.setJointValues(pose);
      const solved = solveUrdfLinkWorldTransforms(robot.description, pose);
      const frames = scene.linkFrames();
      assert.deepEqual([...frames.keys()].sort(), [...solved.keys()].sort());
      for (const [link, transform] of solved) closeTo(frames.get(link), transform, 1e-9, `${link} @ ${JSON.stringify(pose)}`);
      const posed = solvedBounds(robot, pose);
      const rest = solvedBounds(robot, {});
      closeTo([...scene.bounds.min, ...scene.bounds.max], [...posed.min, ...posed.max], 1e-9, `bounds @ ${JSON.stringify(pose)}`);
      closeTo([...scene.restBounds.min, ...scene.restBounds.max], [...rest.min, ...rest.max], 1e-9, "rest bounds never move");
    }
    scene.dispose();
  });
}

test("the scene is a graph: a group per link, a joint as static frame > motion > child link, meshes attached once", () => {
  const robot = robotOf(parseArmUrdf());
  const scene = createRobotScene(THREE, robot);
  assert.equal(isKitScene(scene), true);
  assert.equal(scene.object3D.name, "robot");
  const names = [];
  scene.object3D.traverse(object => names.push(object.name));
  assert.deepEqual(names.filter(value => value.startsWith("link:")).sort(), robot.description.links.map(link => `link:${link.name}`).sort());
  const arm = scene.links.get("arm");
  assert.deepEqual([arm.parent.name, arm.parent.parent.name, arm.parent.parent.parent.name], ["motion:pitch", "joint:pitch", "link:turret"]);
  assert.deepEqual(arm.children.filter(child => child.isMesh).map(mesh => [mesh.userData.partId, mesh.userData.linkName, mesh.castShadow]), [["arm:v1", "arm", true]]);
  assert.equal(scene.partCount, robot.parts.length);
  const everything = [];
  scene.object3D.traverse(object => everything.push(object.matrixAutoUpdate));
  assert.ok(everything.every(value => value === false), "every matrix is written, none derived per frame");
  assert.deepEqual(sceneFramingBounds(scene), scene.restBounds);
});

test("a pose writes only the matrices of the joints that changed, mimic followers included", () => {
  const robot = robotOf(parseArmUrdf());
  const scene = createRobotScene(THREE, robot);
  const writes = new Map();
  scene.object3D.traverse((object) => {
    if (!object.name.startsWith("motion:")) return;
    const set = object.matrix.set.bind(object.matrix);
    object.matrix.set = (...values) => { writes.set(object.name, (writes.get(object.name) || 0) + 1); return set(...values); };
  });
  const changed = (pose) => { writes.clear(); const moved = scene.setJointValues(pose); return { moved, written: [...writes.keys()].sort(), counted: scene.stats.lastPoseWrites }; };

  assert.deepEqual(changed({ pitch: 30 }), { moved: true, written: ["motion:pitch"], counted: 1 });
  assert.deepEqual(changed({ pitch: 30 }), { moved: false, written: [], counted: 0 }, "the same pose writes nothing");
  assert.deepEqual(changed({ pitch: 30, finger: 0.03 }), { moved: true, written: ["motion:finger", "motion:finger_mirror"], counted: 2 }, "a master carries its follower");
  assert.deepEqual(changed({ pitch: 400, finger: 0.03 }).written, ["motion:pitch"], "clamped to its limit");
  assert.deepEqual(changed({ pitch: 900, finger: 0.03 }), { moved: false, written: [], counted: 0 }, "further past the limit is the same pose");
  assert.equal(scene.jointValue("finger_mirror"), -0.03);
  assert.equal(scene.jointValue("yaw"), 0);
  assert.deepEqual(changed({ yaw: 725 }).written, ["motion:finger", "motion:finger_mirror", "motion:pitch", "motion:yaw"], "a continuous joint is not clamped; the rest return to default");
  assert.equal(scene.jointValue("yaw"), 725);
});

test("bounds follow the pose and the rest box does not; only the moved subtree is re-measured", () => {
  const robot = robotOf(parseArmUrdf());
  const scene = createRobotScene(THREE, robot);
  const rest = structuredClone(scene.restBounds);
  assert.deepEqual(scene.bounds, rest);
  scene.setJointValues({ pitch: -90 });
  assert.ok(scene.bounds.max[2] > rest.max[2] + 0.5, "the arm stands up");
  assert.deepEqual(scene.restBounds, rest);
  assert.equal(scene.bounds, scene.bounds, "one box per pose, not one per read");
});

test("the look: a description's colour, the viewer's surface colour without one, Color by part in the order parts always took", () => {
  const robot = robotOf(parseArmUrdf());
  const scene = createRobotScene(THREE, robot);
  const mesh = id => { let found = null; scene.object3D.traverse((object) => { if (object.userData.partId === id) found = object; }); return found; };
  scene.setSurfaceLook(look());
  assert.equal(mesh("arm:v1").material.userData.cadSourceColor, true);
  assert.equal(mesh("turret:v1").material.userData.cadSourceColor, false);
  assert.equal(mesh("turret:v1").material.color.getHexString(), new THREE.Color("#b6c4ce").getHexString());
  assert.equal(mesh("arm:v1").material.side, THREE.DoubleSide, "a mirrored <mesh scale> must not turn a link inside out");
  assert.equal(mesh("arm:v1").material.roughness, 0.58);
  // Render is a look like Solid: a robot authors no finish to keep.
  scene.setSurfaceLook({ ...look({ materialSettings: { roughness: 0.34, emissiveIntensity: 0 } }), authored: true });
  assert.equal(mesh("arm:v1").material.roughness, 0.34);
  scene.setSurfaceLook(look({ materialSettings: { overrideSourceColors: true, cycleColors: true } }));
  const palette = INSPECT.fillColors.map(color => new THREE.Color(color).getHexString());
  for (const part of robot.parts) assert.equal(mesh(part.id).material.color.getHexString(), palette[part.fillIndex % palette.length], part.id);
  scene.setSurfaceLook(look({ surface: { style: "flat", opacity: 0.5 } }));
  assert.equal(mesh("arm:v1").material.isMeshBasicMaterial, true);
  assert.equal(mesh("arm:v1").material.opacity, 0.5);
});

test("a colour the description gives a visual wins over the colours its mesh brought; without one the mesh's own are worn per vertex", () => {
  const description = parseArmUrdf();
  const triangle = { vertices: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]), indices: new Uint32Array([0, 1, 2]), normals: new Float32Array(0),
    colors: new Float32Array([1, 0, 0, 1, 0, 0, 1, 0, 0]), bounds: { min: [0, 0, 0], max: [1, 1, 0] }, has_source_colors: true, parts: [] };
  const visual = (name, color) => { const link = description.links.find(candidate => candidate.name === name);
    link.visuals = link.visuals.map(entry => ({ ...entry, primitive: null, meshUrl: "/robots/meshes/red.stl", color })); };
  visual("arm", "#0000ff");
  visual("tool", "");
  const scene = createRobotScene(THREE, robotOf(description, new Map([["/robots/meshes/red.stl", triangle]])));
  const mesh = name => scene.links.get(name).children.find(child => child.isMesh);
  scene.setSurfaceLook(look());
  assert.deepEqual([mesh("arm").material.vertexColors, mesh("arm").material.color.getHexString(), Boolean(mesh("arm").geometry.getAttribute("color"))], [false, "0000ff", false]);
  assert.deepEqual([mesh("tool").material.vertexColors, mesh("tool").material.color.getHexString(), Boolean(mesh("tool").geometry.getAttribute("color"))], [true, "ffffff", true]);
  assert.notEqual(mesh("tool").geometry.getAttribute("color").array, triangle.colors, "graded in the scene's own copy, never in the loader's");
  assert.notEqual(mesh("arm").geometry, mesh("tool").geometry, "one mesh, two geometries: only one of them carries colours");
});

test("picking walks up the graph to the link; a named object is itself", () => {
  const robot = robotOf(parseArmUrdf());
  // The tool's box as a named object of its mesh, as a GLB link's objects are.
  const parts = robot.parts.map(part => (part.id === "tool:v1" ? { ...part, id: "tool:v1/object/0", componentName: "flange" } : part));
  const scene = createRobotScene(THREE, { description: robot.description, parts });
  const down = (x, y) => new THREE.Ray(new THREE.Vector3(x, y, 10), new THREE.Vector3(0, 0, -1));
  const arm = scene.pick(down(0.5 * Math.cos(0.3), 0.5 * Math.sin(0.3)));
  assert.deepEqual([arm.kind, arm.linkName, arm.id], ["link", "arm", "link:arm"]);
  assert.ok(Math.abs(arm.point.z - 1.2) < 1e-6, "the surface the ray met first");
  assert.equal(scene.pick(down(5, 5)), null);
  // Just past the arm's end, where only the tool's box is under the ray.
  const flange = scene.pick(down(1.03 * Math.cos(0.3), 1.03 * Math.sin(0.3)));
  assert.deepEqual([flange.kind, flange.linkName, flange.componentId, flange.id], ["component", "tool", "tool:v1/object/0", "tool:v1/object/0"]);
  assert.equal(scene.hasComponent("tool:v1/object/0"), true);
  // Posed, the pick follows: the arm is no longer under the ray it was under.
  scene.setJointValues({ yaw: 90 });
  assert.equal(scene.pick(down(0.5 * Math.cos(0.3), 0.5 * Math.sin(0.3)))?.linkName ?? "base", "base");
});

test("a highlight round-trips to the exact look underneath it, in Solid, Flat and Render", () => {
  const robot = robotOf(parseArmUrdf());
  const scene = createRobotScene(THREE, robot);
  const arm = scene.links.get("arm").children.find(child => child.isMesh);
  const state = () => { const { material } = arm; return JSON.stringify([material.type, material.color.getHexString(), material.opacity, material.transparent,
    material.depthWrite, material.emissive?.getHexString() ?? null, material.emissiveIntensity ?? null, arm.renderOrder,
    arm.children.filter(child => child.visible).length]); };
  for (const [name, dressed] of [["solid", look()], ["flat", look({ surface: { style: "flat", opacity: 0.4 } })],
    ["render", { ...look({ materialSettings: { emissiveIntensity: 0 } }), authored: true }]]) {
    scene.setSurfaceLook(dressed);
    const base = state();
    scene.setHighlight({ hoveredLink: "arm" });
    const hovered = state();
    assert.notEqual(hovered, base, `${name}: hover shows`);
    scene.setHighlight({ hoveredLink: "arm", selectedLinks: ["arm"] });
    assert.notEqual(state(), hovered, `${name}: selection outranks hover`);
    assert.deepEqual([arm.renderOrder, arm.material.opacity, arm.children.filter(child => child.userData.isOcclusionGhost && child.visible).length], [23, 1, 1]);
    // A look change while highlighted keeps the highlight on the NEW look.
    scene.setSurfaceLook(dressed);
    assert.equal(arm.renderOrder, 23);
    scene.setHighlight({});
    assert.equal(state(), base, `${name}: and back, exactly`);
  }
});

test("visuals that name one mesh share one geometry, and dispose releases everything the scene made", () => {
  const description = parseArmUrdf();
  const mesh = { vertices: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]), indices: new Uint32Array([0, 1, 2]), normals: new Float32Array(0),
    colors: new Float32Array(0), bounds: { min: [0, 0, 0], max: [1, 1, 0] }, has_source_colors: false, parts: [] };
  for (const link of description.links.filter(candidate => ["finger_link", "finger_mirror_link"].includes(candidate.name))) {
    link.visuals = link.visuals.map(visual => ({ ...visual, primitive: null, meshUrl: "/robots/meshes/finger.stl" }));
  }
  const robot = robotOf(description, new Map([["/robots/meshes/finger.stl", mesh]]));
  const scene = createRobotScene(THREE, robot);
  const geometry = name => scene.links.get(name).children.find(child => child.isMesh).geometry;
  assert.equal(geometry("finger_link"), geometry("finger_mirror_link"));
  assert.equal(geometry("finger_link").getAttribute("position").array, mesh.vertices, "the loader's array, wrapped");

  scene.setSurfaceLook(look());
  scene.setHighlight({ selectedLinks: ["arm"] });
  const disposed = { geometry: 0, material: 0 };
  scene.object3D.traverse((object) => {
    if (!object.isMesh) return;
    object.geometry.addEventListener("dispose", () => { disposed.geometry += 1; });
    for (const material of [object.material].flat()) material.addEventListener("dispose", () => { disposed.material += 1; });
  });
  const parent = new THREE.Group().add(scene.object3D);
  scene.dispose();
  assert.equal(parent.children.length, 0);
  assert.ok(disposed.geometry >= 6 && disposed.material >= robot.parts.length, JSON.stringify(disposed));
  assert.equal(scene.pick(new THREE.Ray(new THREE.Vector3(0, 0, 10), new THREE.Vector3(0, 0, -1))), null, "a disposed scene answers nothing");
  assert.equal(scene.setJointValues({ pitch: 10 }), false);
});
