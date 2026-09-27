import assert from "node:assert/strict";
import test from "node:test";

import { resolvePackageAssetUrl, resolvePackageDirRef } from "./assetUrl.js";

test("resolvePackageDirRef joins self-contained package refs", () => {
  assert.equal(
    resolvePackageDirRef("/models/step/parts/__cadgen__/models/part.step", "components/abc.glb"),
    "/models/step/parts/__cadgen__/models/part.step/components/abc.glb"
  );
  assert.equal(resolvePackageDirRef("/models/part.step", "./assembly.json"), "/models/part.step/assembly.json");
});

test("resolvePackageAssetUrl repoints the file param on query-style (local-fs) URLs", () => {
  const meshUrl =
    "/__cad/asset?file=%2Fmodels%2Fstep%2Fparts%2F__cadgen__%2Fmodels%2Fpart.step&v=abc123";

  const descriptorUrl = resolvePackageAssetUrl(meshUrl, "assembly.json");
  const descriptor = new URL(descriptorUrl, "http://x.local");
  assert.equal(descriptor.searchParams.get("file"), "/models/step/parts/__cadgen__/models/part.step/assembly.json");
  // v survives so the sub-asset keeps its cache key. There is no dir param: the server
  // serves one root and the request does not name a directory.
  assert.equal(descriptor.searchParams.get("dir"), null);
  assert.equal(descriptor.searchParams.get("v"), "abc123");

  const componentUrl = resolvePackageAssetUrl(meshUrl, "components/7e4f.glb");
  const component = new URL(componentUrl, "http://x.local");
  assert.equal(
    component.searchParams.get("file"),
    "/models/step/parts/__cadgen__/models/part.step/components/7e4f.glb"
  );

  // A naive `${meshUrl}/assembly.json` would have left file at the directory; assert we did NOT.
  assert.notEqual(descriptor.searchParams.get("file"), "/models/step/parts/__cadgen__/models/part.step");
});

test("resolvePackageAssetUrl returns empty for missing inputs", () => {
  assert.equal(resolvePackageAssetUrl("", "assembly.json"), "");
  assert.equal(resolvePackageAssetUrl("/__cad/asset?file=%2Fx", ""), "");
});
