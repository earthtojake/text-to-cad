import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { jointDeltas, jointValues } from "../../common/articulation.js";
import { isKitScene, sceneFramingBounds } from "../viewer/sceneContract.js";
import { ARM, ARM_SRDF, SWING, boxMesh, robotOf } from "./__tests__/robotFixtures.js";
import { createRobotScene } from "./robotScene.js";

// The articulation player (`common/articulation.js`, the one STEP poses with) is the ORACLE here:
// for any control vector, the graph must put every link where that joint's world delta over the
// link's rest placement puts it. The graph is the ONE way a robot is posed, in the viewer and in
// a snapshot alike, and it decides nothing the payload did not.

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
function randomPose(robot, next) {
  // Beyond the limits on purpose: a control vector is normalized against the articulation.
  return Object.fromEntries(robot.articulation.controls.map(control => [control.id, control.unit === "m" ? (next() - 0.3) * 1.2 : (next() - 0.5) * 500]));
}
const closeTo = (actual, expected, tolerance, message) => {
  assert.equal(actual.length, expected.length, message);
  actual.forEach((value, index) => assert.ok(Math.abs(value - expected[index]) <= tolerance, `${message}: [${index}] ${value} != ${expected[index]}`));
};
// The oracle: each link's frame is its carrying joint's delta over its rest placement.
function solvedFrames(robot, values) {
  const deltas = jointDeltas(THREE, robot.articulation, values);
  const carrier = new Map(Object.entries(robot.articulation.carries).flatMap(([joint, links]) => links.map(link => [link, joint])));
  return new Map(robot.links.map(link => {
    const frame = new THREE.Matrix4().set(...link.placement);
    const delta = deltas.get(carrier.get(link.name));
    if (delta) frame.premultiply(delta);
    return [link.name, frame.transpose().toArray()];
  }));
}
// The oracle's box: every part's source box through its link's frame and its own placement.
function solvedBounds(model, values) {
  const frames = solvedFrames(model.robot, values);
  const deltas = jointDeltas(THREE, model.robot.articulation, values);
  const carrier = new Map(Object.entries(model.robot.articulation.carries).flatMap(([joint, links]) => links.map(link => [link, joint])));
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (const part of model.parts) {
    const placement = new THREE.Matrix4().set(...part.placement);
    const delta = deltas.get(carrier.get(part.link));
    if (delta) placement.premultiply(delta);
    const { min: low, max: high } = part.sourceBounds;
    for (let index = 0; index < 8; index += 1) {
      const corner = new THREE.Vector3(index & 4 ? high[0] : low[0], index & 2 ? high[1] : low[1], index & 1 ? high[2] : low[2]).applyMatrix4(placement);
      for (let axis = 0; axis < 3; axis += 1) { min[axis] = Math.min(min[axis], corner.getComponent(axis)); max[axis] = Math.max(max[axis], corner.getComponent(axis)); }
    }
  }
  void frames;
  return { min, max };
}

for (const [name, robot] of [["URDF", ARM], ["SDF", SWING]]) {
  test(`${name}: every link is where the articulation's delta over its rest placement puts it, for any control vector`, () => {
    const model = robotOf(robot);
    const scene = createRobotScene(THREE, model);
    const next = random(name.length * 7919);
    for (let round = 0; round < 40; round += 1) {
      const values = round === 0 ? {} : randomPose(robot, next);
      scene.setControlValues(values);
      const solved = solvedFrames(robot, Object.fromEntries(robot.articulation.controls.map(control => {
        // The scene normalizes as the player does: a limited control is clamped.
        const value = values[control.id] ?? 0;
        return [control.id, control.min === null ? value : Math.min(Math.max(value, control.min), control.max)];
      })));
      const frames = scene.linkFrames();
      assert.deepEqual([...frames.keys()].sort(), [...solved.keys()].sort());
      for (const [link, frame] of solved) closeTo(frames.get(link), frame, 1e-9, `${link} @ ${JSON.stringify(values)}`);
      const rest = solvedBounds(model, {});
      closeTo([...scene.restBounds.min, ...scene.restBounds.max], [...rest.min, ...rest.max], 1e-9, "rest bounds never move");
    }
    scene.dispose();
  });
}

test("the scene is a graph: a node per joint under its parent's, a link's meshes under the joint that carries it, attached once", () => {
  const model = robotOf(ARM);
  const scene = createRobotScene(THREE, model);
  assert.equal(isKitScene(scene), true);
  assert.equal(scene.object3D.name, "robot");
  const byName = new Map();
  scene.object3D.traverse(object => byName.set(object.name, object));
  assert.deepEqual([...byName.keys()].filter(value => value.startsWith("joint:")).sort(), ARM.articulation.joints.map(joint => `joint:${joint.id}`).sort());
  const arm = byName.get("arm:v1");
  assert.deepEqual([arm.parent.name, arm.parent.parent.name, arm.parent.parent.parent.name], ["joint:pitch", "joint:yaw", "robot"]);
  assert.deepEqual([arm.userData.partId, arm.userData.linkName, arm.castShadow], ["arm:v1", "arm", true]);
  assert.equal(byName.get("base:v1").parent.name, "robot", "a root link's mesh hangs from the robot itself");
  assert.equal(byName.get("joint:finger_mirror").parent.name, "joint:lift");
  assert.equal(scene.partCount, model.parts.length);
  const everything = [];
  scene.object3D.traverse(object => everything.push(object.matrixAutoUpdate));
  assert.ok(everything.every(value => value === false), "every matrix is written, none derived per frame");
  assert.deepEqual(sceneFramingBounds(scene), scene.restBounds);
  scene.dispose();
});

test("a pose writes only the joints whose rows changed, mimic followers included; a motion frame is the joint's delta", () => {
  const model = robotOf(ARM);
  const scene = createRobotScene(THREE, model);
  const writes = new Map();
  scene.object3D.traverse((object) => {
    if (!object.name.startsWith("joint:")) return;
    const set = object.matrix.set.bind(object.matrix);
    object.matrix.set = (...values) => { writes.set(object.name, (writes.get(object.name) || 0) + 1); return set(...values); };
  });
  const changed = (values) => { writes.clear(); const moved = scene.setControlValues(values); return { moved, written: [...writes.keys()].sort(), counted: scene.stats.lastPoseWrites }; };

  assert.deepEqual(changed({ pitch: 30 }), { moved: true, written: ["joint:pitch"], counted: 1 });
  assert.deepEqual(changed({ pitch: 30 }), { moved: false, written: [], counted: 0 }, "the same pose writes nothing");
  assert.deepEqual(changed({ pitch: 30, finger: 0.03 }), { moved: true, written: ["joint:finger", "joint:finger_mirror"], counted: 2 }, "a leader carries its follower");
  assert.deepEqual(scene.jointRow("finger_mirror"), { turn: 0, travel: -0.03 }, "the follower's row is the leader's, mirrored");
  assert.deepEqual(changed({ pitch: 400, finger: 0.03 }).written, ["joint:pitch"], "clamped to its limit");
  assert.deepEqual(changed({ pitch: 900, finger: 0.03 }), { moved: false, written: [], counted: 0 }, "further past the limit is the same pose");
  assert.deepEqual(changed({ yaw: 725 }).written, ["joint:finger", "joint:finger_mirror", "joint:pitch", "joint:yaw"], "a continuous joint is not clamped; the rest return to the opening");
  assert.equal(scene.jointRow("yaw").turn, 725);
  assert.equal(scene.jointRow("camera_mount").turn, 0, "a fixed joint has no row to write");
  assert.equal(scene.jointRow("nothing"), null);
  // The motion frame of a joint IS its world delta: what the handles hang on.
  const delta = jointDeltas(THREE, ARM.articulation, { yaw: 725 }).get("pitch");
  closeTo(scene.motionFrame("pitch").toArray(), delta.toArray(), 1e-9, "the pitch's frame after the yaw's turn");
  scene.dispose();
});

test("an SRDF's home state is the opening: a control the vector does not name rests there", () => {
  const scene = createRobotScene(THREE, robotOf(ARM_SRDF));
  scene.setControlValues({});
  assert.ok(Math.abs(scene.jointRow("pitch").turn - (-0.5 * 180 / Math.PI)) < 1e-9);
  scene.setControlValues({ yaw: 10 });
  assert.ok(Math.abs(scene.jointRow("pitch").turn - (-0.5 * 180 / Math.PI)) < 1e-9, "named controls over the opening, not over zero");
  assert.deepEqual(jointValues(ARM_SRDF.articulation, { yaw: 10 }).pitch, { turn: 0, travel: 0 }, "(the raw rows know no opening: the player normalizes)");
  scene.dispose();
});

test("bounds follow the pose and the rest box does not; only the moved subtree is re-measured", () => {
  const scene = createRobotScene(THREE, robotOf(ARM));
  const rest = structuredClone(scene.restBounds);
  assert.deepEqual(scene.bounds, rest);
  scene.setControlValues({ pitch: -90 });
  assert.ok(scene.bounds.max[2] > rest.max[2] + 0.5, "the arm stands up");
  assert.deepEqual(scene.restBounds, rest);
  assert.equal(scene.bounds, scene.bounds, "one box per pose, not one per read");
  scene.dispose();
});

test("the look: a description's colour, the viewer's surface colour without one, Color by part in the order parts always took", () => {
  const model = robotOf(ARM);
  const scene = createRobotScene(THREE, model);
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
  for (const part of model.parts) assert.equal(mesh(part.id).material.color.getHexString(), palette[part.fillIndex % palette.length], part.id);
  scene.setSurfaceLook(look({ surface: { style: "flat", opacity: 0.5 } }));
  assert.equal(mesh("arm:v1").material.isMeshBasicMaterial, true);
  assert.equal(mesh("arm:v1").material.opacity, 0.5);
  scene.dispose();
});

test("a colour the description gives a visual wins over the colours its mesh brought; without one the mesh's own are worn per vertex", () => {
  const red = boxMesh([100, 100, 100], { colors: new Float32Array(Array(8).fill([1, 0, 0]).flat()) });
  const meshes = new Map([[ARM.visuals[2].mesh.url, red], [ARM.visuals[3].mesh.url, red]]);
  const robot = { ...ARM, visuals: ARM.visuals.filter(visual => ["arm:v1", "tool:v1"].includes(visual.id)).map(visual => ({ ...visual, color: visual.id === "arm:v1" ? "#0000ff" : "" })) };
  const scene = createRobotScene(THREE, robotOf(robot, meshes));
  const mesh = id => { let found = null; scene.object3D.traverse((object) => { if (object.userData.partId === id) found = object; }); return found; };
  scene.setSurfaceLook(look());
  assert.deepEqual([mesh("arm:v1").material.vertexColors, mesh("arm:v1").material.color.getHexString(), Boolean(mesh("arm:v1").geometry.getAttribute("color"))], [false, "0000ff", false]);
  assert.deepEqual([mesh("tool:v1").material.vertexColors, mesh("tool:v1").material.color.getHexString(), Boolean(mesh("tool:v1").geometry.getAttribute("color"))], [true, "ffffff", true]);
  assert.notEqual(mesh("tool:v1").geometry.getAttribute("color").array, red.colors, "graded in the scene's own copy, never in the loader's");
  assert.notEqual(mesh("arm:v1").geometry, mesh("tool:v1").geometry, "one mesh, two geometries: only one of them carries colours");
  scene.dispose();
});

test("picking names the link under the ray; a named object is itself; the pick follows the pose", () => {
  const model = robotOf(ARM);
  // The tool's box as a named object of its mesh, as a GLB link's objects are.
  const parts = model.parts.map(part => (part.id === "tool:v1" ? { ...part, id: "tool:v1/object/0", componentName: "flange" } : part));
  const scene = createRobotScene(THREE, { robot: ARM, parts });
  const down = (x, y) => new THREE.Ray(new THREE.Vector3(x, y, 10), new THREE.Vector3(0, 0, -1));
  const arm = scene.pick(down(0.5 * Math.cos(0.3), 0.5 * Math.sin(0.3)));
  assert.deepEqual([arm.kind, arm.linkName, arm.id], ["link", "arm", "link:arm"]);
  assert.ok(Math.abs(arm.point.z - 1.2) < 1e-6, "the surface the ray met first");
  assert.equal(scene.pick(down(5, 5)), null);
  // Just past the arm's end, where only the tool's box is under the ray.
  const flange = scene.pick(down(1.03 * Math.cos(0.3), 1.03 * Math.sin(0.3)));
  assert.deepEqual([flange.kind, flange.linkName, flange.componentId, flange.id], ["component", "tool", "tool:v1/object/0", "tool:v1/object/0"]);
  assert.equal(scene.hasComponent("tool:v1/object/0"), true);
  scene.setControlValues({ yaw: 90 });
  assert.equal(scene.pick(down(0.5 * Math.cos(0.3), 0.5 * Math.sin(0.3)))?.linkName ?? "base", "base");
  scene.dispose();
});

test("a highlight round-trips to the exact look underneath it, in Solid, Flat and Render", () => {
  const scene = createRobotScene(THREE, robotOf(ARM));
  let arm = null;
  scene.object3D.traverse((object) => { if (object.userData.partId === "arm:v1") arm = object; });
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
    scene.setSurfaceLook(dressed);
    assert.equal(arm.renderOrder, 23);
    scene.setHighlight({});
    assert.equal(state(), base, `${name}: and back, exactly`);
  }
  scene.dispose();
});

test("visuals that name one mesh share one geometry, and dispose releases everything the scene made", () => {
  const model = robotOf(ARM);
  const scene = createRobotScene(THREE, model);
  const geometry = id => { let found = null; scene.object3D.traverse((object) => { if (object.userData.partId === id) found = object.geometry; }); return found; };
  // The fixture names one box for the base and another for the turret; two visuals of one URL would share.
  const shared = createRobotScene(THREE, robotOf({ ...ARM, visuals: ARM.visuals.map(visual => ({ ...visual, mesh: ARM.visuals[0].mesh })) }));
  const sharedGeometry = id => { let found = null; shared.object3D.traverse((object) => { if (object.userData.partId === id) found = object.geometry; }); return found; };
  assert.equal(sharedGeometry("base:v1"), sharedGeometry("turret:v1"));
  assert.equal(geometry("base:v1").getAttribute("position").array, model.parts[0].sourceMesh.vertices, "the loader's array, wrapped");
  shared.dispose();

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
  assert.ok(disposed.geometry >= 5 && disposed.material >= model.parts.length, JSON.stringify(disposed));
  assert.equal(scene.pick(new THREE.Ray(new THREE.Vector3(0, 0, 10), new THREE.Vector3(0, 0, -1))), null, "a disposed scene answers nothing");
  assert.equal(scene.setControlValues({ pitch: 10 }), false);
});
