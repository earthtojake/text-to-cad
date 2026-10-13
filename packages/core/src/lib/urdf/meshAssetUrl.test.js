import assert from "node:assert/strict";
import test from "node:test";

import { createHttpCadResourceProvider } from "../../client/resources.js";
import { loadRobotMeshes, robotMeshUrls } from "./loadRobot.js";
import { resolveCadAssetMeshUrl, resolveLocalAssetFileRef } from "./meshAssetUrl.js";

const SOURCE = "/__cad/asset?file=%2Fw%2Fso101_description%2Furdf%2Fso101.urdf&v=7";
const fileOf = url => new URL(url, "http://cad.local/").searchParams.get("file");

test("a package:// mesh is the file under the folder named for its package above the description", () => {
  const url = resolveCadAssetMeshUrl("package://so101_description/meshes/base.stl", SOURCE);
  assert.equal(fileOf(url), "/w/so101_description/meshes/base.stl");
  assert.equal(new URL(url, "http://cad.local/").searchParams.get("v"), "7");
  // The nearest folder of that name, and never above it.
  assert.equal(resolveLocalAssetFileRef("/w/arm/src/arm/urdf/a.urdf", "package://arm/meshes/x.stl"), "/w/arm/src/arm/meshes/x.stl");
  assert.equal(resolveLocalAssetFileRef("/w/arm/urdf/a.urdf", "package://arm/../secrets/x.stl"), "");
  assert.equal(resolveLocalAssetFileRef("C:\\robots\\arm\\urdf\\a.urdf", "package://arm/meshes/x.stl"), "C:/robots/arm/meshes/x.stl");
});

test("a package:// mesh with no folder of its package's name above the description says so", () => {
  // Resolved against the server's root, it fetched the page and failed as a corrupt mesh.
  assert.throws(() => resolveCadAssetMeshUrl("package://other_description/meshes/base.stl", SOURCE),
    /package:\/\/other_description\/meshes\/base\.stl: no folder named “other_description” holds \/w\/so101_description\/urdf\/so101\.urdf/);
  // A description that is not served from the asset route keeps its host's own rule.
  assert.equal(resolveCadAssetMeshUrl("package://other/meshes/base.stl", "/robots/arm.urdf"), "");
});

test("a file:// mesh is its absolute path", () => {
  assert.equal(fileOf(resolveCadAssetMeshUrl("file:///w/so101_description/meshes/base%20link.stl", SOURCE)),
    "/w/so101_description/meshes/base link.stl");
  assert.equal(resolveLocalAssetFileRef("C:/r/a.urdf", "file:///C:/r/meshes/x.stl"), "C:/r/meshes/x.stl");
});

test("a link mesh that fails to load names its link, the mesh as written, and the server's reason", async () => {
  const meshUrl = resolveCadAssetMeshUrl("../meshes/upper_arm.stl", SOURCE);
  const description = { links: [
    { name: "base", visuals: [] },
    { name: "upper_arm", visuals: [{ filename: "../meshes/upper_arm.stl", meshUrl }] }
  ] };
  const reason = "No file at /w/so101_description/meshes/upper_arm.stl";
  const resources = createHttpCadResourceProvider({
    origin: "http://cad.local",
    fetch: async () => new Response(JSON.stringify({ error: reason }), { status: 404 })
  });
  await assert.rejects(loadRobotMeshes(robotMeshUrls(description), { description, resources }), (error) => {
    assert.equal(error.message, `Link “upper_arm” mesh “../meshes/upper_arm.stl”: ${reason}`);
    assert.equal(error.status, 404);
    return true;
  });
});
