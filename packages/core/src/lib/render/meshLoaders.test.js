import assert from "node:assert/strict";
import test from "node:test";

import { RENDER_FORMAT } from "../fileFormats.js";
import {
  meshFormatFromUrl,
  resolveMeshFormatFromUrl
} from "./meshLoaders.js";

test("meshFormatFromUrl routes native mesh URLs to the correct loader family", () => {
  assert.equal(meshFormatFromUrl("/assets/part.stl"), RENDER_FORMAT.STL);
  assert.equal(meshFormatFromUrl("/assets/part.3mf?download=1"), RENDER_FORMAT.THREE_MF);
  assert.equal(meshFormatFromUrl("/assets/part.glb"), RENDER_FORMAT.GLB);
  assert.equal(meshFormatFromUrl("/assets/part.gltf#scene"), RENDER_FORMAT.GLB);
});

test("meshFormatFromUrl routes CAD asset URLs using the file query extension", () => {
  assert.equal(
    meshFormatFromUrl("/__cad/asset?file=%2Fworkspace%2Frobots%2Ftom%2F3MF%2Fsts3250.3mf&v=abc123"),
    RENDER_FORMAT.THREE_MF
  );
  assert.equal(
    meshFormatFromUrl("/__cad/asset?file=%2Fworkspace%2Frobots%2Ftom%2Fmeshes%2Ftool.glb"),
    RENDER_FORMAT.GLB
  );
});

test("meshFormatFromUrl keeps the headless GLB fallback by default", () => {
  assert.equal(meshFormatFromUrl("/assets/link-mesh.obj"), RENDER_FORMAT.GLB);
  assert.equal(meshFormatFromUrl("/assets/link-mesh"), RENDER_FORMAT.GLB);
});

test("resolveMeshFormatFromUrl allows viewer consumers to preserve STL fallback paths", () => {
  assert.equal(
    resolveMeshFormatFromUrl("/assets/link-mesh.obj", { fallback: RENDER_FORMAT.STL }),
    RENDER_FORMAT.STL
  );
  assert.equal(
    resolveMeshFormatFromUrl("/__cad/asset?file=%2Fworkspace%2Frobots%2Ftom%2F3MF%2Fsts3250.3mf", { fallback: RENDER_FORMAT.STL }),
    RENDER_FORMAT.THREE_MF
  );
});
