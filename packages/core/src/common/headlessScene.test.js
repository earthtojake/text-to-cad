// The snapshot CLI's headless stage draws a GLB, an STL, a 3MF and a robot with the scene
// its VIEWER renderer draws: the same loader, the same builder, the same look, the same
// pose. These hold the seams where a second path would creep back in: which builder a job
// reaches, how the scene is dressed, what sizes the ground, who owns which buffers, how a
// robot is posed, and that a family scene never takes a CAD model's steps.

import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { writeGlb } from "../lib/glb/writeGlb.js";
import { deformedGlb } from "../lib/render/__tests__/deformedGlb.js";
import { buildGlbDocumentFromBuffer, buildMeshDataFromGlbBuffer } from "../lib/render/glbMeshData.js";
import { buildMeshDataFromStlBuffer } from "../lib/render/stlMeshData.js";
import { parseArmSrdf, parseArmUrdf, robotOf } from "../lib/urdf/__tests__/robotFixtures.js";
import { robotOpeningPose } from "../lib/urdf/motion.js";
import { solveUrdfLinkWorldTransforms } from "../lib/urdf/kinematics.js";
import { headlessSceneDress, headlessSceneFamily, headlessSceneModel } from "./headlessScene.js";
import { captureModel, projectedVisibleGeometryFrame, renderJobContext } from "./renderMeshScene.js";
import { resolveSceneSurfaceLook, resolveViewSceneSettings } from "./sceneSettings.js";
import { EDGELESS_VIEW_FEATURES } from "./viewSettings.js";

const job = (kind, extra = {}) => ({ resolved: { kind, url: `/__render_asset/part.${kind}`, inputPath: `/models/part.${kind}` }, ...extra });

function box([x, y, z], size) {
  const [a, b, c] = [x + size, y + size, z + size];
  const corners = [[x, y, z], [a, y, z], [a, b, z], [x, b, z], [x, y, c], [a, y, c], [a, b, c], [x, b, c]];
  const faces = [[0, 2, 1, 0, 3, 2], [4, 5, 6, 4, 6, 7], [0, 1, 5, 0, 5, 4], [2, 3, 7, 2, 7, 6], [1, 2, 6, 1, 6, 5], [3, 0, 4, 3, 4, 7]];
  return new Float32Array(faces.flat().flatMap(index => corners[index]));
}
function glbBytes() {
  const glb = writeGlb({ primitives: [
    { name: "base", node: "base", occurrenceId: "o1.1", positions: box([0, 0, 0], 0.02), color: "#d02020", material: { roughness: 0.05, metalness: 1 } },
    { name: "rider", node: "rider", occurrenceId: "o1.2", positions: box([0.03, 0, 0], 0.01), color: "#2040d0" }
  ] }, { preset: "export" });
  return glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength);
}
// A binary STL of two separate boxes: 24 triangles, one object.
function stlBytes() {
  const triangles = [...box([0, 0, 0], 10), ...box([20, 0, 0], 5)];
  const count = triangles.length / 9;
  const buffer = new ArrayBuffer(84 + count * 50);
  const view = new DataView(buffer);
  view.setUint32(80, count, true);
  for (let triangle = 0; triangle < count; triangle += 1) {
    for (let value = 0; value < 9; value += 1) view.setFloat32(84 + triangle * 50 + 12 + value * 4, triangles[triangle * 9 + value], true);
  }
  return buffer;
}
const settingsFor = (display, kind = "stl") => renderJobContext({ bounds: { min: [0, 0, 0], max: [1, 1, 1] } }, job(kind, { display })).sceneSettings;
const DISPLAYS = {
  "solid light": { mode: "solid", appearance: "light" },
  "solid dark": { mode: "solid", appearance: "dark" },
  render: { mode: "render" },
  "by part": { mode: "solid", surfaces: { colorMode: "by-part" } },
  single: { mode: "render", surfaces: { colorMode: "single", color: "#ff8800" } },
  "flat 50%": { mode: "solid", surfaces: { style: "flat", opacity: 0.5 } }
};
function materialState(object3D) {
  const rows = [];
  object3D.traverse((object) => {
    if (!object.isMesh) return;
    const material = object.material;
    rows.push([object.name, material.type, material.color.getHexString(), material.roughness ?? null, material.metalness ?? null,
      material.clearcoat ?? null, material.emissive?.getHexString() ?? null, material.emissiveIntensity ?? null,
      material.opacity, material.transparent, material.side, object.receiveShadow]);
  });
  return rows;
}

test("every file family the snapshot CLI draws reaches its viewer builder; a STEP model and a drawing do not", async () => {
  for (const kind of ["glb", "stl", "3mf", "urdf", "srdf", "sdf"]) assert.ok(headlessSceneFamily(job(kind)), kind);
  for (const kind of ["step", "stp", "dxf", ""]) assert.equal(headlessSceneFamily(job(kind)), null, kind || "(none)");
  assert.equal(headlessSceneFamily(job("stl")), headlessSceneFamily(job("3mf")), "STL and 3MF are one family: the mesh renderer's");
  assert.equal(headlessSceneFamily(job("urdf")), headlessSceneFamily(job("sdf")), "URDF, SRDF and SDF are one family: the robot renderer's");

  // What each family's build returns IS its builder's scene: the viewer renderer's own object.
  const document = await buildGlbDocumentFromBuffer(glbBytes());
  const glb = headlessSceneFamily(job("glb")).build(THREE, document, job("glb"));
  assert.deepEqual([glb.object3D.name, glb.document === document, document.scene.parent === glb.object3D], ["glb-document", true, true]);
  const mesh = headlessSceneFamily(job("stl")).build(THREE, await buildMeshDataFromStlBuffer(stlBytes()), job("stl"));
  assert.deepEqual([mesh.object3D.name, mesh.meshCount], ["mesh-document", 1]);
  const robot = headlessSceneFamily(job("urdf")).build(THREE, robotOf(parseArmUrdf()), job("urdf"));
  assert.deepEqual([robot.object3D.name, typeof robot.setJointValues, robot.links.has("turret")], ["robot", "function", true]);
  for (const scene of [glb, mesh, robot]) scene.dispose();
});

test("a family scene on the headless stage wears exactly the look the viewer's viewport puts on it", async () => {
  const meshData = await buildMeshDataFromStlBuffer(stlBytes());
  const family = headlessSceneFamily(job("stl"));
  for (const [name, display] of Object.entries(DISPLAYS)) {
    const sceneSettings = settingsFor(display);
    const headless = headlessSceneModel(THREE, family.build(THREE, meshData, job("stl")), headlessSceneDress(sceneSettings));
    // The viewport's own dressing (ShellViewport): the look it resolves, then every mesh takes shadows or none.
    const viewer = family.build(THREE, meshData, job("stl"));
    viewer.setSurfaceLook(resolveSceneSurfaceLook({ themeSettings: sceneSettings.theme, displaySettings: sceneSettings.display,
      renderMode: sceneSettings.render.enabled, renderConfiguration: sceneSettings.render.configuration }));
    viewer.object3D.traverse((object) => { if (object.isMesh) object.receiveShadow = sceneSettings.view.lighting.enabled; });
    assert.deepEqual(materialState(headless.root), materialState(viewer.object3D), name);
    headless.dispose();
    viewer.dispose();
  }
});

test("the look is really worn: Inspect's finish in Solid, a GLB's authored finish in Render, shadows only under the lights", async () => {
  const solid = headlessSceneModel(THREE, headlessSceneFamily(job("glb")).build(THREE, await buildGlbDocumentFromBuffer(glbBytes())),
    headlessSceneDress(settingsFor(DISPLAYS["solid light"], "glb")));
  const render = headlessSceneModel(THREE, headlessSceneFamily(job("glb")).build(THREE, await buildGlbDocumentFromBuffer(glbBytes())),
    headlessSceneDress(settingsFor(DISPLAYS.render, "glb")));
  const base = model => model.displayRecords.find(({ mesh }) => mesh.parent?.name === "base" || mesh.name === "base").mesh;
  const inspect = settingsFor(DISPLAYS["solid light"], "glb").theme.materials;
  assert.deepEqual([base(solid).material.roughness, base(solid).material.metalness], [inspect.roughness, inspect.metalness],
    "Inspect wears the viewer's surface over the file's colour");
  assert.deepEqual([base(render).material.roughness, base(render).material.metalness], [0.05, 1], "Render keeps the finish the file authored");
  assert.deepEqual([base(solid).receiveShadow, base(render).receiveShadow], [false, true]);
  assert.equal(solid.keepsAuthoredFinish, false, "a GLB asks Inspect for no reflection environment, as it does of the viewport");
  solid.dispose();
  render.dispose();
});

test("a robot opens on the headless stage where the viewer opens it, with the requested joints on top, through its joint matrices", () => {
  const family = headlessSceneFamily(job("srdf"));
  const robot = robotOf(parseArmSrdf());
  const opened = family.build(THREE, robot, job("srdf"));
  assert.ok(Math.abs(opened.jointValue("pitch") - (-0.5 * 180 / Math.PI)) < 1e-9, "the SRDF's home state is where it opens");
  const posed = family.build(THREE, robot, job("srdf", { jointValues: { yaw: 40, lift: 0.2 } }));
  const pose = { ...robotOpeningPose(robot.description), yaw: 40, lift: 0.2 };
  assert.deepEqual([posed.jointValue("yaw"), posed.jointValue("lift"), posed.jointValue("pitch")], [40, 0.2, opened.jointValue("pitch")]);
  const solved = solveUrdfLinkWorldTransforms(robot.description, pose);
  for (const [link, frame] of posed.linkFrames()) {
    frame.forEach((value, index) => assert.ok(Math.abs(value - solved.get(link)[index]) < 1e-9, `${link}[${index}]`));
  }
  opened.dispose();
  posed.dispose();
});

test("a posed robot keeps its REST box for the ground while its live box follows the pose", () => {
  const family = headlessSceneFamily(job("urdf"));
  const robot = robotOf(parseArmUrdf());
  const rest = headlessSceneModel(THREE, family.build(THREE, robot, job("urdf")), headlessSceneDress(settingsFor(DISPLAYS.render, "urdf")));
  const posed = headlessSceneModel(THREE, family.build(THREE, robot, job("urdf", { jointValues: { pitch: -90, lift: 0.5 } })),
    headlessSceneDress(settingsFor(DISPLAYS.render, "urdf")));
  assert.notDeepEqual(posed.bounds, rest.bounds, "the arm stands up");
  assert.deepEqual(posed.restBounds, rest.restBounds, "renderModel sizes the grid, stage and studio floor from this box");
  assert.deepEqual(posed.restBounds, posed.scene.restBounds);
  assert.equal(posed.update({ stepParameters: null }), posed, "an output poses nothing more: the scene was posed as it was built");
  rest.dispose();
  posed.dispose();
});

test("a GLB with clips is framed and grounded on the box sampled over every clip, as the viewer frames it", async () => {
  const glb = writeGlb({ primitives: [{ name: "rider", node: "rider", positions: box([0, 0, 0], 0.01), color: "#2040d0" }] },
    { preset: "export", animations: [{ name: "slide", times: new Float32Array([0, 1]),
      channels: [{ node: "rider", translation: new Float32Array([0, 0, 0, 0.1, 0, 0]) }] }] });
  const document = await buildGlbDocumentFromBuffer(glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength));
  const model = headlessSceneModel(THREE, headlessSceneFamily(job("glb")).build(THREE, document), headlessSceneDress(settingsFor(DISPLAYS["solid light"], "glb")));
  assert.deepEqual(model.restBounds, document.animatedBounds);
  assert.ok(model.restBounds.max[0] > document.restBounds.max[0] + 50, "the clip's travel is inside the ground's box");
  model.dispose();
});

test("two scenes over one decode share its arrays and release only their own buffers", async () => {
  const meshData = await buildMeshDataFromStlBuffer(stlBytes());
  const family = headlessSceneFamily(job("stl"));
  const dress = headlessSceneDress(settingsFor(DISPLAYS["solid light"]));
  const [one, two] = [0, 1].map(() => headlessSceneModel(THREE, family.build(THREE, meshData, job("stl")), dress));
  const geometry = model => model.displayRecords[0].mesh.geometry;
  assert.equal(geometry(one).getAttribute("position").array.buffer, meshData.vertices.buffer, "a view over the decode, not a copy");
  assert.equal(geometry(two).getAttribute("position").array.buffer, meshData.vertices.buffer);
  let released = 0;
  geometry(two).addEventListener("dispose", () => { released += 1; });
  one.dispose();
  assert.equal(released, 0, "the other scene still owns its buffers");
  assert.equal(geometry(two).getAttribute("position").count, meshData.vertices.length / 3);
  assert.equal(two.listParts()[0].triangleCount, 24, "and still draws the whole file");
  two.dispose();
  assert.equal(released, 1, "its owner frees them, once");

  // A robot's link geometries wrap the loader's arrays the same way.
  const robot = robotOf(parseArmUrdf());
  const robotFamily = headlessSceneFamily(job("urdf"));
  const [first, second] = [0, 1].map(() => robotFamily.build(THREE, robot, job("urdf")));
  const disposals = [];
  second.object3D.traverse((object) => { if (object.isMesh) object.geometry.addEventListener("dispose", () => disposals.push(object.name)); });
  first.dispose();
  assert.deepEqual(disposals, []);
  second.dispose();
  assert.ok(disposals.length >= robot.parts.length - 2, "each part geometry once (two finger visuals share one)");
});

test("a document whose scene cannot be built is released, not leaked", async () => {
  const family = headlessSceneFamily(job("glb"));
  const document = await buildGlbDocumentFromBuffer(glbBytes());
  let released = 0;
  document.scene.traverse((object) => { if (object.isMesh) object.geometry.addEventListener("dispose", () => { released += 1; }); });
  family.release(document);
  assert.equal(released, 2);
  await assert.rejects(async () => headlessSceneFamily(job("stl")).build(THREE, { vertices: new Float32Array(0), indices: new Uint32Array(0) }, job("stl")),
    /holds no triangles to draw/, "an empty mesh is the viewer's 'No geometry to display', never a blank picture");
});

test("the still's tight frame fits a skinned and morphed GLB where it is drawn; the flattened copy was a different shape", async () => {
  const bytes = deformedGlb();
  const model = headlessSceneModel(THREE, headlessSceneFamily(job("glb")).build(THREE, await buildGlbDocumentFromBuffer(bytes.slice(0))),
    headlessSceneDress(settingsFor(DISPLAYS["solid light"], "glb")));
  model.root.updateMatrixWorld(true);
  // Looking down CAD +Y: screen x is CAD x, screen y is CAD z.
  const camera = new THREE.OrthographicCamera();
  camera.position.set(0, -5000, 0);
  camera.up.set(0, 0, 1);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);
  const frame = projectedVisibleGeometryFrame(model.displayRecords, camera);
  // The L the GPU draws: x from -1000 to 100, z from -500 to 1100 (DEFORMED_EXTENT in CAD mm).
  assert.ok(Math.abs(frame.spanX - 1100) < 1e-3 && Math.abs(frame.spanY - 1600) < 1e-3, JSON.stringify(frame));
  assert.deepEqual(model.bounds.min.map(Math.round), [-1000, -100, -500]);
  const flattened = await buildMeshDataFromGlbBuffer(bytes.slice(0));
  assert.deepEqual([flattened.bounds.min[2], flattened.bounds.max[2]].map(Math.round), [0, 2000],
    "the mesh data a GLB used to be flattened into is the straight, unskinned, unmorphed bar");
  model.dispose();
});

test("a family scene takes none of a CAD model's steps: no edges, explode or section, and --mode list lists what it drew", async () => {
  const context = renderJobContext({ bounds: { min: [0, 0, 0], max: [1, 1, 1] } }, job("glb", {
    display: { mode: "solid", edges: { enabled: true }, exploded: { enabled: true, amount: 1 }, clip: { enabled: true } }
  }));
  assert.deepEqual([context.stepDisplayEnabled, context.edgesVisible, context.topologyDisplayEdgesVisible,
    context.displaySettings.exploded.enabled, context.displaySettings.clip.enabled], [false, false, false, false, false]);
  assert.deepEqual(resolveViewSceneSettings({ display: { mode: "solid", edges: { enabled: true } }, features: EDGELESS_VIEW_FEATURES }).view.edges.enabled, false);

  const model = headlessSceneModel(THREE, headlessSceneFamily(job("glb")).build(THREE, await buildGlbDocumentFromBuffer(glbBytes())),
    headlessSceneDress(context.sceneSettings));
  assert.equal(model.runtime, undefined, "no CAD runtime: captureModel skips the exploded view, topology edges and line widths");
  const listed = await captureModel({ model, context: { ...context, mode: "list" } }, { job: job("glb") });
  assert.deepEqual(listed.parts.map(({ ref, name, triangleCount, vertexCount }) => [ref, name, triangleCount, vertexCount]),
    [["#o1.1", "base", 12, 24], ["#o1.2", "rider", 12, 24]]);
  assert.deepEqual(listed.parts[1].bounds, { min: [30, -10, 0], max: [40, 0, 10] }, "placed in CAD millimetres, as drawn");
  await assert.rejects(() => captureModel({ model, context: { ...context, mode: "section" } }, { job: job("glb") }),
    /section mode cuts a STEP model's solids/);
  model.dispose();

  const stl = headlessSceneModel(THREE, headlessSceneFamily(job("stl")).build(THREE, await buildMeshDataFromStlBuffer(stlBytes()), job("stl")),
    headlessSceneDress(context.sceneSettings));
  assert.deepEqual(stl.listParts().map(({ id, name, triangleCount }) => [id, name, triangleCount]), [["", "", 24]]);
  stl.dispose();
});
